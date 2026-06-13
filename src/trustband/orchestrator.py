"""Wire the agents into a pipeline over the bus and emit a PR artifact.

Flow: Planner -> (Coder -> Verifier -> Reviewer)* -> human gate -> PR.
The Coder/Verifier/Reviewer steps loop up to ``max_revisions`` so a rejected
patch can be revised. Only a trustworthy verdict plus reviewer approval reaches
the human gate; only human approval writes the PR.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from trustband.agents import Coder, Planner, Reviewer
from trustband.bus import AgentBus, AgentMessage, ApprovalRequest
from trustband.contracts import Decision, FixPlan, Issue, Patch, ReviewReport, VerdictReport
from trustband.verifier import verify


@dataclass
class RunResult:
    """The outcome of one orchestrated run."""

    issue_id: str
    plan: FixPlan
    patch: Patch
    verdict: VerdictReport
    review: ReviewReport
    decision: Decision | None
    merged: bool
    pr_path: Path | None
    revisions: int


def _unified_diff(repo_path: str | Path, patch: Patch) -> str:
    """Render the patch as a unified diff against the current repo contents."""
    root = Path(repo_path)
    blocks: list[str] = []
    for change in patch.changes:
        target = root / change.path
        original = target.read_text() if target.exists() else ""
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            change.new_content.splitlines(keepends=True),
            fromfile=f"a/{change.path}",
            tofile=f"b/{change.path}",
        )
        blocks.append("".join(diff))
    return "\n".join(blocks)


def _render_pr(
    issue: Issue,
    plan: FixPlan,
    patch: Patch,
    verdict: VerdictReport,
    review: ReviewReport,
    diff: str,
) -> str:
    """Render a human-readable PR description backed by the verifier evidence."""
    assertions = "\n".join(
        f"- {'PASS' if a.passed else 'FAIL'} {a.name} — {a.detail}" for a in verdict.assertions
    )
    findings = (
        "\n".join(f"- **{f.severity.value}**: {f.message}" for f in review.findings) or "- none"
    )
    suite_green = bool(verdict.after and verdict.after.all_green)
    return (
        f"# PR: {issue.title} ({issue.id})\n\n"
        "> Opened by TrustBand after the Verifier confirmed the fix earns the merge.\n\n"
        f"## Summary\n{patch.summary}\n\n"
        f"## Root cause\n{plan.root_cause}\n\n"
        f"## Verifier evidence — verdict: **{verdict.verdict.value.upper()}**\n"
        f"- target tests now passing: {verdict.newly_passing}\n"
        f"- regressions (green -> red): {verdict.regressions or 'none'}\n"
        f"- suite green after patch: {suite_green}\n\n"
        f"### Trajectory assertions\n{assertions}\n\n"
        f"## Review — {review.status.value}\n{findings}\n\n"
        f"## Diff\n```diff\n{diff}```\n"
    )


class Orchestrator:
    """Drives the agents over a bus and produces a verified, gated PR."""

    def __init__(
        self,
        bus: AgentBus,
        planner: Planner,
        coder: Coder,
        reviewer: Reviewer,
        max_revisions: int = 2,
        artifacts_dir: str | Path = "artifacts",
    ) -> None:
        """Bind the collaboration layer, the three agents, and run limits."""
        self.bus = bus
        self.planner = planner
        self.coder = coder
        self.reviewer = reviewer
        self.max_revisions = max(1, max_revisions)
        self.artifacts_dir = Path(artifacts_dir)

    def run(self, issue: Issue) -> RunResult:
        """Run the full pipeline for one issue and return the result."""
        self.bus.send(
            AgentMessage(sender="orchestrator", kind="note", text=f"opened room for {issue.id}")
        )
        plan = self.planner.plan(issue)

        patch: Patch | None = None
        verdict: VerdictReport | None = None
        review: ReviewReport | None = None
        revisions = 0
        for revision in range(1, self.max_revisions + 1):
            revisions = revision
            patch = self.coder.code(issue, plan, review)
            patch.revision = revision
            verdict = verify(issue, patch)
            self.bus.send(
                AgentMessage(
                    sender="verifier",
                    kind="note",
                    text=f"verdict={verdict.verdict.value} regressions={verdict.regressions}",
                )
            )
            self.bus.handoff("verifier", "reviewer", verdict)
            review = self.reviewer.review(issue, patch, verdict)
            if verdict.trustworthy and review.approved:
                break

        merged = False
        decision: Decision | None = None
        pr_path: Path | None = None
        if verdict is not None and verdict.trustworthy and review is not None and review.approved:
            decision = self.bus.request_approval(
                ApprovalRequest(
                    issue_id=issue.id,
                    summary=f"Merge fix for {issue.id}? target green, no regressions.",
                    artifact_type="Patch",
                    payload={"summary": patch.summary if patch else ""},
                )
            )
            if decision.approved:
                pr_path = self._open_pr(issue, plan, patch, verdict, review)
                merged = True
                self.bus.send(
                    AgentMessage(
                        sender="orchestrator", kind="note", text=f"approved; PR at {pr_path}"
                    )
                )
        else:
            self.bus.send(
                AgentMessage(
                    sender="orchestrator",
                    kind="note",
                    text="not merged: verdict or review did not pass",
                )
            )

        return RunResult(
            issue_id=issue.id,
            plan=plan,
            patch=patch,
            verdict=verdict,
            review=review,
            decision=decision,
            merged=merged,
            pr_path=pr_path,
            revisions=revisions,
        )

    def _open_pr(
        self,
        issue: Issue,
        plan: FixPlan,
        patch: Patch,
        verdict: VerdictReport,
        review: ReviewReport,
    ) -> Path:
        """Write the PR description and diff into the artifacts directory."""
        out_dir = self.artifacts_dir / issue.id
        out_dir.mkdir(parents=True, exist_ok=True)
        diff = _unified_diff(issue.repo_path, patch)
        (out_dir / "fix.diff").write_text(diff)
        pr_path = out_dir / "PR.md"
        pr_path.write_text(_render_pr(issue, plan, patch, verdict, review, diff))
        return pr_path
