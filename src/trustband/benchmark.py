"""Benchmark the band across all showcase scenarios and report effect metrics.

This produces the quantitative evidence for the project: how often the band
reaches the correct outcome, how many bad patches the Verifier caught, how many
regressions it prevented, and how many risky patches the Security agent blocked.
Everything runs offline and deterministically, so the numbers are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from trustband.agents import Coder, Planner, Reproducer, Reviewer, SecurityReviewer, Triage
from trustband.bus import InMemoryBus
from trustband.orchestrator import Orchestrator, RunResult
from trustband.scenarios import SCENARIOS, Scenario


@dataclass
class ScenarioOutcome:
    """The measured outcome of one scenario run."""

    name: str
    expected_merge: bool
    merged: bool
    correct: bool
    revisions: int
    verifier_rejections: int
    regressions_caught: int
    security_blocks: int
    note: str


@dataclass
class BenchmarkReport:
    """Aggregate metrics across all scenario outcomes."""

    outcomes: list[ScenarioOutcome]

    @property
    def total(self) -> int:
        """Number of scenarios run."""
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        """Scenarios whose merge outcome matched expectation."""
        return sum(1 for outcome in self.outcomes if outcome.correct)

    @property
    def merged(self) -> int:
        """Scenarios where a fix was shipped."""
        return sum(1 for outcome in self.outcomes if outcome.merged)

    @property
    def bad_patches_caught(self) -> int:
        """Scenarios where the Verifier rejected at least one patch."""
        return sum(1 for outcome in self.outcomes if outcome.verifier_rejections > 0)

    @property
    def regressions_prevented(self) -> int:
        """Total distinct regressions the Verifier flagged across scenarios."""
        return sum(outcome.regressions_caught for outcome in self.outcomes)

    @property
    def security_issues_caught(self) -> int:
        """Scenarios where the Security agent blocked at least one patch."""
        return sum(1 for outcome in self.outcomes if outcome.security_blocks > 0)

    @property
    def nonactionable_filtered(self) -> int:
        """Scenarios correctly stopped at triage (expected no merge, none happened)."""
        return sum(
            1 for outcome in self.outcomes if not outcome.expected_merge and not outcome.merged
        )

    @property
    def avg_revisions(self) -> float:
        """Average revisions across scenarios that did real work (revisions > 0)."""
        acted = [outcome.revisions for outcome in self.outcomes if outcome.revisions > 0]
        return round(sum(acted) / len(acted), 2) if acted else 0.0

    @property
    def accuracy(self) -> float:
        """Fraction of scenarios with the correct outcome."""
        return round(self.correct / self.total, 2) if self.total else 0.0


def _run_scenario(scenario: Scenario, artifacts_dir: str) -> RunResult:
    """Run one scenario on a fresh bus + its canned FakeLLM."""
    bus = InMemoryBus()
    llm = scenario.llm_factory()
    orchestrator = Orchestrator(
        bus,
        Triage(bus, llm),
        Reproducer(bus, llm),
        Planner(bus, llm),
        Coder(bus, llm),
        SecurityReviewer(bus),
        Reviewer(bus, llm),
        artifacts_dir=artifacts_dir,
    )
    return orchestrator.run(scenario.issue())


def run_benchmark(
    scenarios: list[Scenario] | None = None, artifacts_dir: str = "artifacts/bench"
) -> BenchmarkReport:
    """Run every scenario and collect a :class:`BenchmarkReport`."""
    scenarios = scenarios if scenarios is not None else SCENARIOS
    outcomes: list[ScenarioOutcome] = []
    for scenario in scenarios:
        result = _run_scenario(scenario, artifacts_dir)
        outcomes.append(
            ScenarioOutcome(
                name=scenario.name,
                expected_merge=scenario.expected_merge,
                merged=result.merged,
                correct=result.merged == scenario.expected_merge,
                revisions=result.revisions,
                verifier_rejections=result.verifier_rejections,
                regressions_caught=result.regressions_caught,
                security_blocks=result.security_blocks,
                note=scenario.note,
            )
        )
    return BenchmarkReport(outcomes)


def _summary_rows(report: BenchmarkReport) -> list[str]:
    """Build the markdown rows for the summary metrics table."""
    accuracy_pct = int(report.accuracy * 100)
    return [
        f"| scenarios | {report.total} |",
        f"| correct outcomes | {report.correct}/{report.total} ({accuracy_pct}%) |",
        f"| fixes shipped (merged) | {report.merged} |",
        f"| bad patches caught by Verifier | {report.bad_patches_caught} |",
        f"| regressions prevented | {report.regressions_prevented} |",
        f"| security issues caught | {report.security_issues_caught} |",
        f"| non-actionable filtered | {report.nonactionable_filtered} |",
        f"| avg revisions to merge | {report.avg_revisions} |",
    ]


def _scenario_row(outcome: ScenarioOutcome) -> str:
    """Build one markdown row for the per-scenario table."""
    cells = [
        outcome.name,
        str(outcome.expected_merge),
        str(outcome.merged),
        "yes" if outcome.correct else "NO",
        str(outcome.revisions),
        str(outcome.verifier_rejections),
        str(outcome.regressions_caught),
        str(outcome.security_blocks),
        outcome.note,
    ]
    return "| " + " | ".join(cells) + " |"


def render_report(report: BenchmarkReport) -> str:
    """Render the benchmark report as Markdown."""
    header = (
        "| scenario | expected | merged | correct | revisions | "
        "verifier_rej | regressions | security_blocks | note |"
    )
    divider = "|" + "---|" * 9
    rows = [_scenario_row(outcome) for outcome in report.outcomes]
    return "\n".join(
        [
            "# TrustBand benchmark",
            "",
            "Offline, deterministic run across all bundled showcase scenarios "
            "(`uv run trustband bench`).",
            "",
            "## Summary",
            "| metric | value |",
            "|---|---|",
            *_summary_rows(report),
            "",
            "## Per scenario",
            header,
            divider,
            *rows,
            "",
        ]
    )
