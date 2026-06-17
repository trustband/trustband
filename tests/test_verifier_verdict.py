"""Phase 2.2 — the Verifier passes a good patch and rejects a regressing one.

This is the proof of the differentiator: a patch that makes the target test pass
is still REJECTED if it silently breaks another test. The bad patch below fixes
``order_total`` but "refactors" ``_subtotal`` to drop the quantity, which keeps
the target green while breaking the no-discount and cart-summary tests.
"""

from pathlib import Path

from trustband.contracts import FileChange, Issue, Patch, TextEdit, Verdict
from trustband.verifier import _matches, verify

FIXTURE = Path(__file__).parent.parent / "fixtures" / "buggy_app"

GOOD_PRICING = '''def _subtotal(items):
    return sum(unit_price * quantity for unit_price, quantity in items)


def order_total(items, discount_rate=0.0):
    return _subtotal(items) * (1 - discount_rate)


def cart_summary(items):
    return {"count": len(items), "subtotal": _subtotal(items)}
'''

BAD_PRICING = '''def _subtotal(items):
    return sum(unit_price for unit_price, quantity in items)


def order_total(items, discount_rate=0.0):
    return _subtotal(items) * (1 - discount_rate)


def cart_summary(items):
    return {"count": len(items), "subtotal": _subtotal(items)}
'''


def _issue() -> Issue:
    return Issue(
        id="BUG-1",
        title="percentage discount",
        repo_path=str(FIXTURE),
        failing_test="test_percentage_discount",
    )


def test_matches_is_not_a_loose_substring():
    assert _matches("test_add", "m::test_add") is True
    assert _matches("test_add", "test_add") is True
    assert _matches("test_add", "pkg::test_addition") is False  # no longer over-matches


def test_good_patch_is_trustworthy():
    patch = Patch(
        issue_id="BUG-1",
        summary="apply percentage discount",
        changes=[FileChange(path="pricing.py", new_content=GOOD_PRICING)],
    )
    report = verify(_issue(), patch)
    assert report.verdict == Verdict.TRUSTWORTHY
    assert any("test_percentage_discount" in t for t in report.newly_passing)
    assert report.regressions == []
    assert report.after is not None and report.after.all_green


def test_edit_patch_is_trustworthy():
    patch = Patch(
        issue_id="BUG-1",
        summary="apply percentage discount",
        edits=[
            TextEdit(
                path="pricing.py",
                find="return _subtotal(items) - discount_rate",
                replace="return _subtotal(items) * (1 - discount_rate)",
            )
        ],
    )
    report = verify(_issue(), patch)
    assert report.verdict == Verdict.TRUSTWORTHY
    assert report.touched_files == ["pricing.py"]


def test_bad_edit_patch_is_rejected_as_apply_error():
    patch = Patch(
        issue_id="BUG-1",
        summary="bad edit",
        edits=[TextEdit(path="pricing.py", find="missing target", replace="x")],
    )
    report = verify(_issue(), patch)
    assert report.verdict == Verdict.REJECTED
    assert report.after is not None
    assert report.after.returncode == -2
    assert any("<patch-apply-error>" in reason for reason in report.reasons)


def test_bad_patch_is_rejected_with_named_regression():
    patch = Patch(
        issue_id="BUG-1",
        summary="fix discount but break subtotal",
        changes=[FileChange(path="pricing.py", new_content=BAD_PRICING)],
    )
    report = verify(_issue(), patch)
    assert report.verdict == Verdict.REJECTED
    # The target test does pass under the bad patch ...
    assert any("test_percentage_discount" in t for t in report.newly_passing)
    # ... but the Verifier catches the silent regressions and names them.
    assert report.regressions
    assert any(
        "cart_summary" in r or "subtotal_no_discount" in r for r in report.regressions
    )


def test_affected_scope_falls_back_to_full_suite_for_source_change():
    patch = Patch(
        issue_id="BUG-1",
        summary="apply percentage discount",
        edits=[
            TextEdit(
                path="pricing.py",
                find="return _subtotal(items) - discount_rate",
                replace="return _subtotal(items) * (1 - discount_rate)",
            )
        ],
    )
    report = verify(
        _issue(),
        patch,
        target_tests=["test_percentage_discount"],
        verifier_scope="affected",
    )
    assert report.verdict == Verdict.TRUSTWORTHY
    assert report.scope_mode == "affected"
    assert report.selected_tests == ["test_percentage_discount"]
    assert report.full_suite_run is True
    assert "source file" in report.scope_reason


def test_affected_scope_can_skip_full_suite_for_test_only_patch():
    patch = Patch(
        issue_id="BUG-1",
        changes=[
            FileChange(
                path="test_extra.py",
                new_content="def test_extra_added_by_scaffold():\n    assert True\n",
            )
        ],
    )
    report = verify(
        _issue(),
        patch,
        target_tests=["test_extra_added_by_scaffold"],
        verifier_scope="affected",
    )
    assert report.full_suite_run is False
    assert report.scope_reason == "selected tests passed"
