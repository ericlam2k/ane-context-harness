"""Baseline path safety (defense-in-depth, not the full Phase 2 security policy).

Blocks traversal (`..`), symlinks that escape the repo root, and normalizes paths.
Full denied-path / secret-redaction policy is deferred to Phase 2.
"""
from __future__ import annotations

import os
from pathlib import Path


def normalize_repo_path(repo_root: str | os.PathLike) -> Path:
    return Path(repo_root).resolve()


def safe_relpath(path: Path, repo_root: Path) -> str | None:
    """Return a normalized relative path within repo_root, or None if unsafe."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        return None
    if rel.parts and (rel.parts[0] == ".." or ".." in rel.parts):
        return None
    # reject absolute escapes
    if resolved.is_symlink():
        return None
    return str(rel).replace("\\", "/")


def is_within(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root)
        return True
    except (ValueError, OSError, RuntimeError):
        return False
