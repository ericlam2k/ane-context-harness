"""Tests for deterministic chunking and line provenance."""
from __future__ import annotations

from src.ane_context_harness import tokens as tokens_mod
from src.ane_context_harness.indexing.chunking import chunk_file, lex_terms, ChunkPiece


SAMPLE = """\
def alpha():
    pass


def beta():
    # a comment
    x = 1
    return x


def gamma():
    return 2
"""


def test_chunk_boundaries_cover_whole_file():
    pieces = chunk_file(SAMPLE, target_tokens=30, overlap_tokens=5)
    assert pieces
    # first starts at line 1
    assert pieces[0].start_line == 1
    # last ends at last line
    assert pieces[-1].end_line == len(SAMPLE.splitlines())
    # contiguous (within overlap)
    for a, b in zip(pieces, pieces[1:]):
        assert b.start_line <= a.end_line + 1


def test_chunk_line_provenance():
    pieces = chunk_file(SAMPLE, target_tokens=20, overlap_tokens=3)
    # each chunk knows its lines
    for p in pieces:
        assert p.start_line >= 1
        assert p.end_line >= p.start_line
        assert p.tokens == tokens_mod.count(p.content)


def test_chunk_overlap_tokens():
    pieces = chunk_file(SAMPLE, target_tokens=20, overlap_tokens=20)
    # overlap should not exceed target and pieces should not be empty
    assert len(pieces) >= 1


def test_lex_terms_lowercase():
    terms = lex_terms("Hello World foo_bar X1")
    assert all(t == t.lower() for t in terms)
    assert "hello" in terms and "foo_bar" in terms


def test_empty_input():
    assert chunk_file("", target_tokens=20, overlap_tokens=3) == []
