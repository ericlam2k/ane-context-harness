"""Tests for token estimation."""
from __future__ import annotations

from src.ane_context_harness import tokens


def test_count_nonempty():
    n = tokens.count("def foo(): return 1")
    assert n > 0


def test_count_empty():
    assert tokens.count("") == 0
    assert tokens.count(None or "") == 0


def test_count_monotonic_in_length():
    a = tokens.count("hello world")
    b = tokens.count("hello world " * 50)
    assert b > a


def test_estimate_matches_count():
    text = "def add(a, b):\n    return a + b\n"
    assert tokens.estimate(text) == tokens.count(text)


def test_backend_label():
    assert tokens.BACKEND in ("tiktoken-cl100k_base", "regex-heuristic")
