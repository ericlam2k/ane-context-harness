"""Integration: index a repo, then select context for a labelled task."""
from __future__ import annotations

import json
from pathlib import Path

from src.ane_context_harness.schemas import SelectRequest
from src.ane_context_harness.indexing.repository import detect_language
from src.ane_context_harness.providers.markdown import render_markdown


def test_index_python_repo(pipeline, py_repo):
    resp = pipeline.register_repository(py_repo, "synthetic_py_project", True)
    assert resp.files_indexed >= 1
    assert resp.chunks_indexed >= 1
    # .env must not be indexed
    chunks = pipeline._storage_for("synthetic_py_project").load_chunks()
    paths = {c.path for c in chunks}
    assert ".env" not in paths
    assert "src/discount.py" in paths


def test_select_context_recall_and_reduction(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="Fix the incorrect discount calculation and update its tests",
        token_budget=1200,
        explicit_paths=["src/discount.py"],
    )
    pkg = pipeline.select_context(req)
    pkg.markdown = render_markdown(pkg)
    assert pkg.request_id.startswith("ctx_")
    assert pkg.metrics["candidate_tokens"] >= pkg.metrics["selected_tokens"]
    # recall: discount.py and a test chunk must appear
    sel_paths = {e["path"] for e in pkg.evidence}
    assert "src/discount.py" in sel_paths
    assert any(p.startswith("tests/test") for p in sel_paths)
    # reduction on this fixture (plenty of distractors) should exceed 25%
    assert pkg.metrics["reduction_percent"] >= 25.0
    # no secret leaked
    full = pkg.markdown
    assert "AKIAIOSFODNN7EXAMPLE" not in full
    assert "secret@db.internal" not in full
    # provenance
    ev0 = pkg.evidence[0]
    assert "content_hash" in ev0
    assert "selection_reasons" in ev0
    assert "start_line" in ev0 and "end_line" in ev0


def test_select_returns_stable_request_id_length(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(repository_id="synthetic_py_project", task="discount bug", token_budget=4000)
    pkg = pipeline.select_context(req)
    assert pkg.request_id.startswith("ctx_") and len(pkg.request_id) == 20


def test_markdown_is_non_empty(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(repository_id="synthetic_py_project", task="discount", token_budget=8000)
    pkg = pipeline.select_context(req)
    pkg.markdown = render_markdown(pkg)
    assert "# Selected repository context" in pkg.markdown


def test_explicit_path_mandatory_when_budget_tight(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(repository_id="synthetic_py_project", task="discount",
                        token_budget=50, explicit_paths=["src/discount.py"])
    pkg = pipeline.select_context(req)
    sel_paths = {e["path"] for e in pkg.evidence}
    assert "src/discount.py" in sel_paths


def test_no_shell_execution_attribute(pipeline):
    # The pipeline must not expose any subprocess/shell entrypoint.
    import inspect
    src = inspect.getsource(type(pipeline)).lower()
    assert "subprocess" not in src
    assert "os.system" not in src
