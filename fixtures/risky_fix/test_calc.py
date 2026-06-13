"""Tests for calc. ``test_add_one_str`` fails until string input is parsed."""

from calc import add_one


def test_add_one_int():
    assert add_one(5) == 6


def test_add_one_str():
    assert add_one("41") == 42
