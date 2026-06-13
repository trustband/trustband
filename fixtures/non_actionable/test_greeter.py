"""Tests for greeter (all green; the bundled issue is a feature request, not a bug)."""

from greeter import greet


def test_greet():
    assert greet("world") == "Hello, world!"
