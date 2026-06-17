"""Phase 3.3 + 3.4 — the offline pipeline produces a trustworthy PR end to end.

This is the "system works" gate: fully offline, free, and deterministic.
"""

import json
from pathlib import Path

from trustband.agents import Coder, Planner, Reproducer, Reviewer, SecurityReviewer, Triage
from trustband.bus import InMemoryBus
from trustband.cli import main
from trustband.contracts import Issue
from trustband.demo import make_demo_fake_llm
from trustband.orchestrator import Orchestrator
from trustband.scenarios import get_scenario

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def _issue() -> Issue:
    return Issue(
        id="BUG-1",
        title="percentage discount",
        repo_path=str(FIXTURE),
        failing_test="test_percentage_discount",
    )


def test_e2e_offline_produces_trustworthy_pr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bus = InMemoryBus()
    llm = make_demo_fake_llm()
    orchestrator = Orchestrator(
        bus,
        Triage(bus, llm),
        Reproducer(bus, llm),
        Planner(bus, llm),
        Coder(bus, llm),
        SecurityReviewer(bus),
        Reviewer(bus, llm),
    )

    result = orchestrator.run(_issue())

    assert result.verdict.trustworthy
    assert result.merged
    assert result.decision is not None and result.decision.approved

    pr_path = tmp_path / "artifacts" / "BUG-1" / "PR.md"
    assert pr_path.exists()
    text = pr_path.read_text()
    assert "TRUSTWORTHY" in text.upper()
    assert "1 - discount_rate" in text

    senders = {message.sender for message in bus.history()}
    expected = {"triage", "reproducer", "planner", "coder", "verifier", "security", "reviewer"}
    assert expected.issubset(senders)


def test_cli_run_offline_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "run",
            "--repo",
            str(FIXTURE),
            "--issue",
            str(FIXTURE / "ISSUE.md"),
            "--bus",
            "memory",
            "--llm",
            "fake",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "TRUSTWORTHY" in out.upper()
    assert "Merged: True" in out


def test_cli_run_json_outputs_machine_readable_result(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "run",
            "--repo",
            str(FIXTURE),
            "--issue",
            str(FIXTURE / "ISSUE.md"),
            "--bus",
            "memory",
            "--llm",
            "fake",
            "--json",
        ]
    )
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["issue_id"] == "BUG-1"
    assert payload["merged"] is True
    assert payload["verdict"]["verdict"] == "trustworthy"
    assert "Band room transcript" not in out


def test_orchestrator_reuses_baseline_across_revisions(monkeypatch, tmp_path):
    import trustband.orchestrator as orchestrator_module

    scenario = get_scenario("regression_trap")
    bus = InMemoryBus()
    llm = scenario.llm_factory()
    calls = {"baseline": 0, "verify": 0}
    real_run_pytest = orchestrator_module.run_pytest
    real_verify = orchestrator_module.verify

    def counting_run_pytest(*args, **kwargs):
        calls["baseline"] += 1
        return real_run_pytest(*args, **kwargs)

    def counting_verify(*args, **kwargs):
        calls["verify"] += 1
        assert kwargs.get("baseline") is not None
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(orchestrator_module, "run_pytest", counting_run_pytest)
    monkeypatch.setattr(orchestrator_module, "verify", counting_verify)
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

    result = orchestrator.run(scenario.issue())

    assert result.revisions == 2
    assert calls == {"baseline": 1, "verify": 2}
