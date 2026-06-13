"""Phase 2.2 — the Verifier passes a good patch and rejects a regressing one.

This is the proof of the differentiator: a patch that makes the target test pass
is still REJECTED if it silently breaks another test. The bad patch below fixes
``order_total`` but "refactors" ``_subtotal`` to drop the quantity, which keeps
the target green while breaking the no-discount and cart-summary tests.
"""

from pathlib import Path

from trustband.contracts import FileChange, Issue, Patch, Verdict
from trustband.verifier import verify

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
