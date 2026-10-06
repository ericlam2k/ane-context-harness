"""Byte-stability proof: identical selects share one fingerprint."""
from ane_context_harness import schemas
from ane_context_harness.config import build_config, merge
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.stability import evidence_fingerprint


def _select(tmp_path, task):
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "s")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project", "stab")
    try:
        return pipe.select_context(schemas.SelectRequest(
            repository_id="stab", task=task, token_budget=2000))
    finally:
        pipe.close()


def test_identical_selects_share_fingerprint(tmp_path):
    a = _select(tmp_path, "Fix the discount calculation")
    b = _select(tmp_path, "Fix the discount calculation")
    assert evidence_fingerprint(a) == evidence_fingerprint(b)
    assert len(evidence_fingerprint(a)) == 64


def test_different_task_changes_fingerprint(tmp_path):
    a = _select(tmp_path, "Fix the discount calculation")
    b = _select(tmp_path, "How does the inventory module work")
    assert evidence_fingerprint(a) != evidence_fingerprint(b)


def test_task_override_pins_comparison(tmp_path):
    a = _select(tmp_path, "Fix the discount calculation")
    assert (evidence_fingerprint(a, task="Fix the discount calculation")
            == evidence_fingerprint(a))
