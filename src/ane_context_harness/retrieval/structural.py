"""Structural + deterministic score aggregation (symbol, path, dependency,
git-recency, test-pair). ML reranking interface defined but Phase 1 uses the
deterministic backend only.

Backend selection is delegated to the capability profile; this module exposes
`RankBackend`-agnostic initial scoring and a `ScoreBackend` hook for future
Core ML integration without changing API contracts.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..schemas import ChunkScore


@dataclass
class RankRequest:
    task: str
    chunks: list
    explicit_paths: list
    task_language: str = ""


def _terms(text: str) -> set:
    from ..indexing.chunking import lex_terms
    return set(lex_terms(text))


# Symbol-name matches must be evidence, not noise: micro terms ("to", "is",
# "for" from camel splits like roundToCents/profileFor) and test-framework
# words ("test" matching any Test* class) never justify a symbol hit.
SYMBOL_MATCH_MIN_LEN = 4
GENERIC_SYMBOL_TERMS = frozenset({
    "test", "tests", "describe", "expect", "should", "it", "main", "run",
})


def usable_symbol_terms(terms: set) -> set:
    return {t for t in terms
            if len(t) >= SYMBOL_MATCH_MIN_LEN and t not in GENERIC_SYMBOL_TERMS}


def _candidate_symbols(chunk) -> list:
    """Symbols that may explain this chunk's relevance.

    A symbol-scoped chunk speaks for its own symbol only (never a symbol from
    a different region of the file). A file-level chunk (symbol=None — the
    norm for single-chunk files, whose first line sits outside any symbol
    span) falls back to the file's full symbol list from metadata.
    """
    if chunk.symbol:
        return [chunk.symbol]
    return list((chunk.metadata or {}).get("file_symbols") or [])


def matched_symbol_terms(chunk, task_terms: set) -> set:
    """Usable task terms that match this chunk's symbol name(s)."""
    out = set()
    for sym in _candidate_symbols(chunk):
        out |= usable_symbol_terms(_terms(sym) & task_terms)
    return out


def symbol_score(chunk, task_terms: set) -> float:
    """Best symbol match against task terms (own symbol, or file symbols
    for file-level chunks)."""
    best = 0.0
    for sym in _candidate_symbols(chunk):
        usable = usable_symbol_terms(_terms(sym) & task_terms)
        if usable:
            sym_terms = _terms(sym)
            best = max(best, len(usable) /
                       max(1, len(sym_terms | task_terms)))
        elif task_terms and any(len(t) >= SYMBOL_MATCH_MIN_LEN
                                and t not in GENERIC_SYMBOL_TERMS
                                and t in sym.lower() for t in task_terms):
            best = max(best, 0.6)
    return best


def path_score(chunk, explicit_paths: list) -> float:
    if not explicit_paths:
        return 0.0
    norm = chunk.path.replace("\\", "/")
    for ep in explicit_paths:
        ep_n = ep.replace("\\", "/")
        if norm == ep_n:
            return 1.0
        if norm.endswith(ep_n) or ep_n in norm.split("/"):
            return 0.8
    return 0.0


def dependency_score(chunk, task_terms: set) -> float:
    """Best-effort: count imports/references among task terms (requires metadata)."""
    meta = chunk.metadata or {}
    imp = meta.get("imports", [])
    if not imp:
        return 0.0
    hits = sum(1 for i in imp if i in task_terms)
    return hits / max(1, len(set(imp)))


def pair_test_score(chunk) -> float:
    """Pair test files with implementation symbols matching the task."""
    is_test = "/".join(chunk.path.split("/")[-1:]).lower().startswith("test_") or \
              chunk.path.lower().startswith("test/") or chunk.path.endswith(".test.ts") or chunk.path.endswith(".spec.ts")
    if not is_test:
        return 0.0
    if chunk.symbol and chunk.symbol.startswith("test_"):
        return 0.5
    return 0.2


def git_recency_score(chunk) -> float:
    """Git recency as low-weight signal. No shell exec: 0 unless metadata present."""
    meta = chunk.metadata or {}
    recency = meta.get("git_recency_days")
    if recency is None:
        return 0.0
    # more recent (smaller days) => higher score
    return max(0.0, min(1.0, 1.0 / (1.0 + recency * 0.1)))


def aggregate_scores(chunks: list, task: str, explicit_paths: list,
                     weights: dict, bm25_scores: list) -> list:
    """Compute initial_score per chunk using configurable deterministic weights."""
    task_terms = _terms(task)
    out = []
    for idx, c in enumerate(chunks):
        s_lex = bm25_scores[idx] if idx < len(bm25_scores) else 0.0
        s_sym = symbol_score(c, task_terms)
        s_path = path_score(c, explicit_paths)
        s_dep = dependency_score(c, task_terms)
        s_test = pair_test_score(c)
        s_git = git_recency_score(c)
        initial = (
            weights.get("lexical_weight", 0.35) * s_lex
            + weights.get("symbol_weight", 0.25) * s_sym
            + weights.get("path_weight", 0.15) * s_path
            + weights.get("dependency_weight", 0.10) * s_dep
            + weights.get("test_pair_weight", 0.10) * s_test
            + weights.get("git_recency_weight", 0.05) * s_git
        )
        cs = ChunkScore(
            chunk_id=c.chunk_id,
            lexical_score=s_lex,
            symbol_score=s_sym,
            path_score=s_path,
            dependency_score=s_dep,
            test_pair_score=s_test,
            git_recency_score=s_git,
            initial_score=initial,
        )
        out.append(cs)
    return out
