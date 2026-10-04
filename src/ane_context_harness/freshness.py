"""Pinned-source freshness: silent refresh + change notices.

Scope is deliberately tiny — only explicitly pinned sources are watched:
per-request `explicit_paths` and config `authority.authoritative_paths`.
Everything else the agent edits never triggers a notice (no nag fatigue
by construction).

On each select the pipeline resolves pinned paths against the stored
index, compares filesystem content hashes, silently re-indexes changed
files, and reports `pinned_changed` / `pinned_missing` in diagnostics.
The footer surfaces a one-line notice; the refresh itself is silent.

Portable: stdlib only. Same sha256 content-hash as scan_repository.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def expand_pinned(repo_root: str, explicit_paths: list,
                  authority_paths: list, indexed: set | None = None) -> list:
    """Resolve pinned patterns to repo-relative file paths (sorted, deduped).

    Explicit paths are exact (normalized); authority entries are globs
    expanded against the filesystem. An explicit path that is indexed but
    no longer on disk is kept so its deletion is reported as missing.
    Non-matching patterns vanish silently.
    """
    root = Path(repo_root)
    indexed = indexed or set()
    out: dict = {}
    for p in explicit_paths or []:
        norm = str(p).replace("\\", "/").lstrip("./")
        if norm and ((root / norm).is_file() or norm in indexed):
            out[norm] = True
    for pat in authority_paths or []:
        pat = str(pat).replace("\\", "/").lstrip("./")
        if not pat:
            continue
        try:
            for hit in sorted(root.glob(pat)):
                if hit.is_file():
                    rel = hit.relative_to(root).as_posix()
                    out[rel] = True
        except (OSError, ValueError):
            continue
    return sorted(out)


def file_hash(repo_root: str, rel_path: str) -> str | None:
    """Current sha256 of a repo file, or None when unreadable (same rules
    as scan_repository: regular utf-8 files only)."""
    try:
        raw = (Path(repo_root) / rel_path).read_bytes()
    except OSError:
        return None
    if not raw or b"\x00" in raw[:8192]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_stale(repo_root: str, rel_paths: list, stored: dict) -> tuple[list, list]:
    """Split pinned paths into (changed, missing).

    Changed = exists on disk with a different hash than the index
    (or never indexed). Missing = pinned but absent from disk.
    Unchanged files are silent — no notice, no refresh.
    """
    changed, missing = [], []
    for rel in rel_paths:
        if not (Path(repo_root) / rel).is_file():
            missing.append(rel)
            continue
        cur = file_hash(repo_root, rel)
        if cur is None:
            continue  # binary/unreadable: index-time rules skip it too
        prev = stored.get(rel)
        if prev is None or prev[0] != cur:
            changed.append(rel)
    return changed, missing
