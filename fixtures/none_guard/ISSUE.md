# Bug: normalize() crashes on None input

`normalize(None)` raises AttributeError instead of returning an empty string.

- **Failing test:** `test_normalize_none_returns_empty` (test_textutil.py)
- **Expected:** `normalize(None)` returns `""`.
