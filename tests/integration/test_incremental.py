"""Integration: incremental indexing only re-chunks changed files."""
from __future__ import annotations

from pathlib import Path


def test_incremental_no_change_no_reindex(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    chunks0 = pipeline._storage_for("synthetic_py_project").load_chunks()
    # second registration is incremental
    resp = pipeline.register_repository(py_repo, "synthetic_py_project", False)
    assert resp.incremental is True
    assert resp.files_indexed == 0
    chunks1 = pipeline._storage_for("synthetic_py_project").load_chunks()
    assert len(chunks1) == len(chunks0)


def test_incremental_rebuilds_changed_file(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    target = Path(py_repo) / "src" / "discount.py"
    original = target.read_text()
    target.write_text(original + "\n# fixture edit for incremental test\n")
    try:
        resp = pipeline.register_repository(py_repo, "synthetic_py_project", False)
        assert resp.incremental is True
        assert resp.files_indexed >= 1
    finally:
        target.write_text(original)


def test_force_rebuild_resets(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    resp = pipeline.register_repository(py_repo, "synthetic_py_project", True)
    assert resp.incremental is False
    assert resp.files_indexed >= 1
