"""Wire the agents into a pipeline over the bus and emit a PR artifact.

Flow: Triage (gate) -> Planner -> (Coder -> Verifier -> Security -> Reviewer)* ->
human gate -> PR. A non-actionable issue stops at triage. The inner steps loop
up to ``max_revisions`` so a regressing or risky patch can be revised. Only a
trustworthy verdict **and** clean security **and** reviewer approval reach the
human gate; only human approval writes the PR.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from trustband.agents import Coder, Planner, Reviewer, SecurityReviewer, Triage
from trustband.bus import AgentBus, AgentMessage, ApprovalRequest
from trustband.contracts import (
    Decision,
    FixPlan,
    Issue,
    Patch,
    ReviewReport,
    SecurityReport,
    TriageReport,
    VerdictReport,
)
from trustband.verifier import verify

_PARTICIPANTS = ["triage", "planner", "coder", "verifier", "security", "reviewer", "human"]


@dataclass
class RunResult:
    """The outcome of one orchestrated run, with metrics for the benchmark."""

    issue_id: str
    triage: TriageReport | None
    plan: FixPlan | None
    patch: Patch | None
    verdict: VerdictReport | None
    review: ReviewReport | None
    security: SecurityReport | None
    decision: Decision | None
    merged: bool
    pr_path: Path | None
    revisions: int
    verifier_rejections: int
    regressions_caught: int
    security_blocks: int

    @property
    def actionable(self) -> bool:
        """True when triage deemed the issue actionable."""
        return self.triage is not None and self.triage.actionable


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
    security: SecurityReport,
    diff: str,
) -> str:
    """Render a human-readable PR description backed by the verifier evidence."""
    assertions = "\n".join(
        f"- {'PASS' if a.passed else 'FAIL'} {a.name} — {a.detail}" for a in verdict.assertions
    )
    findings = (
        "\n".join(f"- **{f.severity.value}**: {f.message}" for f in review.findings) or "- none"
    )
    sec = "clean" if security.clean else "findings"
    sec_findings = (
        "\n".join(f"- **{f.severity.value}**: {f.message}" for f in security.findings) or "- none"
    )
    suite_green = bool(verdict.after and verdict.after.all_green)
    return (
        f"# PR: {issue.title} ({issue.id})\n\n"
        "> Opened by TrustBand after the Verifier and Security agents cleared the fix.\n\n"
        f"## Summary\n{patch.summary} (revision {patch.revision})\n\n"
        f"## Root cause\n{plan.root_cause}\n\n"
        f"## Verifier evidence — verdict: **{verdict.verdict.value.upper()}**\n"
        f"- target tests now passing: {verdict.newly_passing}\n"
        f"- regressions (green -> red): {verdict.regressions or 'none'}\n"
        f"- suite green after patch: {suite_green}\n\n"
        f"### Trajectory assertions\n{assertions}\n\n"
        f"## Security — {sec}\n{sec_findings}\n\n"
        f"## Review — {review.status.value}\n{findings}\n\n"
        f"## Diff\n```diff\n{diff}```\n"
    )


class Orchestrator:
    """Drives the agents over a bus and produces a verified, gated PR."""

    def __init__(
        self,
        bus: AgentBus,
        triage: Triage,
        planner: Planner,
        coder: Coder,
        security: SecurityReviewer,
        reviewer: Reviewer,
        max_revisions: int = 2,
        artifacts_dir: str | Path = "artifacts",
    ) -> None:
        """Bind the collaboration layer, the agents, and run limits."""
        self.bus = bus
        self.triage = triage
        self.planner = planner
        self.coder = coder
        self.security = security
        self.reviewer = reviewer
        self.max_revisions = max(1, max_revisions)
        self.artifacts_dir = Path(artifacts_dir)

    def run(self, issue: Issue) -> RunResult:
        """Run the full pipeline for one issue and return the result + metrics."""
        self.bus.send(
            AgentMessage(
                sender="orchestrator",
                kind="note",
                text=f"opened room for {issue.id}; participants: {', '.join(_PARTICIPANTS)}",
            )
        )

        triage = self.triage.run(issue)
        if not triage.actionable:
            self.bus.send(
                AgentMessage(
                    sender="orchestrator",
                    kind="note",
                    text=f"triage: non-actionable ({triage.category.value}); stopping",
                )
            )
            return RunResult(
                issue_id=issue.id,
                triage=triage,
                plan=None,
                patch=None,
                verdict=None,
                review=None,
                security=None,
                decision=None,
                merged=False,
                pr_path=None,
                revisions=0,
                verifier_rejections=0,
                regressions_caught=0,
                security_blocks=0,
            )

        plan = self.planner.plan(issue)

        patch: Patch | None = None
        verdict: VerdictReport | None = None
        review: ReviewReport | None = None
        security: SecurityReport | None = None
        revisions = 0
        verifier_rejections = 0
        regressions: set[str] = set()
        security_blocks = 0

        for revision in range(1, self.max_revisions + 1):
            revisions = revision
            patch = self.coder.code(issue, plan, review)
            patch.revision = revision
            verdict = verify(issue, patch, target_tests=triage.target_tests or None)
            self.bus.send(
                AgentMessage(
                    sender="verifier",
                    kind="note",
                    text=f"verdict={verdict.verdict.value} regressions={verdict.regressions}",
                )
            )
            self.bus.handoff("verifier", "security", verdict)
            security = self.security.review(issue, patch)
            review = self.reviewer.review(issue, patch, verdict, security)

            if not verdict.trustworthy:
                verifier_rejections += 1
            regressions |= set(verdict.regressions)
            if not security.clean:
                security_blocks += 1

            if verdict.trustworthy and security.clean and review.approved:
                break

        merged = False
        decision: Decision | None = None
        pr_path: Path | None = None
        cleared = bool(
            verdict
            and verdict.trustworthy
            and security
            and security.clean
            and review
            and review.approved
        )
        if cleared:
            decision = self.bus.request_approval(
                ApprovalRequest(
                    issue_id=issue.id,
                    summary=f"Merge fix for {issue.id}? verified green, security clean.",
                    artifact_type="Patch",
                    payload={"summary": patch.summary if patch else ""},
                )
            )
            if decision.approved:
                pr_path = self._open_pr(issue, plan, patch, verdict, review, security)
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
                    text="not merged: verdict, security, or review did not pass",
                )
            )

        return RunResult(
            issue_id=issue.id,
            triage=triage,
            plan=plan,
            patch=patch,
            verdict=verdict,
            review=review,
            security=security,
            decision=decision,
            merged=merged,
            pr_path=pr_path,
            revisions=revisions,
            verifier_rejections=verifier_rejections,
            regressions_caught=len(regressions),
            security_blocks=security_blocks,
        )

    def _open_pr(
        self,
        issue: Issue,
        plan: FixPlan,
        patch: Patch,
        verdict: VerdictReport,
        review: ReviewReport,
        security: SecurityReport,
    ) -> Path:
        """Write the PR description and diff into the artifacts directory."""
        out_dir = self.artifacts_dir / issue.id
        out_dir.mkdir(parents=True, exist_ok=True)
        diff = _unified_diff(issue.repo_path, patch)
        (out_dir / "fix.diff").write_text(diff)
        pr_path = out_dir / "PR.md"
        pr_path.write_text(_render_pr(issue, plan, patch, verdict, review, security, diff))
        return pr_path
