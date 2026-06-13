"""The Planner, Coder, and Reviewer agents.

Each agent turns a prompt into a typed artifact via the LLMClient, then hands it
off on the shared bus so the collaboration is visible in the room transcript.
The Reviewer additionally respects the Verifier's evidence: it cannot approve a
patch the Verifier rejected.
"""

from __future__ import annotations

from pathlib import Path

from trustband.bus import AgentBus, AgentMessage
from trustband.contracts import (
    Finding,
    FixPlan,
    Issue,
    Patch,
    ReviewReport,
    ReviewStatus,
    Severity,
    VerdictReport,
)
from trustband.llm import LLMClient, extract_json

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
        plan = FixPlan.model_validate_json(extract_json(self.llm.complete(prompt, kind="plan")))
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
        patch = Patch.model_validate_json(extract_json(self.llm.complete(prompt, kind="code")))
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

    def review(self, issue: Issue, patch: Patch, verdict: VerdictReport) -> ReviewReport:
        """Produce a ReviewReport, overriding to request changes if the verdict failed."""
        prompt = (
            "You are a code reviewer. Given the patch and the verifier's report, "
            "return a ReviewReport as JSON.\n"
            f"## Patch\n{patch.model_dump_json()}\n## Verdict\n{verdict.model_dump_json()}"
        )
        review = ReviewReport.model_validate_json(
            extract_json(self.llm.complete(prompt, kind="review"))
        )
        review.issue_id = issue.id
        if not verdict.trustworthy:
            review.status = ReviewStatus.REQUEST_CHANGES
            review.findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    message=f"verifier rejected the patch: {verdict.reasons}",
                )
            )
        self.bus.send(
            AgentMessage(
                sender=self.name, kind="note", text=f"review status: {review.status.value}"
            )
        )
        self.bus.handoff(self.name, "human", review)
        return review
