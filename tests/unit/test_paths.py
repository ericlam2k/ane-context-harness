"""Baseline path safety tests (traversal + symlink blocking)."""
from __future__ import annotations

import os
from pathlib import Path

from src.ane_context_harness.indexing.paths import safe_relpath, is_within, normalize_repo_path


def _make_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("hello\n")
    return root


def test_safe_relpath_inside(tmp_path):
    root = _make_repo(tmp_path)
    p = root / "src" / "a.py"
    assert safe_relpath(p, root) == "src/a.py"


def test_safe_relpath_blocks_traversal(tmp_path):
    root = _make_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    assert safe_relpath(outside, root) is None


def test_safe_relpath_blocks_symlink_escape(tmp_path):
    root = _make_repo(tmp_path)
    target = tmp_path / "secret.txt"
    target.write_text("secret")
    link = root / "link.txt"
    try:
        os.symlink(target, link)
    except OSError:
        return  # skip on systems that can't symlink
    assert safe_relpath(link, root) is None


def test_is_within(tmp_path):
    root = _make_repo(tmp_path)
    assert is_within(root / "src" / "a.py", root) is True
    assert is_within(tmp_path / "outside.txt", root) is False


def test_normalize_repo_path(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    assert normalize_repo_path(root).exists()
