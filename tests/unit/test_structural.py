"""Tests for structural score weights and initial_score aggregation."""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.structural import (
    aggregate_scores, symbol_score, path_score, git_recency_score, pair_test_score,
)
from src.ane_context_harness.schemas import RepositoryChunk


def _chunk(cid, path, text, symbol=None, metadata=None):
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=path, language="python",
        start_line=1, end_line=2, symbol=symbol, content_hash="h",
        estimated_tokens=len(text), lexical_terms=tuple(lex_terms(text)),
        content=text, metadata=metadata or {},
    )


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10, "git_recency_weight": 0.05,
}


def test_symbol_score_matches_task_term():
    c = _chunk("1", "src/discount.py", "def calculate_discount(price, rate):", symbol="calculate_discount")
    s = symbol_score(c, {"discount", "rate", "fix"})
    assert s > 0.0


def test_path_score_exact_and_partial():
    c = _chunk("1", "src/discount.py", "x")
    assert path_score(c, ["src/discount.py"]) == 1.0
    assert path_score(c, [".py"]) == 0.8  # path endswith .py


def test_git_recency_zero_without_metadata():
    c = _chunk("1", "src/x.py", "x", metadata={})
    assert git_recency_score(c) == 0.0


def test_pair_test_score_for_test_file():
    c = _chunk("1", "tests/test_discount.py", "x", symbol="test_discount")
    assert pair_test_score(c) > 0.0
    c2 = _chunk("2", "src/discount.py", "x", symbol="calculate_discount")
    assert pair_test_score(c2) == 0.0


def test_aggregate_scores_normalizes_weights():
    chunks = [
        _chunk("1", "src/discount.py", "def calculate_discount", symbol="calculate_discount"),
        _chunk("2", "src/inventory.py", "class Inventory", symbol="Inventory"),
    ]
    bm_scores = [1.0, 0.0]
    # monkeypatch bm25 lexical not used; aggregate takes lexical_scores list
    scores = aggregate_scores(chunks, "discount fix", [], WEIGHTS, bm_scores)
    assert len(scores) == 2
    # discount chunk should score higher than inventory
    assert scores[0].initial_score >= scores[1].initial_score
    assert scores[0].initial_score > 0
