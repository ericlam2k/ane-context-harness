"""Tests for the P3.6 >=1,000-pair agreement corpus generation (no torch/ct)."""
from __future__ import annotations

import pytest

from src.ane_context_harness.coreml.agreement import (
    DEFAULT_MIN_PAIRS, generate_agreement_pairs,
)


def test_generates_at_least_1000_deterministic_pairs():
    p1 = generate_agreement_pairs(target=DEFAULT_MIN_PAIRS)
    p2 = generate_agreement_pairs(target=DEFAULT_MIN_PAIRS)
    assert len(p1) == DEFAULT_MIN_PAIRS >= 1000
    assert p1 == p2  # fixed seed + sorted walk => reproducible
    for q, c in p1:
        assert isinstance(q, str) and q
        assert isinstance(c, str) and c


def test_pairs_span_tasks_code_and_paths():
    pairs = generate_agreement_pairs(target=DEFAULT_MIN_PAIRS)
    queries = " ".join(q for q, _ in pairs)
    texts = " ".join(c for _, c in pairs)
    assert "discount" in queries          # benchmark task text
    assert "src/discount.py" in queries   # labelled required path
    assert "def " in texts                # source-file passages
    assert "calculate_discount" in texts  # fixture implementation content


def test_raises_when_target_exceeds_corpus_capacity():
    with pytest.raises(ValueError):
        generate_agreement_pairs(target=10 ** 6)
