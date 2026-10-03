"""Unit: query normalization + expansion + fusion (ranking only)."""
from __future__ import annotations

import pytest

from src.ane_context_harness.retrieval.queries import (
    expand_queries,
    full_identifiers,
    fuse_scores,
    usable_terms,
)


def test_usable_terms_drops_noise():
    terms = usable_terms("Fix it to arm the c5 unit with max speed")
    assert "to" not in terms and "arm" not in terms and "max" not in terms
    assert "speed" in terms and "unit" in terms


def test_full_identifiers_kept_whole():
    ids = full_identifiers("Implement runtime.max_concurrent_agents gating now")
    assert "max_concurrent_agents" in ids
    assert "runtime" not in ids  # no underscore/camel: not an identifier form


def test_expand_queries_always_three():
    qs = expand_queries("hi")
    assert len(qs) == 3 and all(qs)
    qs = expand_queries("Implement threshold gating with reranker")
    assert qs[0].startswith("Implement")
    assert "reranker" in qs[1]
    assert qs[2] == qs[0] or "_" in qs[2] or any(
        c.isupper() for c in qs[2])


def test_fuse_max_and_sum():
    per = [[0.2, 0.9], [0.8, 0.1], [0.5, 0.5]]
    assert fuse_scores(per, "max") == [0.8, 0.9]
    assert fuse_scores(per, "sum") == [1.5, 1.5]
    with pytest.raises(ValueError):
        fuse_scores(per, "avg")
    assert fuse_scores([], "max") == []
