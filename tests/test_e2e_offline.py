"""Phase 3.3 + 3.4 — the offline pipeline produces a trustworthy PR end to end.

This is the "system works" gate: fully offline, free, and deterministic.
"""

from pathlib import Path

from trustband.agents import Coder, Planner, Reviewer
from trustband.bus import InMemoryBus
from trustband.cli import main
from trustband.contracts import Issue
from trustband.demo import make_demo_fake_llm
from trustband.orchestrator import Orchestrator

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
    orchestrator = Orchestrator(bus, Planner(bus, llm), Coder(bus, llm), Reviewer(bus, llm))

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
    assert {"planner", "coder", "verifier", "reviewer"}.issubset(senders)


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
