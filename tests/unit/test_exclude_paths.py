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
        "paths": [], "chunks_dropped": 0, "dropped_by_pattern": {},
        "unmatched": []}


def test_exclude_directory_prefix_drops_whole_tree(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-dir")
    for pat in ("tests/", "tests"):
        pkg = _select(pipe, "exc-dir", "Fix the discount calculation",
                      exclude_paths=[pat])
        assert pkg.evidence  # precondition: plenty left outside tests/
        assert all(not e["path"].startswith("tests/") for e in pkg.evidence)
        diag = pkg.metrics["diagnostics"]["excluded"]
        assert diag["chunks_dropped"] >= 2  # both fixture test files
        assert diag["unmatched"] == []
        assert sum(diag["dropped_by_pattern"].values()) == diag["chunks_dropped"]


def test_exclude_prefix_needs_slash_boundary(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-bound")
    # "src" must not swallow a hypothetical "src-discount/" tree: the `/`
    # boundary is mandatory. The fixture has no such dir, so assert the
    # matcher directly for the boundary plus the positive case.
    from ane_context_harness.pipeline import _is_excluded
    assert _is_excluded("tests/test_discount.py", ["tests/"])
    assert _is_excluded("tests/test_discount.py", ["tests"])
    assert not _is_excluded("src-discount/extra.py", ["src"])
    assert not _is_excluded("latest/news.md", ["test"])
    assert _is_excluded("src/discount.py", ["discount.py"])


def test_exclude_unmatched_pattern_reported(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-unmatched")
    pkg = _select(pipe, "exc-unmatched", "Fix the discount calculation",
                  exclude_paths=["no/such/dir/"])
    diag = pkg.metrics["diagnostics"]["excluded"]
    assert diag["unmatched"] == ["no/such/dir/"]
    assert diag["chunks_dropped"] == 0


def test_contradiction_refuses_directory_prefix(tmp_path):
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "exc-contra-dir")
    with pytest.raises(ValueError, match="contradictory pin"):
        _select(pipe, "exc-contra-dir", "Fix the discount calculation",
                explicit_paths=["tests/test_discount.py"],
                exclude_paths=["tests/"])


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

