"""Tests for BM25 lexical retrieval."""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.lexical import BM25, lexical_scores

from src.ane_context_harness.schemas import RepositoryChunk


def _chunk(cid, text, terms=None):
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=f"p/{cid}.py", language="python",
        start_line=1, end_line=3, symbol=None, content_hash="h",
        estimated_tokens=len(text), lexical_terms=tuple(terms or lex_terms(text)),
        content=text, metadata={},
    )


def test_bm25_scores_descending():
    chunks = [
        _chunk("a", "discount rate calculation apply", lex_terms("discount rate calculation")),
        _chunk("b", "inventory warehouse stock storage"),
        _chunk("c", "discount coupon savings off"),
    ]
    bm = BM25(chunks)
    rows = bm.scores("discount calculation")
    top_id = chunks[rows[0][0]].chunk_id
    assert top_id == "a"  # 'a' has both terms


def test_bm25_empty_query_zero():
    chunks = [_chunk("a", "hello world")]
    bm = BM25(chunks)
    assert bm.score("", 0) == 0.0


def test_lexical_scores_normalized_01():
    chunks = [
        _chunk("a", "discount rate calculation"),
        _chunk("b", "inventory warehouse stock"),
    ]
    lm = lexical_scores(BM25(chunks), "discount calculation")
    assert max(lm) == 1.0
    assert min(lm) <= max(lm)


def test_bm25_term_not_present():
    chunks = [_chunk("a", "hello world")]
    bm = BM25(chunks)
    assert bm.score("nonexistentterm", 0) == 0.0
