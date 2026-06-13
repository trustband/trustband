"""Tiny pricing module used as the TrustBand demo target.

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
    # BUG: subtracts the rate as a flat amount instead of applying a percentage.
    return _subtotal(items) - discount_rate


def cart_summary(items):
    """Return a small summary dict (count + subtotal) for a cart."""
    return {"count": len(items), "subtotal": _subtotal(items)}
