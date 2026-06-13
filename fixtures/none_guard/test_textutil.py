"""Tests for textutil. ``test_normalize_none_returns_empty`` fails until None is guarded."""

from textutil import normalize


def test_normalize_basic():
    assert normalize("  Hi There ") == "hi there"


def test_normalize_none_returns_empty():
    assert normalize(None) == ""


def test_normalize_already_clean():
    assert normalize("hi") == "hi"
