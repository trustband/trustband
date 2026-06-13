# Bug: percentage discount is computed incorrectly

`order_total(items, discount_rate)` applies the discount as a flat subtraction
instead of a percentage. A 10% discount on a single $100 item returns `99.9`
instead of `90.0`.

- **Failing test:** `test_percentage_discount` (test_pricing.py)
- **Expected:** a `discount_rate` of `0.1` reduces the subtotal by 10%.
- **Constraint:** do not change the behavior of `cart_summary` or the no-discount path.
