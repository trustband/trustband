"""Stable JSON output contracts for CLI and benchmark consumers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trustband.benchmark import BenchmarkReport
from trustband.orchestrator import RunResult


class RunJsonResult(BaseModel):
    """Machine-readable result for ``trustband run --json``."""

    issue_id: str
    actionable: bool
    merged: bool
    revisions: int
    triage: dict[str, Any] | None = None
    repro: dict[str, Any] | None = None
    verdict: dict[str, Any] | None = None
    security: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class BenchmarkJsonResult(BaseModel):
    """Machine-readable benchmark report."""

    mode: str
    model: str | None = None
    total: int
    correct: int
    accuracy: float
    merged: int
    bad_patches_caught: int
    regressions_prevented: int
    security_issues_caught: int
    nonactionable_filtered: int
    avg_revisions: float
    outcomes: list[dict[str, Any]]


def run_to_json_result(result: RunResult) -> RunJsonResult:
    """Convert an internal run result into the stable CLI JSON contract."""
    artifacts: dict[str, str] = {}
    if result.pr_path is not None:
        artifacts["pr"] = str(result.pr_path)
        artifacts["diff"] = str(result.pr_path.with_name("fix.diff"))
    return RunJsonResult(
        issue_id=result.issue_id,
        actionable=result.actionable,
        merged=result.merged,
        revisions=result.revisions,
        triage=result.triage.model_dump() if result.triage else None,
        repro=result.repro.model_dump() if result.repro else None,
        verdict=result.verdict.model_dump() if result.verdict else None,
        security=result.security.model_dump() if result.security else None,
        review=result.review.model_dump() if result.review else None,
        decision=result.decision.model_dump() if result.decision else None,
        artifacts=artifacts,
    )


def benchmark_to_json_result(
    report: BenchmarkReport,
    *,
    mode: str,
    model: str | None = None,
) -> BenchmarkJsonResult:
    """Convert a benchmark report into the stable CLI JSON contract."""
    outcomes = [
        {
            "name": outcome.name,
            "expected_merge": outcome.expected_merge,
            "merged": outcome.merged,
            "correct": outcome.correct,
            "revisions": outcome.revisions,
            "verifier_rejections": outcome.verifier_rejections,
            "regressions_caught": outcome.regressions_caught,
            "security_blocks": outcome.security_blocks,
            "note": outcome.note,
            "status": outcome.status,
            "failure_reason": outcome.failure_reason,
        }
        for outcome in report.outcomes
    ]
    return BenchmarkJsonResult(
        mode=mode,
        model=model,
        total=report.total,
        correct=report.correct,
        accuracy=report.accuracy,
        merged=report.merged,
        bad_patches_caught=report.bad_patches_caught,
        regressions_prevented=report.regressions_prevented,
        security_issues_caught=report.security_issues_caught,
        nonactionable_filtered=report.nonactionable_filtered,
        avg_revisions=report.avg_revisions,
        outcomes=outcomes,
    )
