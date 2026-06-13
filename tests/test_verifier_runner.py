"""Phase 2.1 — the runner executes a target repo in isolation and parses results."""

from pathlib import Path

from trustband.contracts import FileChange, Patch
from trustband.runner import run_pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def test_runner_detects_failing_target():
    result = run_pytest(FIXTURE)
    assert any("test_percentage_discount" in nid for nid in result.failed)
    assert len(result.passed) == 3
    assert result.all_green is False
    assert result.returncode != 0


def test_runner_applies_multi_file_patch_with_new_files():
    # A patch that adds a new module AND a new test importing it — both must land.
    patch = Patch(
        issue_id="X",
        changes=[
            FileChange(path="extra.py", new_content="VALUE = 42\n"),
            FileChange(
                path="test_extra.py",
                new_content=(
                    "from extra import VALUE\n\n\ndef test_extra():\n    assert VALUE == 42\n"
                ),
            ),
        ],
    )
    result = run_pytest(FIXTURE, patch)
    assert any(nid.endswith("::test_extra") for nid in result.passed)
