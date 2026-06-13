"""Phase 1.1 — contracts round-trip and behave correctly."""

from trustband.contracts import (
    Decision,
    DecisionType,
    FileChange,
    Finding,
    FixPlan,
    Issue,
    Patch,
    ReviewReport,
    ReviewStatus,
    Severity,
    SuiteResult,
    Verdict,
    VerdictReport,
)


def test_issue_round_trip():
    issue = Issue(id="BUG-1", title="discount", repo_path="fixtures/buggy_app", labels=["bug"])
    assert Issue.model_validate(issue.model_dump()) == issue


def test_fixplan_and_patch_round_trip():
    plan = FixPlan(issue_id="BUG-1", root_cause="flat subtraction", files_to_touch=["pricing.py"])
    patch = Patch(
        issue_id="BUG-1",
        summary="apply percentage",
        changes=[FileChange(path="pricing.py", new_content="x = 1\n")],
        revision=2,
    )
    assert FixPlan.model_validate(plan.model_dump()) == plan
    assert Patch.model_validate(patch.model_dump()) == patch
    assert patch.changes[0].path == "pricing.py"


def test_suite_result_all_green():
    green = SuiteResult(passed=["a", "b"])
    red = SuiteResult(passed=["a"], failed=["b"])
    errored = SuiteResult(passed=["a"], errors=["c"])
    assert green.all_green is True
    assert red.all_green is False
    assert errored.all_green is False


def test_verdict_report_trustworthy_property():
    good = VerdictReport(issue_id="BUG-1", verdict=Verdict.TRUSTWORTHY)
    bad = VerdictReport(issue_id="BUG-1", verdict=Verdict.REJECTED, regressions=["test_x"])
    assert good.trustworthy is True
    assert bad.trustworthy is False
    assert VerdictReport.model_validate(bad.model_dump()) == bad


def test_review_report_and_finding():
    report = ReviewReport(
        issue_id="BUG-1",
        status=ReviewStatus.REQUEST_CHANGES,
        findings=[
            Finding(severity=Severity.CRITICAL, message="no test", path="pricing.py", line=3)
        ],
    )
    assert report.approved is False
    assert report.findings[0].severity == Severity.CRITICAL
    assert ReviewReport.model_validate(report.model_dump()) == report


def test_decision_property():
    approve = Decision(issue_id="BUG-1", decision=DecisionType.APPROVE)
    decline = Decision(issue_id="BUG-1", decision=DecisionType.DECLINE, actor="human")
    assert approve.approved is True
    assert decline.approved is False
