"""Phase 6.1 — Triage and SecurityReviewer agents + their contracts."""

import importlib.util

import pytest

from trustband.agents import SecurityReviewer, Triage
from trustband.bus import InMemoryBus
from trustband.contracts import (
    FileChange,
    Finding,
    Issue,
    IssueCategory,
    Patch,
    SecurityReport,
    Severity,
    TextEdit,
    TriageReport,
)
from trustband.llm import FakeLLM


def _issue() -> Issue:
    return Issue(
        id="BUG-1",
        title="discount",
        repo_path="fixtures/buggy_app",
        failing_test="test_percentage_discount",
    )


def _patch(content: str) -> Patch:
    return Patch(issue_id="BUG-1", changes=[FileChange(path="m.py", new_content=content)])


def test_triage_report_round_trip():
    report = TriageReport(
        issue_id="X", actionable=True, category=IssueCategory.BUG, target_tests=["t"]
    )
    assert TriageReport.model_validate(report.model_dump()) == report


def test_security_report_clean_property():
    clean = SecurityReport(issue_id="X")
    risky = SecurityReport(
        issue_id="X", findings=[Finding(severity=Severity.CRITICAL, message="eval")]
    )
    assert clean.clean is True
    assert risky.clean is False


def test_triage_marks_actionable_and_fills_target():
    triage_json = TriageReport(issue_id="X", actionable=True).model_dump_json()
    bus = InMemoryBus()
    report = Triage(bus, FakeLLM({"triage": triage_json})).run(_issue())
    assert report.actionable
    assert report.issue_id == "BUG-1"
    assert "test_percentage_discount" in report.target_tests
    assert bus.get_context("TriageReport") is not None


def test_triage_can_reject_non_actionable():
    triage_json = TriageReport(
        issue_id="X", actionable=False, category=IssueCategory.QUESTION
    ).model_dump_json()
    bus = InMemoryBus()
    report = Triage(bus, FakeLLM({"triage": triage_json})).run(
        Issue(id="Q1", title="how do I use this", repo_path="x")
    )
    assert report.actionable is False


def test_security_flags_eval():
    bus = InMemoryBus()
    report = SecurityReviewer(bus).review(_issue(), _patch("def f(s):\n    return eval(s)\n"))
    assert report.clean is False
    assert any("eval" in finding.message for finding in report.findings)
    assert bus.get_context("SecurityReport") is not None


def test_security_flags_hardcoded_secret():
    bus = InMemoryBus()
    report = SecurityReviewer(bus).review(_issue(), _patch('API_KEY = "sk-secret-123"\n'))
    assert report.clean is False


def test_security_flags_risky_text_edit():
    patch = Patch(
        issue_id="BUG-1",
        edits=[TextEdit(path="m.py", find="return x", replace="return eval(x)")],
    )
    report = SecurityReviewer(InMemoryBus()).review(_issue(), patch)
    assert report.clean is False
    assert report.findings[0].path == "m.py"


def test_security_clean_on_safe_patch():
    bus = InMemoryBus()
    report = SecurityReviewer(bus).review(_issue(), _patch("def f(s):\n    return int(s)\n"))
    assert report.clean is True
    assert report.findings == []


@pytest.mark.skipif(importlib.util.find_spec("bandit") is None, reason="bandit not installed")
def test_security_bandit_adds_findings_beyond_regex():
    content = "import hashlib\n\n\ndef weak(data):\n    return hashlib.md5(data).hexdigest()\n"
    regex_only = SecurityReviewer(InMemoryBus()).review(_issue(), _patch(content))
    with_bandit = SecurityReviewer(InMemoryBus(), use_bandit=True).review(_issue(), _patch(content))
    assert regex_only.findings == []  # the regex heuristic misses a weak hash
    assert len(with_bandit.findings) > 0  # bandit (real SAST) catches it
