"""Tests for SQLite incremental storage + hash invalidation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.ane_context_harness.indexing.repository import build_chunks, detect_language
from src.ane_context_harness.indexing.storage import Storage
from src.ane_context_harness.indexing.symbols import extract_symbols


def _index(repo, storage, never_read=None):
    chunks, plan = build_chunks(repo, "repo1", 1000000, 20, 3)
    by_path = {}
    for c in chunks:
        by_path.setdefault(c.path, []).append(_chunk_dict(c))
    for path, cs in by_path.items():
        storage.replace_chunks(path, cs)
    for fi in plan.files:
        if never_read and any(
            fi.rel_path == p or __import__("fnmatch").fnmatch(fi.rel_path, p)
            for p in never_read
        ):
            continue
        for name, s, e in extract_symbols(fi.language, fi.content):
            storage.upsert_symbol(fi.rel_path, name, s, e)
        storage.upsert_file(fi.rel_path, fi.language, fi.size_bytes, fi.content_hash, fi.mtime_ns)
    return chunks


def _chunk_dict(c):
    import json
    return {
        "chunk_id": c.chunk_id, "path": c.path, "language": c.language,
        "start_line": c.start_line, "end_line": c.end_line, "symbol": c.symbol,
        "content_hash": c.content_hash, "estimated_tokens": c.estimated_tokens,
        "lexical_terms": json.dumps(list(c.lexical_terms)),
        "content": c.content,
    }


def test_incremental_only_rechunks_changed(tmp_path, py_repo):
    st = Storage(tmp_path / "idx.db", "repo1")
    st.set_index_version("1")
    chunks0 = _index(py_repo, st, never_read=[".env*", ".aws/**"])
    n0 = len(chunks0)
    # rebuild with incremental (identical never_read)
    res = st.incremental_rebuild(py_repo, 1000000, 20, 3, [".env*", ".aws/**"])
    assert res["files_indexed"] == 0  # nothing changed
    assert res["files_skipped"] >= 1
    chunks1 = st.load_chunks()
    assert len(chunks1) == n0  # unchanged


def test_hash_invalidation_rebuilds_on_change(tmp_path, py_repo):
    st = Storage(tmp_path / "idx.db", "repo1")
    st.set_index_version("1")
    _index(py_repo, st)
    # mutate a file
    target = Path(py_repo) / "src" / "discount.py"
    original = target.read_text()
    target.write_text(original + "\n# extra line\n")
    try:
        res = st.incremental_rebuild(py_repo, 1000000, 20, 3, [".env*", ".aws/**"])
        assert res["files_indexed"] >= 1
    finally:
        target.write_text(original)


def test_index_version_persisted(tmp_path, py_repo):
    st = Storage(tmp_path / "idx.db", "repo1")
    st.set_index_version("3")
    assert st.index_version() == "3"


def test_storage_permissions_user_only(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX permission bits don't apply on Windows ACLs")
    st = Storage(tmp_path / "idx.db", "repo1")
    st.close()
    mode = oct((tmp_path / "idx.db").stat().st_mode & 0o777)
    assert int(mode, 8) & 0o077 == 0  # no group/other bits
