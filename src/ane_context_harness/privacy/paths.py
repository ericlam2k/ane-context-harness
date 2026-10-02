"""Path policy (Phase 2 security layer, builds on Phase 1 path safety).

Denies policy-denied paths during indexing and selection. Reuses the Phase 1
glob matcher and traversal/symlink guards.
"""
from __future__ import annotations

import os
from fnmatch import translate as _fnmatch_translate
from pathlib import Path

from ..indexing.repository import _glob_match


class PathPolicy:
    def __init__(self, never_read: list, never_write: list = None):
        self.never_read = list(never_read or [])
        self.never_write = list(never_write or [])

    def denied(self, rel_path: str) -> str | None:
        """Return a reason string if the path is policy-denied, else None."""
        rel_n = rel_path.replace("\\", "/")
        for pat in self.never_read:
            if _glob_match(rel_n, pat):
                return "policy_deny_read"
        return None

    def allow_read(self, abs_path: Path, repo_root: Path) -> bool:
        from ..indexing.paths import safe_relpath, is_within
        if not is_within(abs_path, repo_root):
            return False
        rel = safe_relpath(abs_path, repo_root)
        if rel is None:
            return False
        return self.denied(rel) is None
