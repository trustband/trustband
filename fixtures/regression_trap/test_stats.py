"""Tests for stats. ``test_mean_empty_is_zero`` fails until empty input is handled.

``test_total_with_duplicates`` guards ``_total``: a careless fix that dedups regresses it.
"""

from stats import mean, summary


def test_mean_basic():
    assert mean([2, 4]) == 3


def test_mean_empty_is_zero():
    assert mean([]) == 0


def test_total_with_duplicates():
    assert summary([2, 2, 4])["total"] == 8
