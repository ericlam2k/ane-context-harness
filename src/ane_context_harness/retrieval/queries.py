"""Task query normalization + expansion for multi-pass scoring.

The raw task carries noise the lexer keeps (``to``, ``arm``, ``c``, ``5``):
harmless for pinning, dilutive for BM25 length norms. This module derives:

- Q0 original task (unchanged; pinning and recall floor always use this),
- Q1 normalized: usable content terms only (len>=4, non-generic) — the pin
  vocabulary as a query, noise dropped,
- Q2 identifier-joined: full identifier forms (``max_concurrent_agents``)
  kept whole to match full-form chunk terms.

Ranking-only: fused scores reorder candidates; selection reasons, mandatory
stamps, and budgets are untouched. Deterministic, no models, no network.
"""
from __future__ import annotations

from ..indexing.chunking import lex_terms
from .structural import GENERIC_SYMBOL_TERMS, SYMBOL_MATCH_MIN_LEN


def usable_terms(task: str) -> list:
    """Content terms eligible to pin: len>=4 and non-generic, order-kept."""
    seen: list = []
    for t in lex_terms(task):
        if len(t) >= SYMBOL_MATCH_MIN_LEN and t not in GENERIC_SYMBOL_TERMS \
                and t not in seen:
            seen.append(t)
    return seen


def full_identifiers(task: str) -> list:
    """Underscore/camel identifiers kept whole (match full-form chunk terms)."""
    import re
    seen: list = []
    for tok in re.findall(r"[A-Za-z_][\w$]*", task):
        low = tok.lower()
        if ("_" in tok or any(c.isupper() for c in tok[1:])) \
                and len(low) >= SYMBOL_MATCH_MIN_LEN and low not in seen:
            seen.append(low)
    return seen


def expand_queries(task: str) -> list:
    """[original, normalized-content, identifier-joined]. Never empty."""
    content = " ".join(usable_terms(task))
    idents = " ".join(full_identifiers(task))
    out = [task]
    out.append(content if content else task)
    out.append(idents if idents else task)
    return out


def fuse_scores(per_query: list, mode: str) -> list:
    """Elementwise fusion across query passes: 'max' or 'sum'."""
    if not per_query:
        return []
    if mode not in ("max", "sum"):
        raise ValueError(f"fusion mode must be 'max' or 'sum', got {mode!r}")
    n = len(per_query[0])
    if mode == "max":
        return [max(q[i] for q in per_query) for i in range(n)]
    return [sum(q[i] for q in per_query) for i in range(n)]
