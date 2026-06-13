"""Canned FakeLLM wiring for the bundled discount-bug fixture demo.

This couples to ``fixtures/buggy_app`` on purpose: it lets the offline pipeline
(``--llm fake``) reproduce a correct, deterministic fix without any API calls.
Real repositories use ``--llm real`` (Phase 4).
"""

from __future__ import annotations

from trustband.contracts import FileChange, FixPlan, Patch, ReviewReport, ReviewStatus
from trustband.llm import FakeLLM

CORRECT_PRICING = '''"""Tiny pricing module used as the TrustBand demo target.

It contains a deliberate bug in ``order_total`` (see ISSUE.md): a percentage
discount is applied as a flat subtraction instead of a proportion.
"""


def _subtotal(items):
    """Sum unit_price * quantity over a list of (unit_price, quantity) pairs."""
    return sum(unit_price * quantity for unit_price, quantity in items)


def order_total(items, discount_rate=0.0):
    """Return the order total after applying a percentage discount.

    Args:
        items: list of (unit_price, quantity) pairs.
        discount_rate: fraction in [0, 1]; e.g. 0.1 means 10% off.
    """
    return _subtotal(items) * (1 - discount_rate)


def cart_summary(items):
    """Return a small summary dict (count + subtotal) for a cart."""
    return {"count": len(items), "subtotal": _subtotal(items)}
'''


def make_demo_fake_llm() -> FakeLLM:
    """Build a FakeLLM that fixes the bundled discount bug deterministically."""
    plan = FixPlan(
        issue_id="BUG-1",
        root_cause=(
            "order_total subtracts discount_rate as a flat amount instead of "
            "applying it as a percentage of the subtotal"
        ),
        files_to_touch=["pricing.py"],
        acceptance_criteria=[
            "a 10% discount on a $100 item returns 90.0",
            "no-discount and cart_summary behavior is unchanged",
        ],
        test_strategy="run test_pricing.py; test_percentage_discount must pass with no regressions",
        notes="keep _subtotal semantics intact (quantity matters)",
    )
    patch = Patch(
        issue_id="BUG-1",
        summary="apply the discount as a percentage of the subtotal",
        changes=[FileChange(path="pricing.py", new_content=CORRECT_PRICING)],
    )
    review = ReviewReport(
        issue_id="BUG-1",
        status=ReviewStatus.APPROVE,
        summary="minimal, on-point fix; covered by the existing suite and verified green",
    )
    return FakeLLM(
        {
            "plan": plan.model_dump_json(),
            "code": patch.model_dump_json(),
            "review": review.model_dump_json(),
        }
    )
