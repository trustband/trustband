"""Phase 6.3 — each showcase scenario runs end to end with the expected outcome."""

import pytest

from trustband.agents import Coder, Planner, Reproducer, Reviewer, SecurityReviewer, Triage
from trustband.bus import InMemoryBus
from trustband.orchestrator import Orchestrator, RunResult
from trustband.scenarios import SCENARIOS, Scenario, get_scenario


def _run(scenario: Scenario, tmp_path) -> RunResult:
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
        artifacts_dir=str(tmp_path / "artifacts"),
    )
    return orchestrator.run(scenario.issue())


@pytest.mark.parametrize("name", [scenario.name for scenario in SCENARIOS])
def test_scenario_outcome_matches_expected(name, tmp_path):
    scenario = get_scenario(name)
    result = _run(scenario, tmp_path)
    assert result.merged is scenario.expected_merge


def test_regression_trap_loops_to_a_clean_fix(tmp_path):
    result = _run(get_scenario("regression_trap"), tmp_path)
    assert result.merged is True
    assert result.revisions == 2
    assert result.verifier_rejections >= 1
    assert result.regressions_caught >= 1


def test_risky_fix_is_blocked_by_security_then_cleaned(tmp_path):
    result = _run(get_scenario("risky_fix"), tmp_path)
    assert result.merged is True
    assert result.revisions == 2
    assert result.security_blocks >= 1
    # round 1 passed the tests — security, not the verifier, is what caught it
    assert result.verifier_rejections == 0


def test_no_test_scenario_authors_a_failing_test(tmp_path):
    result = _run(get_scenario("no_test"), tmp_path)
    assert result.merged is True
    assert result.repro is not None
    assert result.repro.authored_test is not None  # the Reproducer wrote the test


def test_non_actionable_stops_at_triage(tmp_path):
    result = _run(get_scenario("non_actionable"), tmp_path)
    assert result.merged is False
    assert result.actionable is False
    assert result.plan is None


def test_discount_merges_in_one_revision(tmp_path):
    result = _run(get_scenario("discount"), tmp_path)
    assert result.merged is True
    assert result.revisions == 1
    assert result.security is not None and result.security.clean
