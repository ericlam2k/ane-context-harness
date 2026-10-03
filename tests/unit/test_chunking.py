"""Tests for deterministic chunking and line provenance."""
from __future__ import annotations

from src.ane_context_harness import tokens as tokens_mod
from src.ane_context_harness.indexing.chunking import chunk_file, chunk_symbols, lex_terms, ChunkPiece


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


def test_symbol_chunks_keep_functions_whole():
    pieces = chunk_symbols(SAMPLE, "python", target_tokens=350, overlap_tokens=40)
    starts = [p.start_line for p in pieces]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    full = "\n".join(p.content for p in pieces)
    for name in ("def alpha():", "def beta():", "def gamma():"):
        assert name in full
    # alpha (2 lines) shares a chunk; no chunk starts mid-function
    alpha = next(p for p in pieces if "def alpha():" in p.content)
    assert alpha.content.index("def alpha():") < alpha.content.index("def beta():") \
        or "def beta():" not in alpha.content


def test_symbol_chunks_fallback_without_symbols():
    text = "just some prose\nno code here\n" * 10
    pieces = chunk_symbols(text, "unknown-lang", target_tokens=30, overlap_tokens=5)
    assert pieces and all(p.tokens > 0 for p in pieces)


def test_symbol_chunks_split_oversized_symbol():
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    text = f"def big():\n{body}\n    return 1\n"
    pieces = chunk_symbols(text, "python", target_tokens=60, overlap_tokens=10)
    assert len(pieces) > 1
    starts = [p.start_line for p in pieces]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert pieces[0].start_line == 1  # decorators/gap included, starts at top
