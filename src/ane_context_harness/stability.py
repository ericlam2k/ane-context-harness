"""Byte-stability proof for selections: read-only, no retention, no daemon.

Why this exists: providers charge less when the prompt prefix they already
read stays byte-identical. This module proves OUR side of that contract —
two identical selects share one fingerprint, so a caller can check that a
re-select reproduces the exact bytes before paying for another prefill.

What lives here:

- ``evidence_fingerprint``: stable sha256 over the deterministic evidence
  projection (task, repo, versions, ordered evidence path/symbol/score/
  reasons/content-hash/content). Two identical selects MUST share it.

What deliberately does NOT live here (commercial line only): TTL-bound
memoization of packages, background refresh while the machine is idle,
provider cache-window tables. Verification is public; retention is not.

Portable: stdlib only.
"""
from __future__ import annotations

import hashlib
import json


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def evidence_fingerprint(package, task: str | None = None) -> str:
    """Stable fingerprint of what providers actually cache.

    Same select (same task, repo, index, and evidence bytes) always yields
    the same fingerprint; anything that changes what would be sent changes
    it. Deterministic: JSON canonical form over the evidence projection.
    """
    proj = [
        package.repository_id,
        task if task is not None else package.task,
        package.policy_version,
        package.index_version,
        package.model_version,
        [(
            e.get("path"), e.get("start_line"), e.get("end_line"),
            e.get("symbol"), e.get("score"),
            e.get("selection_reasons"), e.get("category"),
            e.get("content_hash"), e.get("content"),
        ) for e in package.evidence],
    ]
    return hashlib.sha256(_canonical(proj)).hexdigest()
