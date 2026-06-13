"""The Planner, Coder, and Reviewer agents.

Each agent turns a prompt into a typed artifact via the LLMClient, then hands it
off on the shared bus so the collaboration is visible in the room transcript.
The Reviewer additionally respects the Verifier's evidence: it cannot approve a
patch the Verifier rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

from trustband.bus import AgentBus, AgentMessage
from trustband.contracts import (
    Finding,
    FixPlan,
    Issue,
    Patch,
    ReviewReport,
    ReviewStatus,
    SecurityReport,
    Severity,
    TriageReport,
    VerdictReport,
)
from trustband.llm import LLMClient, parse_with_retry

_MAX_CONTEXT_BYTES = 8000


def read_repo_context(repo_path: str | Path, limit: int = _MAX_CONTEXT_BYTES) -> str:
    """Return a compact text snapshot of the repo's Python files for prompting."""
    root = Path(repo_path)
    chunks: list[str] = []
    budget = limit
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        block = f"# file: {path.relative_to(root)}\n{path.read_text()}\n"
        if len(block) > budget:
            break
        chunks.append(block)
        budget -= len(block)
    return "\n".join(chunks)


class Planner:
    """Reads the issue + repo and produces a structured FixPlan."""

    name = "planner"

    def __init__(self, bus: AgentBus, llm: LLMClient) -> None:
        """Bind the agent to a bus and an LLM client."""
        self.bus = bus
        self.llm = llm

    def plan(self, issue: Issue) -> FixPlan:
        """Produce a FixPlan for the issue and hand it off to the Coder."""
        context = read_repo_context(issue.repo_path)
        prompt = (
            "You are a planning agent. Read the issue and repo, return a FixPlan as JSON.\n"
            f"## Issue {issue.id}: {issue.title}\n{issue.description}\n\n## Repo\n{context}"
        )
        plan = parse_with_retry(self.llm, prompt, "plan", FixPlan)
        plan.issue_id = issue.id
        self.bus.send(
            AgentMessage(sender=self.name, kind="note", text=f"root cause: {plan.root_cause}")
        )
        self.bus.handoff(self.name, "coder", plan)
        return plan


class Coder:
    """Implements a FixPlan into a Patch, optionally addressing a prior review."""

    name = "coder"

    def __init__(self, bus: AgentBus, llm: LLMClient) -> None:
        """Bind the agent to a bus and an LLM client."""
        self.bus = bus
        self.llm = llm

    def code(self, issue: Issue, plan: FixPlan, prior_review: ReviewReport | None = None) -> Patch:
        """Produce a Patch for the plan and hand it off to the Verifier."""
        context = read_repo_context(issue.repo_path)
        review_note = ""
        if prior_review is not None:
            findings = "; ".join(f.message for f in prior_review.findings) or prior_review.summary
            review_note = f"\n## Address this prior review feedback\n{findings}"
        prompt = (
            "You are a coding agent. Implement the FixPlan and return a Patch as JSON "
            "(full file contents per change).\n"
            f"## Plan\n{plan.model_dump_json()}{review_note}\n\n## Repo\n{context}"
        )
        patch = parse_with_retry(self.llm, prompt, "code", Patch)
        patch.issue_id = issue.id
        self.bus.send(
            AgentMessage(
                sender=self.name,
                kind="note",
                text=f"patch touches {[change.path for change in patch.changes]}",
            )
        )
        self.bus.handoff(self.name, "verifier", patch)
        return patch


