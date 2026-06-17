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
from dataclasses import dataclass, field
from pathlib import Path

from trustband.contracts import Patch, SuiteResult
from trustband.patching import PatchApplyError, apply_patch

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".venv", ".pytest_cache")


def _pytest_selection(work: Path, targets: list[str] | None) -> list[str]:
    """Build pytest selection args from node ids, paths, or short test names."""
    if not targets:
        return [str(work)]
    path_targets: list[str] = []
    name_targets: list[str] = []
    for target in targets:
        if "::" in target:
            module, _, test_name = target.partition("::")
            if "/" not in module and not module.endswith(".py"):
                path_targets.append(f"{module}.py::{test_name}")
            else:
                path_targets.append(target)
        elif "/" in target or target.endswith(".py"):
            path_targets.append(target)
        else:
            name_targets.append(target)
    args = path_targets or [str(work)]
    if name_targets:
        expression = " or ".join(name_targets)
        args.extend(["-k", expression])
    return args


def _nodeid(testcase: ET.Element) -> str:
    """Build a stable identifier from a junit ``<testcase>`` element."""
    classname = testcase.get("classname") or ""
    name = testcase.get("name") or ""
    return f"{classname}::{name}" if classname else name


@dataclass
class ParsedJunit:
    """Parsed junit node buckets and failure/error details."""

    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failure_details: dict[str, str] = field(default_factory=dict)
    error_details: dict[str, str] = field(default_factory=dict)


def _parse_junit(xml_path: Path) -> ParsedJunit:
    """Parse a junit-xml report into node ids and failure/error details."""
    tree = ET.parse(xml_path)
    buckets = ParsedJunit()
    for testcase in tree.getroot().iter("testcase"):
        nodeid = _nodeid(testcase)
        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")
        if failure is not None:
            buckets.failed.append(nodeid)
            detail = failure.get("message") or failure.text or ""
            buckets.failure_details[nodeid] = detail[:500]
        elif error is not None:
            buckets.errors.append(nodeid)
            detail = error.get("message") or error.text or ""
            buckets.error_details[nodeid] = detail[:500]
        elif skipped is not None:
            buckets.skipped.append(nodeid)
        else:
            buckets.passed.append(nodeid)
    return buckets


def run_pytest(
    repo_dir: str | Path,
    patch: Patch | None = None,
    *,
    scaffold: Patch | None = None,
    targets: list[str] | None = None,
    timeout: float = 120.0,
) -> SuiteResult:
    """Copy ``repo_dir`` to a temp dir, apply patches, run pytest, parse results.

    Args:
        repo_dir: path to the target repository.
        patch: optional fix patch to apply to the copy before running.
        scaffold: optional patch applied before ``patch`` on every run (e.g. an
            authored failing test the Reproducer added).
        targets: optional pytest node ids, files, or test names to run.
        timeout: seconds before the pytest subprocess is abandoned.

    Returns:
        A :class:`SuiteResult` describing the run.
    """
    source = Path(repo_dir)
    with tempfile.TemporaryDirectory(prefix="trustband-run-") as td:
        work = Path(td) / "repo"
        shutil.copytree(source, work, ignore=_IGNORE)
        try:
            for extra in (scaffold, patch):
                if extra is not None:
                    apply_patch(work, extra)
        except PatchApplyError as exc:
            return SuiteResult(returncode=-2, errors=[f"<patch-apply-error>: {exc}"])
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
                    *_pytest_selection(work, targets),
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
            passed=buckets.passed,
            failed=buckets.failed,
            errors=buckets.errors,
            skipped=buckets.skipped,
            failure_details=buckets.failure_details,
            error_details=buckets.error_details,
            returncode=proc.returncode,
            duration_s=duration,
        )
