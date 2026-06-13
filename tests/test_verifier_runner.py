"""Phase 2.1 — the runner executes a target repo in isolation and parses results."""

from pathlib import Path

from trustband.runner import run_pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def test_runner_detects_failing_target():
    result = run_pytest(FIXTURE)
    assert any("test_percentage_discount" in nid for nid in result.failed)
    assert len(result.passed) == 3
    assert result.all_green is False
    assert result.returncode != 0
