"""Negative pins: exclude_paths never appear in evidence, contradictions refuse.

Portable (public-syncable): stdlib only, fixture repos only.
"""
import pytest

from ane_context_harness.config import build_config, merge
from ane_context_harness.pipeline import Pipeline
from ane_context_harness import schemas

FIXTURE = "tests/fixtures/synthetic_py_project"


def _pipe(tmp_path):
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5}}
    return Pipeline(build_config(merge(base, {})))


def _select(pipe, rid, task, **kw):
    req = schemas.SelectRequest(repository_id=rid, task=task,
                                token_budget=2000, **kw)
    return pipe.select_context(req)


def test_excluded_path_never_appears(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-live")
    base = _select(pipe, "exc-live", "Fix the discount calculation")
    assert base.evidence  # precondition: something to exclude
    victim = base.evidence[0]["path"]
    pkg = _select(pipe, "exc-live", "Fix the discount calculation",
                  exclude_paths=[victim])
    assert all(e["path"] != victim for e in pkg.evidence)
    diag = pkg.metrics["diagnostics"]["excluded"]
    assert victim in diag["paths"]
    assert diag["chunks_dropped"] >= 1


def test_excluded_diag_stamped_when_empty(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-empty")
    pkg = _select(pipe, "exc-empty", "Fix the discount calculation")
    assert pkg.metrics["diagnostics"]["excluded"] == {
        "paths": [], "chunks_dropped": 0}


def test_contradiction_refuses_exact_and_suffix(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-contra")
    with pytest.raises(ValueError, match="contradictory pin"):
        _select(pipe, "exc-contra", "Fix the discount calculation",
                explicit_paths=["src/discount.py"],
                exclude_paths=["src/discount.py"])
    with pytest.raises(ValueError, match="contradictory pin"):
        _select(pipe, "exc-contra", "Fix the discount calculation",
                explicit_paths=["src/discount.py"],
                exclude_paths=["discount.py"])
    with pytest.raises(ValueError, match="contradictory pin"):
        _select(pipe, "exc-contra", "Fix the discount calculation",
                explicit_paths=["discount.py"],
                exclude_paths=["src/discount.py"])


def test_pin_forms_normalize(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-norm")
    base = _select(pipe, "exc-norm", "Fix the discount calculation")
    victim = base.evidence[0]["path"]
    pkg = _select(pipe, "exc-norm", "Fix the discount calculation",
                  exclude_paths=["./" + victim])
    assert all(e["path"] != victim for e in pkg.evidence)

