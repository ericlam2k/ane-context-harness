"""Structural + deterministic score aggregation (symbol, path, dependency,
git-recency, test-pair). ML reranking interface defined but Phase 1 uses the
deterministic backend only.

Backend selection is delegated to the capability profile; this module exposes
`RankBackend`-agnostic initial scoring and a `ScoreBackend` hook for future
backends without changing API contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..schemas import ChunkScore
from ..indexing.chunking import lex_terms


@dataclass
class RankRequest:
    task: str
    chunks: list
    explicit_paths: list
    task_language: str = ""


def _terms(text: str) -> set:
    return set(lex_terms(text))


@lru_cache(maxsize=8192)
def _termset(text: str) -> frozenset:
    """Memoized lex terms for small repeated strings (symbol names, paths).

    File-level chunk metadata repeats the same symbol strings for every chunk
    of a file, so small strings ride a cache; large texts (task, chunk
    content) stay uncached at the call sites.
    """
    return frozenset(lex_terms(text or ""))


# Symbol-name matches must be evidence, not noise: micro terms ("to", "is",
# "for" from camel splits like roundToCents/profileFor) and test-framework
# words ("test" matching any Test* class) never justify a symbol hit.
# Prompt-navigation vocabulary ("Name the files and symbols involved") is
# evidence of nothing either — such words pin every file that merely shares
# them.
SYMBOL_MATCH_MIN_LEN = 4
# Loose substring fallback bound (see symbol_score): beyond this many distinct
# query terms the scan is quadratic noise, disabled deterministically.
_SUBSTRING_FALLBACK_MAX_TERMS = 96
GENERIC_SYMBOL_TERMS = frozenset({
    "test", "tests", "describe", "expect", "should", "it", "main", "run",
    "file", "files",
    "name", "names", "naming", "symbol", "symbols",
    "relevant", "relevance", "involved", "involve",
})


def usable_symbol_terms(terms: set) -> set:
    return {t for t in terms
            if len(t) >= SYMBOL_MATCH_MIN_LEN and t not in GENERIC_SYMBOL_TERMS}


# A symbol-name match should be evidence, not noise: on a large repo a vague
# task shares a common word such as "data", "step", or "config" with the
# symbols of dozens of unrelated files, and pinning them all blows the token
# budget. A chunk is therefore pinned by a symbol match only when at least
# one matched term is discriminative — rare enough across the corpus to
# justify retention. Frequency is measured per distinct file over the
# symbols that file declares (metadata.file_symbols), so it reflects how
# many files a match could pin. Small corpora always pass via the absolute
# floor; on large corpora ubiquitous words stop pinning and fall back to
# ordinary score-based selection.
SPECIFICITY_MIN_FILE_FREQ_ABS = 3
SPECIFICITY_MAX_FILE_FREQ_FRACTION = 0.01


def symbol_term_file_frequency(chunks: list) -> tuple[dict, int]:
    """(term -> number of distinct files naming it in a symbol, file count).

    Each path's symbol list is tokenized once (all chunks of a path carry the
    same metadata.file_symbols), so the pass is O(files), not O(chunks).
    """
    per_file: dict[str, set] = {}
    seen: set[str] = set()
    for c in chunks:
        if c.path in seen:
            continue
        seen.add(c.path)
        syms = list((getattr(c, "metadata", None) or {}).get("file_symbols") or [])
        if not syms and getattr(c, "symbol", None):
            syms = [c.symbol]
        terms: set = set()
        for s in syms:
            terms |= usable_symbol_terms(set(lex_terms(s)))
        if terms:
            per_file[c.path] = terms
    freq: dict = {}
    for terms in per_file.values():
        for t in terms:
            freq[t] = freq.get(t, 0) + 1
    return freq, len(per_file)


def is_specific_symbol_term(term: str, freq: dict, n_files: int,
                            min_abs: int = SPECIFICITY_MIN_FILE_FREQ_ABS,
                            max_fraction: float = SPECIFICITY_MAX_FILE_FREQ_FRACTION) -> bool:
    """True when a matched term is rare enough across files to justify a pin.

    A term is specific when it names symbols in at most ``max(min_abs,
    max_fraction * n_files)`` distinct files.
    """
    return freq.get(term, 0) <= max(min_abs, max_fraction * n_files)


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
        out |= usable_symbol_terms(_termset(sym) & task_terms)
    return out


def path_basename_terms(path: str) -> set:
    """Usable terms from a file's basename stem (no extension)."""
    stem = (path or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return set(_termset(stem))


def matched_path_terms(chunk, task_terms: set) -> set:
    """Usable task terms that match this chunk's file basename."""
    return usable_symbol_terms(path_basename_terms(chunk.path) & task_terms)


def path_term_file_frequency(chunks: list) -> tuple[dict, int]:
    """(basename-term -> number of distinct files naming it, file count)."""
    seen: set = set()
    per_file: dict = {}
    for c in chunks:
        if c.path in seen:
            continue
        seen.add(c.path)
        terms = path_basename_terms(c.path)
        if terms:
            per_file[c.path] = terms
    freq: dict = {}
    for terms in per_file.values():
        for t in terms:
            freq[t] = freq.get(t, 0) + 1
    return freq, len(per_file)


def symbol_score(chunk, task_terms: set, *, sym_freq: dict | None = None,
                 n_files: int | None = None) -> float:
    """Best symbol match against task terms (own symbol, or file symbols
    for file-level chunks).

    The loose substring fallback is held to the same standard as pinning: a
    matched term must be discriminative across the corpus. Everyday task words
    such as ``file`` or ``page`` that merely float inside camelCase symbol
    names are NOT evidence.
    """
    gate = sym_freq is not None and n_files is not None
    best = 0.0
    fall_back = gate and len(task_terms) <= _SUBSTRING_FALLBACK_MAX_TERMS
    for sym in _candidate_symbols(chunk):
        usable = usable_symbol_terms(_termset(sym) & task_terms)
        if usable:
            sym_terms = _termset(sym)
            best = max(best, len(usable) /
                       max(1, len(sym_terms | task_terms)))
        elif fall_back:
            # Bounded loose substring fallback, held to the specificity
            # standard: beyond _SUBSTRING_FALLBACK_MAX_TERMS distinct query
            # terms the scan is disabled deterministically.
            sym_l = sym.lower()
            for t in task_terms:
                if (len(t) >= SYMBOL_MATCH_MIN_LEN
                        and t not in GENERIC_SYMBOL_TERMS
                        and t in sym_l
                        and is_specific_symbol_term(t, sym_freq, n_files)):
                    best = max(best, 0.6)
                    break
    return best


def path_score(chunk, explicit_paths: list, task_terms: set | None = None,
               path_freq: dict | None = None, n_files: int | None = None) -> float:
    """Path evidence: explicit request first, then basename-to-task matches.

    A basename match only counts when the term is discriminative across the
    corpus (same specificity rule as pinning); common words such as ``test``
    or ``util`` do not make a path relevant. The score is the fraction of the
    basename's terms that the task names, so ``discount_service.py`` scores
    higher for "fix discount rounding" than ``service.py``.
    """
    norm = chunk.path.replace("\\", "/")
    for ep in explicit_paths or []:
        ep_n = ep.replace("\\", "/")
        if norm == ep_n:
            return 1.0
        if norm.endswith(ep_n) or ep_n in norm.split("/"):
            return 0.8
    if not task_terms:
        return 0.0
    matched = matched_path_terms(chunk, task_terms)
    if not matched:
        return 0.0
    if path_freq is not None and n_files is not None:
        if not any(is_specific_symbol_term(t, path_freq, n_files)
                   for t in matched):
            return 0.0
    base = path_basename_terms(chunk.path)
    return len(matched) / max(1, len(base))


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
    sym_freq, n_files = symbol_term_file_frequency(chunks)
    path_freq, n_path_files = path_term_file_frequency(chunks)
    out = []
    for idx, c in enumerate(chunks):
        s_lex = bm25_scores[idx] if idx < len(bm25_scores) else 0.0
        s_sym = symbol_score(c, task_terms, sym_freq=sym_freq,
                             n_files=n_files)
        s_path = path_score(c, explicit_paths, task_terms=task_terms,
                            path_freq=path_freq, n_files=n_path_files)
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
