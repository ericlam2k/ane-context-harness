#!/usr/bin/env python3
"""Ranking-metrics confirmation: single-pass vs max vs sum fusion.

Macro-mean Recall@1/5/10, nDCG@10, MRR over the frozen eval split per
METRIC_DEFINITIONS (relevant = required + helpful). Ties keep max.

Usage:
    python3 scripts/ranking_fusion.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("recall_at_1", "recall_at_5", "recall_at_10", "ndcg_at_10", "mrr")


def _run(mode: str):
    from ane_context_harness.benchmark import (
        FIXTURE_REPO_PATHS, load_task_split, DEFAULT_NEVER_READ)
    from ane_context_harness.config import build_config
    from ane_context_harness.metrics import package_ranking_metrics
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness.schemas import SelectRequest
    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)},
        "retrieval": {"query_expansion": mode}})
    pipe = Pipeline(cfg)
    paths = {k: str(ROOT / v) for k, v in FIXTURE_REPO_PATHS.items()}
    tasks = load_task_split("eval", tasks_dir=str(ROOT / "benchmarks/tasks"))
    per_task = []
    for t in tasks:
        pipe.register_repository(paths[t.repository_id], t.repository_id, False)
        pkg = pipe.select_context(SelectRequest(
            repository_id=t.repository_id, task=t.task,
            token_budget=t.token_budget))
        chunks = pipe._storage_for(t.repository_id).load_chunks()
        m = package_ranking_metrics(pkg.evidence, chunks, t)
        per_task.append({"task_id": t.task_id,
                         **{k: m[k] for k in KEYS}})
    agg = {k: round(st.fmean([r[k] for r in per_task]), 4) for k in KEYS}
    return agg, per_task


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    out = {"n_eval_tasks": 18, "modes": {}, "per_task": {}}
    for mode in ("off", "max", "sum"):
        agg, per_task = _run(mode)
        out["modes"][mode] = agg
        out["per_task"][mode] = per_task
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
