"""Schema v2 and frozen dev/eval split protections.

The split is write-once: budgets/tasks may be tuned on dev only, eval must
never move. These tests bind the frozen file to the task set by hash and
reject tasks that would pass trivially (budget >= eligible repo total).
"""
from __future__ import annotations

import json

import pytest

from src.ane_context_harness.benchmark import (DIFFICULTIES, PINNED_ASSIGNMENTS,
                                               REQUIRED_TASK_FIELDS, SPLIT_FILE,
                                               TaskSchemaError, derive_split,
                                               estimate_repo_totals,
                                               load_benchmark_tasks,
                                               load_task_split, task_set_hash,
                                               validate_task)


def _task(**over):
    d = {
        "task_id": "unit-001",
        "task": "do the thing",
        "repository_id": "repo_x",
        "difficulty": "typical",
        "category": "unit",
        "token_budget": 400,
        "required_chunks": [{"path": "src/a.py"}],
        "challenge": "unit challenge",
        "expected_retrieval_behavior": "unit behavior",
        "expected_final_package": "unit package",
        "ground_truth_provenance": "unit fixture",
    }
    d.update(over)
    return d


def test_validate_task_accepts_well_formed_task():
    validate_task(_task(), {"repo_x": 1000})


def test_validate_task_rejects_missing_required_fields():
    for field in REQUIRED_TASK_FIELDS:
        d = _task()
        d.pop(field, None)
        with pytest.raises(TaskSchemaError, match="missing required fields"):
            validate_task(d, {"repo_x": 1000})


def test_validate_task_rejects_unknown_difficulty():
    with pytest.raises(TaskSchemaError, match="difficulty"):
        validate_task(_task(difficulty="impossible"), {"repo_x": 1000})
    assert set(DIFFICULTIES) == {"small", "typical", "difficult"}


def test_validate_task_rejects_non_positive_budget():
    for bad in (0, -5, "400", 400.0):
        with pytest.raises(TaskSchemaError, match="token_budget"):
            validate_task(_task(token_budget=bad), {"repo_x": 1000})


def test_validate_task_rejects_empty_required_chunks():
    with pytest.raises(TaskSchemaError, match="required_chunks"):
        validate_task(_task(required_chunks=[]), {"repo_x": 1000})
    with pytest.raises(TaskSchemaError, match="path"):
        validate_task(_task(required_chunks=[{"symbol": "x"}]), {"repo_x": 1000})


def test_validate_task_rejects_whole_repo_fits():
    """A budget >= the eligible total means no selection pressure at all."""
    with pytest.raises(TaskSchemaError, match="entire repository fits"):
        validate_task(_task(token_budget=1000), {"repo_x": 1000})
    with pytest.raises(TaskSchemaError, match="entire repository fits"):
        validate_task(_task(token_budget=1500), {"repo_x": 1000})


def test_validate_task_rejects_unknown_repository_when_totals_given():
    with pytest.raises(TaskSchemaError, match="unknown repository_id"):
        validate_task(_task(), {"other_repo": 1000})


def test_validate_task_rejects_missing_provenance():
    d = _task()
    d.pop("ground_truth_provenance")
    with pytest.raises(TaskSchemaError, match="ground_truth_provenance"):
        validate_task(d, {"repo_x": 1000})


def test_all_benchmark_tasks_validate_against_totals():
    import pathlib
    totals = estimate_repo_totals()
    raw = [json.loads(p.read_text(encoding="utf-8"))
           for p in sorted(pathlib.Path("benchmarks/tasks").glob("*.json"))]
    assert len(raw) >= 20
    for d in raw:
        validate_task(d, totals)  # raises on schema or trivially-large budgets


# ---- frozen split -----------------------------------------------------------

def test_split_file_exists_and_is_frozen():
    with open(SPLIT_FILE, encoding="utf-8") as f:
        frozen = json.load(f)
    assert frozen["schema_version"] == "split-1"
    assert frozen["seed"] == 20261002
    tasks = load_benchmark_tasks("benchmarks/tasks")
    assert frozen["task_set_hash"] == task_set_hash(tasks)
    dev, ev = set(frozen["dev"]), set(frozen["eval"])
    assert not (dev & ev)
    assert dev | ev == {t.task_id for t in tasks}
    assert frozen["counts"] == {"dev": len(dev), "eval": len(ev),
                                "total": len(dev) + len(ev)}


def test_split_is_stratified_and_pinned():
    frozen = json.loads(open(SPLIT_FILE, encoding="utf-8").read())
    tasks = {t.task_id: t for t in load_benchmark_tasks("benchmarks/tasks")}
    for tid, side in PINNED_ASSIGNMENTS.items():
        assert tid in frozen[side], f"pinned {tid} must be {side}"
    per_diff = {}
    for tid, t in tasks.items():
        side = "dev" if tid in set(frozen["dev"]) else "eval"
        per_diff.setdefault(t.difficulty, {"dev": 0, "eval": 0})[side] += 1
    for counts in per_diff.values():
        total = counts["dev"] + counts["eval"]
        assert 0.3 <= counts["dev"] / total <= 0.5, counts


def test_load_task_split_returns_eval_side_only():
    dev = load_task_split("dev")
    ev = load_task_split("eval")
    assert dev and ev
    assert not ({t.task_id for t in dev} & {t.task_id for t in ev})
    assert len(dev) + len(ev) == len(load_benchmark_tasks("benchmarks/tasks"))
    # deterministic across calls
    assert [t.task_id for t in load_task_split("eval")] == [t.task_id for t in ev]


def test_load_task_split_rejects_unknown_side():
    with pytest.raises(ValueError, match="split must be"):
        load_task_split("train")


def test_load_task_split_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="freeze it with derive_split"):
        load_task_split("eval", split_file=tmp_path / "nope.json")


def test_load_task_split_rejects_hash_mismatch(tmp_path):
    frozen = json.loads(open(SPLIT_FILE, encoding="utf-8").read())
    frozen["task_set_hash"] = "deadbeef"
    p = tmp_path / "splits.json"
    p.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="does not match the current task set"):
        load_task_split("eval", split_file=p)


def test_derive_split_is_deterministic_and_pinned():
    tasks = load_benchmark_tasks("benchmarks/tasks")
    a = derive_split(tasks)
    b = derive_split(tasks)
    assert a["dev"] == b["dev"] and a["eval"] == b["eval"]
    for tid, side in PINNED_ASSIGNMENTS.items():
        assert tid in a[side]
