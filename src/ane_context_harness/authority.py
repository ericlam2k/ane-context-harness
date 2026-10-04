"""Per-source authority flags: developer-declared source truth.

One file (config `authority.authoritative_paths`), no auto-suggestion: the
machine finds candidates, only the developer crowns truth. A flagged path
(a repo-relative glob, e.g. "docs/pricing-rules.md") pins its chunks as
mandatory — the same retention mechanism as explicit paths. Retrieval can
only find; this file declares what wins.

Portable: stdlib fnmatch only.
"""
from __future__ import annotations

import fnmatch


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def match_authority(path: str, patterns: list) -> list:
    """Return the subset of patterns crowning this chunk path."""
    norm = _norm(path)
    base = norm.split("/")[-1]
    hit = []
    for pat in patterns or []:
        p = _norm(str(pat))
        if not p:
            continue
        if (fnmatch.fnmatch(norm, p) or fnmatch.fnmatch(base, p)
                or norm == p or norm.endswith("/" + p)):
            hit.append(str(pat))
    return hit
