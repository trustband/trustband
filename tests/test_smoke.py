"""Smoke test: the package imports and exposes a version string."""

import trustband
from trustband.cli import main


def test_version_present() -> None:
    """The package exposes a non-empty semantic version."""
    assert trustband.__version__


def test_cli_stub_runs() -> None:
    """The CLI stub returns a success exit code."""
    assert main([]) == 0
