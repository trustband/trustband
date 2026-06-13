# Bug: mean() divides by zero on an empty list

`mean([])` raises ZeroDivisionError instead of returning 0.

- **Failing test:** `test_mean_empty_is_zero` (test_stats.py)
- **Expected:** `mean([])` returns `0`.
- **Constraint:** `_total` must keep summing all values, duplicates included.
