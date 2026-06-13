"""Run a target repo's pytest suite in an isolated copy and parse the outcome.

The repo is copied to a temp dir outside the host project tree so the target's
tests are collected with their own (empty) config, never the host project's
pytest settings. An optional patch is applied to the copy before running, which
lets the Verifier compare a baseline run against a post-patch run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from trustband.contracts import Patch, SuiteResult

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".venv", ".pytest_cache")


def _nodeid(testcase: ET.Element) -> str:
    """Build a stable identifier from a junit ``<testcase>`` element."""
    classname = testcase.get("classname") or ""
    name = testcase.get("name") or ""
    return f"{classname}::{name}" if classname else name


def _parse_junit(xml_path: Path) -> dict[str, list[str]]:
    """Parse a junit-xml report into passed/failed/errors/skipped node id lists."""
    tree = ET.parse(xml_path)
    buckets: dict[str, list[str]] = {"passed": [], "failed": [], "errors": [], "skipped": []}
    for testcase in tree.getroot().iter("testcase"):
        tags = {child.tag for child in testcase}
        nodeid = _nodeid(testcase)
        if "failure" in tags:
            buckets["failed"].append(nodeid)
        elif "error" in tags:
            buckets["errors"].append(nodeid)
        elif "skipped" in tags:
            buckets["skipped"].append(nodeid)
        else:
            buckets["passed"].append(nodeid)
    return buckets


def _apply_patch(work: Path, patch: Patch) -> None:
    """Write each file change into the working copy (full-content replacement)."""
    for change in patch.changes:
        target = work / change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new_content)


def run_pytest(
    repo_dir: str | Path, patch: Patch | None = None, timeout: float = 120.0
) -> SuiteResult:
    """Copy ``repo_dir`` to a temp dir, optionally apply ``patch``, run pytest, parse results.

    Args:
        repo_dir: path to the target repository.
        patch: optional patch to apply to the copy before running.
        timeout: seconds before the pytest subprocess is abandoned.

    Returns:
        A :class:`SuiteResult` describing the run.
    """
    source = Path(repo_dir)
    with tempfile.TemporaryDirectory(prefix="trustband-run-") as td:
        work = Path(td) / "repo"
        shutil.copytree(source, work, ignore=_IGNORE)
        if patch is not None:
            _apply_patch(work, patch)
        xml_path = Path(td) / "report.xml"
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                    "--junit-xml",
                    str(xml_path),
                    str(work),
                ],
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return SuiteResult(returncode=-1, errors=["<timeout>"], duration_s=timeout)
        duration = time.perf_counter() - started
        if not xml_path.exists():
            return SuiteResult(
                returncode=proc.returncode, errors=["<no-report>"], duration_s=duration
            )
        buckets = _parse_junit(xml_path)
        return SuiteResult(
            passed=buckets["passed"],
            failed=buckets["failed"],
            errors=buckets["errors"],
            skipped=buckets["skipped"],
            returncode=proc.returncode,
            duration_s=duration,
        )