class Reviewer:
    """Critiques a patch; cannot approve what the Verifier rejected."""

    name = "reviewer"

    def __init__(self, bus: AgentBus, llm: LLMClient) -> None:
        """Bind the agent to a bus and an LLM client."""
        self.bus = bus
        self.llm = llm

    def review(
        self,
        issue: Issue,
        patch: Patch,
        verdict: VerdictReport,
        security: SecurityReport | None = None,
    ) -> ReviewReport:
        """Produce a ReviewReport aggregating the Verifier and Security evidence.

        The reviewer cannot approve a patch the Verifier rejected, nor one with a
        critical security finding — even when every test passes.
        """
        prompt = (
            "You are a code reviewer. Given the patch, the verifier's report and the "
            "security report, return a ReviewReport as JSON.\n"
            f"## Patch\n{patch.model_dump_json()}\n## Verdict\n{verdict.model_dump_json()}"
        )
        review = parse_with_retry(self.llm, prompt, "review", ReviewReport)
        review.issue_id = issue.id
        if not verdict.trustworthy:
            review.status = ReviewStatus.REQUEST_CHANGES
            review.findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    message=f"verifier rejected the patch: {verdict.reasons}",
                )
            )
        if security is not None and not security.clean:
            review.status = ReviewStatus.REQUEST_CHANGES
            review.findings.extend(security.findings)
        self.bus.send(
            AgentMessage(
                sender=self.name, kind="note", text=f"review status: {review.status.value}"
            )
        )
        self.bus.handoff(self.name, "human", review)
        return review


class Triage:
    """Classifies an incoming issue and decides whether it is actionable."""

    name = "triage"

    def __init__(self, bus: AgentBus, llm: LLMClient) -> None:
        """Bind the agent to a bus and an LLM client."""
        self.bus = bus
        self.llm = llm

    def run(self, issue: Issue) -> TriageReport:
        """Triage the issue and hand the report off to the Planner."""
        prompt = (
            "You are a triage agent. Classify the issue and decide whether it is an "
            "actionable bug. Return a TriageReport as JSON.\n"
            f"## Issue {issue.id}: {issue.title}\n{issue.description}"
        )
        report = parse_with_retry(self.llm, prompt, "triage", TriageReport)
        report.issue_id = issue.id
        if issue.failing_test and not report.target_tests:
            report.target_tests = [issue.failing_test]
        self.bus.send(
            AgentMessage(
                sender=self.name,
                kind="note",
                text=f"triage: actionable={report.actionable} category={report.category.value}",
            )
        )
        self.bus.handoff(self.name, "planner", report)
        return report


_RISK_PATTERNS: list[tuple[re.Pattern[str], Severity, str]] = [
    (re.compile(r"\beval\s*\("), Severity.CRITICAL, "use of eval()"),
    (re.compile(r"\bexec\s*\("), Severity.CRITICAL, "use of exec()"),
    (re.compile(r"\bos\.system\s*\("), Severity.CRITICAL, "use of os.system()"),
    (re.compile(r"shell\s*=\s*True"), Severity.CRITICAL, "subprocess with shell=True"),
    (re.compile(r"\bpickle\.loads?\s*\("), Severity.RISK, "untrusted pickle deserialization"),
    (
        re.compile(r'''(?i)(password|secret|api_key|token)\s*=\s*['"][^'"]+['"]'''),
        Severity.CRITICAL,
        "possible hardcoded secret",
    ),
]


class SecurityReviewer:
    """Deterministic (non-LLM) static scan of a patch for risky constructs."""

    name = "security"

    def __init__(self, bus: AgentBus) -> None:
        """Bind the agent to a bus. The scan is deterministic, so it needs no LLM."""
        self.bus = bus

    def review(self, issue: Issue, patch: Patch) -> SecurityReport:
        """Scan each changed file for risky patterns and report findings."""
        findings: list[Finding] = []
        for change in patch.changes:
            for lineno, line in enumerate(change.new_content.splitlines(), start=1):
                for pattern, severity, message in _RISK_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            Finding(
                                severity=severity, message=message, path=change.path, line=lineno
                            )
                        )
        report = SecurityReport(
            issue_id=issue.id, findings=findings, summary=f"{len(findings)} risk finding(s)"
        )
        self.bus.send(
            AgentMessage(
                sender=self.name,
                kind="note",
                text=f"security: {len(findings)} finding(s), clean={report.clean}",
            )
        )
        self.bus.handoff(self.name, "reviewer", report)
        return report
