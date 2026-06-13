"""Tests for the pricing module.

``test_percentage_discount`` fails until the bug in ``order_total`` is fixed;
the other three guard against regressions a careless fix might introduce.
"""

from pricing import cart_summary, order_total


def test_subtotal_no_discount():
    assert order_total([(10, 2), (5, 1)]) == 25


def test_percentage_discount():
    # 10% off a single $100 item should be 90.0, not 99.9.
    assert order_total([(100, 1)], 0.1) == 90.0


def test_empty_order():
    assert order_total([]) == 0


def test_cart_summary():
    assert cart_summary([(10, 2), (5, 1)]) == {"count": 2, "subtotal": 25}
