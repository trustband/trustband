"""Materialize a real git branch + commit for an approved fix — safely, on a clone.

This never touches the target repo. It copies the repo to an isolated location,
makes a baseline commit, then applies the patches on a new branch and commits
them. The result is a genuine, PR-ready git branch (``git diff main..trustband/fix``
shows the change; run ``gh pr create`` from it) with zero risk to the source tree.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from trustband.contracts import Patch

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".venv", ".pytest_cache")


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in ``cwd``, raising on failure."""
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _commit(dest: Path, message: str) -> None:
    """Stage everything and commit with a fixed bot identity (no global git config needed)."""
    _git(["add", "-A"], dest)
    _git(
        ["-c", "user.email=bot@trustband.local", "-c", "user.name=TrustBand",
         "commit", "-q", "-m", message],
        dest,
    )


def materialize_pr(
    repo_path: str | Path,
    patches: Iterable[Patch],
    message: str,
    out_dir: str | Path,
    branch: str = "trustband/fix",
) -> Path | None:
    """Create a branch with the patches applied, in an isolated copy of the repo.

    Returns the path to the branched clone, or None if git is unavailable.
    """
    source = Path(repo_path)
    dest = Path(out_dir)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=_IGNORE)
    try:
        _git(["init", "-q", "-b", "main"], dest)
        _commit(dest, "baseline")
        _git(["checkout", "-q", "-b", branch], dest)
        for patch in patches:
            for change in patch.changes:
                target = dest / change.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.new_content)
        _commit(dest, message)
    except (OSError, subprocess.SubprocessError):
        return None
    return dest
