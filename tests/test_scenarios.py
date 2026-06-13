"""Phase 6.2 — the scenario registry and fixture baselines."""

import pytest

from trustband.runner import run_pytest
from trustband.scenarios import SCENARIOS, get_scenario


def test_registry_has_expected_scenarios():
    names = {scenario.name for scenario in SCENARIOS}
    assert {
        "discount",
        "none_guard",
        "regression_trap",
        "risky_fix",
        "non_actionable",
    } <= names


@pytest.mark.parametrize("name", ["discount", "none_guard", "regression_trap", "risky_fix"])
def test_actionable_scenarios_start_red(name):
    scenario = get_scenario(name)
    result = run_pytest(scenario.repo)
    assert not result.all_green
    assert scenario.failing_test is not None
    assert any(scenario.failing_test in nodeid for nodeid in result.failed)


def test_non_actionable_repo_is_green():
    scenario = get_scenario("non_actionable")
    assert run_pytest(scenario.repo).all_green


def test_scenario_issue_loads_from_fixture():
    scenario = get_scenario("none_guard")
    issue = scenario.issue()
    assert issue.id == "NONE-1"
    assert issue.repo_path.endswith("none_guard")
    assert "normalize" in issue.description.lower()
