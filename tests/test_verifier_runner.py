"""Phase 2.1 — the runner executes a target repo in isolation and parses results."""

from pathlib import Path

from trustband.contracts import DeleteFile, FileChange, Patch, TextEdit
from trustband.runner import run_pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def test_runner_detects_failing_target():
    result = run_pytest(FIXTURE)
    assert any("test_percentage_discount" in nid for nid in result.failed)
    assert len(result.passed) == 3
    assert result.all_green is False
    assert result.returncode != 0


def test_runner_can_select_short_test_name():
    result = run_pytest(FIXTURE, targets=["test_percentage_discount"])
    assert any("test_percentage_discount" in nid for nid in result.failed)
    assert len(result.passed) == 0


def test_runner_can_select_junit_style_nodeid():
    result = run_pytest(FIXTURE, targets=["test_pricing::test_percentage_discount"])
    assert any("test_percentage_discount" in nid for nid in result.failed)
    assert len(result.passed) == 0


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


def test_runner_applies_text_edit_patch():
    patch = Patch(
        issue_id="X",
        edits=[
            TextEdit(
                path="pricing.py",
                find="return _subtotal(items) - discount_rate",
                replace="return _subtotal(items) * (1 - discount_rate)",
            )
        ],
    )
    result = run_pytest(FIXTURE, patch)
    assert result.all_green


def test_runner_reports_patch_apply_error():
    patch = Patch(
        issue_id="X",
        edits=[TextEdit(path="pricing.py", find="not in the file", replace="x")],
    )
    result = run_pytest(FIXTURE, patch)
    assert result.returncode == -2
    assert result.errors and "<patch-apply-error>" in result.errors[0]


def test_runner_applies_delete_file_patch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_dead.py").write_text("def test_dead():\n    assert False\n")
    patch = Patch(issue_id="X", deletes=[DeleteFile(path="test_dead.py")])
    result = run_pytest(repo, patch)
    assert result.all_green
