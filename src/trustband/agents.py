"""The Planner, Coder, and Reviewer agents.

Each agent turns a prompt into a typed artifact via the LLMClient, then hands it
off on the shared bus so the collaboration is visible in the room transcript.
The Reviewer additionally respects the Verifier's evidence: it cannot approve a
patch the Verifier rejected.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from trustband.bus import AgentBus, AgentMessage
from trustband.contracts import (
    AssertionResult,
    Finding,
    FixPlan,
    Issue,
    Patch,
    ReproReport,
    ReviewReport,
    ReviewStatus,
    SecurityReport,
    Severity,
    TriageReport,
    VerdictReport,
)
from trustband.llm import LLMClient, parse_with_retry
from trustband.runner import run_pytest

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
                text=f"patch touches {patch.touched_paths}",
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
        self.bus.handoff(self.name, "reproducer", report)
        return report


def _hits(targets: list[str], nodeids: set[str]) -> bool:
    """True if any target test name appears within the given node ids."""
    return any(target in nodeid for target in targets for nodeid in nodeids)


class Reproducer:
    """Confirms the bug reproduces before any fix; authors a failing test if none exists."""

    name = "reproducer"

    def __init__(self, bus: AgentBus, llm: LLMClient) -> None:
        """Bind the agent to a bus and an LLM client."""
        self.bus = bus
        self.llm = llm

    def run(self, issue: Issue, target_tests: list[str]) -> ReproReport:
        """Confirm reproduction (or author a failing test), then hand off to the Planner."""
        baseline = run_pytest(issue.repo_path)
        baseline_red = set(baseline.failed) | set(baseline.errors)
        if target_tests and _hits(target_tests, baseline_red):
            return self._handoff(
                ReproReport(
                    issue_id=issue.id,
                    reproduced=True,
                    target_tests=list(target_tests),
                    quality_checks=[
                        AssertionResult(
                            name="existing_target_fails",
                            passed=True,
                            detail=f"targets={target_tests}",
                        )
                    ],
                    detail="target test(s) fail at baseline",
                )
            )

        # No usable failing test — ask the model to author one that captures the bug.
        prompt = (
            "You are a reproduction agent. Write a pytest test that FAILS on the current "
            "(buggy) code and will pass once the bug is fixed. Return a Patch as JSON that "
            f"adds a new test file.\n## Issue {issue.id}: {issue.title}\n{issue.description}\n\n"
            f"## Repo\n{read_repo_context(issue.repo_path)}"
        )
        authored = parse_with_retry(self.llm, prompt, "reproduce", Patch)
        authored.issue_id = issue.id
        after = run_pytest(issue.repo_path, scaffold=authored)
        new_failed = set(after.failed) - baseline_red
        new_errors = set(after.errors) - baseline_red
        reproduced = bool(new_failed) and not new_errors
        quality_checks = [
            AssertionResult(
                name="authored_test_created_failure",
                passed=bool(new_failed),
                detail=f"new_failed={sorted(new_failed)}",
            ),
            AssertionResult(
                name="authored_test_has_no_new_errors",
                passed=not new_errors,
                detail=f"new_errors={sorted(new_errors)}",
            ),
        ]
        detail = "authored a failing test"
        if new_errors:
            detail = "authored test produced pytest errors, not a clean failing test"
        elif not new_failed:
            detail = "authored test did not fail on the buggy code"
        return self._handoff(
            ReproReport(
                issue_id=issue.id,
                reproduced=reproduced,
                target_tests=sorted(new_failed),
                authored_test=authored if reproduced else None,
                quality_checks=quality_checks,
                detail=detail,
            )
        )

    def _handoff(self, report: ReproReport) -> ReproReport:
        """Post the repro note and hand the report to the Planner."""
        self.bus.send(
            AgentMessage(
                sender=self.name,
                kind="note",
                text=f"reproduced={report.reproduced} targets={report.target_tests}",
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

    def __init__(self, bus: AgentBus, use_bandit: bool = False) -> None:
        """Bind the agent to a bus. The regex scan is always on; bandit SAST is opt-in."""
        self.bus = bus
        self.use_bandit = use_bandit

    def review(self, issue: Issue, patch: Patch) -> SecurityReport:
        """Scan each changed file for risky patterns and report findings."""
        findings: list[Finding] = []
        for path, content in patch.security_snippets():
            for lineno, line in enumerate(content.splitlines(), start=1):
                for pattern, severity, message in _RISK_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            Finding(
                                severity=severity, message=message, path=path, line=lineno
                            )
                        )
        if self.use_bandit:
            findings.extend(self._bandit_findings(patch))
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

    def _bandit_findings(self, patch: Patch) -> list[Finding]:
        """Run bandit (real SAST) on the patched files; return [] if unavailable or clean."""
        severity_map = {
            "HIGH": Severity.CRITICAL,
            "MEDIUM": Severity.RISK,
            "LOW": Severity.SUGGESTION,
        }
        with tempfile.TemporaryDirectory(prefix="trustband-bandit-") as td:
            root = Path(td)
            for path, content in patch.security_snippets():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "bandit", "-q", "-f", "json", "-r", str(root)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except (OSError, subprocess.SubprocessError):
                return []
        try:
            data = json.loads(proc.stdout or "{}")
        except ValueError:
            return []
        findings: list[Finding] = []
        for result in data.get("results", []):
            severity = severity_map.get(result.get("issue_severity", "LOW"), Severity.SUGGESTION)
            message = f"bandit {result.get('test_id', '')}: {result.get('issue_text', '')}".strip()
            findings.append(
                Finding(
                    severity=severity,
                    message=message,
                    path=Path(result.get("filename", "")).name,
                    line=result.get("line_number"),
                )
            )
        return findings
