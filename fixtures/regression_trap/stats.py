"""Stats helpers (TrustBand demo fixture: mean() divides by zero on empty input)."""


def _total(numbers):
    """Sum the numbers."""
    return sum(numbers)


def mean(numbers):
    """Return the arithmetic mean of the numbers."""
    return _total(numbers) / len(numbers)


def summary(numbers):
    """Return count and total."""
    return {"count": len(numbers), "total": _total(numbers)}
