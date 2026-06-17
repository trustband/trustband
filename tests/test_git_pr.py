"""P1 — git_pr materializes a real branch + commit on an isolated clone."""

import subprocess
from pathlib import Path

from trustband.contracts import FileChange, Patch, TextEdit
from trustband.git_pr import materialize_pr

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"


def test_materialize_pr_creates_branch_with_fix(tmp_path):
    patch = Patch(issue_id="X", changes=[FileChange(path="pricing.py", new_content="# fixed\n")])
    clone = materialize_pr(FIXTURE, [patch], "fix: X", str(tmp_path / "clone"))

    assert clone is not None
    assert (clone / "pricing.py").read_text() == "# fixed\n"
    branches = subprocess.run(
        ["git", "branch"], cwd=clone, capture_output=True, text=True
    ).stdout
    assert "trustband/fix" in branches
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=clone, capture_output=True, text=True
    ).stdout
    assert "fix: X" in log

    # The source fixture was never turned into a git repo (isolated clone only).
    assert not (FIXTURE / ".git").exists()


def test_materialize_pr_applies_edit_patch(tmp_path):
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
    clone = materialize_pr(FIXTURE, [patch], "fix: X", str(tmp_path / "clone"))

    assert clone is not None
    text = (clone / "pricing.py").read_text()
    assert "return _subtotal(items) * (1 - discount_rate)" in text
