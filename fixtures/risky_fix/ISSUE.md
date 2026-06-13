# Bug: add_one() crashes on numeric strings

`add_one("41")` raises TypeError instead of returning 42.

- **Failing test:** `test_add_one_str` (test_calc.py)
- **Expected:** `add_one("41")` returns `42`; `add_one(5)` still returns `6`.
- **Note:** parse the value safely — do not use eval().
