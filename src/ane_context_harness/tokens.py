"""Token estimation: one deterministic backend for every environment.

Counts feed selection, budgets, validation gates and every reported token
figure, so they MUST NOT depend on which optional packages happen to be
installed. Earlier versions preferred tiktoken when importable, which made the
same file count differently (e.g. 169 vs 187) across machines and changed
selection results — the counting backend is therefore pinned to the regex
heuristic and versioned in TOKEN_ESTIMATOR_VERSION (bump on any behavior
change; recorded in release-evidence bundles).
"""
from __future__ import annotations

import re

# Bumped whenever the counting behavior changes in a way that can move token
# counts between releases. Recorded in release-evidence bundles.
#   1: heuristic or tiktoken depending on environment (non-reproducible)
#   2: pinned regex heuristic everywhere
TOKEN_ESTIMATOR_VERSION = "2"

_TOK = re.compile(r"\w+|[^\w\s]", re.UNICODE)
BACKEND = "regex-heuristic"


def count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(_TOK.findall(text)))


def estimate(text: str) -> int:
    """Public alias for token count."""
    return count(text)


def split_for_budget(text: str, budget_tokens: int) -> list:
    """Greedy split of text into pieces whose token count stays near budget.

    Returns list of (substring, token_count) tuples. Used to over-allocate
    conservatively when packing evidence.
    """
    if not text:
        return []
    # Conservative token-per-char ratio to avoid under-budget surprises.
    ratio = 0.30
    step = max(1, int(budget_tokens / max(1, ratio)))
    out = []
    i = 0
    while i < len(text):
        chunk = text[i:i + step]
        n = count(chunk)
        out.append((chunk, n))
        i += step
    return out
