# PR: Bug: percentage discount is computed incorrectly (BUG-1)

> Opened by TrustBand after the Verifier confirmed the fix earns the merge.

## Summary
apply the discount as a percentage of the subtotal

## Root cause
order_total subtracts discount_rate as a flat amount instead of applying it as a percentage of the subtotal

## Verifier evidence — verdict: **TRUSTWORTHY**
- target tests now passing: ['test_pricing::test_percentage_discount']
- regressions (green -> red): none
- suite green after patch: True

### Trajectory assertions
- PASS target_tests_pass — targets=['test_percentage_discount']
- PASS no_regressions — regressions=[]
- PASS suite_green — failed=[]
- PASS patch_nonempty — files=['pricing.py']

## Review — approve
- none

## Diff
```diff
--- a/pricing.py
+++ b/pricing.py
@@ -17,8 +17,7 @@
         items: list of (unit_price, quantity) pairs.
         discount_rate: fraction in [0, 1]; e.g. 0.1 means 10% off.
     """
-    # BUG: subtracts the rate as a flat amount instead of applying a percentage.
-    return _subtotal(items) - discount_rate
+    return _subtotal(items) * (1 - discount_rate)
 
 
 def cart_summary(items):
```
