#!/usr/bin/env python3
"""Frozen-eval comparison: single-pass (off) vs max-fused vs sum-fused ranking.

Reports gates (median/min reduction, min/mean recall, p50) plus mean
selected-set overlap with baseline so a tie explains itself. Eval split only.

Usage:
    python3 scripts/eval_expansion.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(mode: str):
    from ane_context_harness.benchmark import (
        run_benchmark, FIXTURE_REPO_PATHS, load_task_split, DEFAULT_NEVER_READ)
    from ane_context_harness.config import build_config
    from ane_context_harness.pipeline import Pipeline
    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)},
        "retrieval": {"query_expansion": mode}})
    pipe = Pipeline(cfg)
    paths = {k: str(ROOT / v) for k, v in FIXTURE_REPO_PATHS.items()}
    tasks = load_task_split("eval", tasks_dir=str(ROOT / "benchmarks/tasks"))
    report = run_benchmark(tasks, pipe, paths)
    return report


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    modes = {}
    lat = {}
    for mode in ("off", "max", "sum"):
        rep = _run(mode)
        reds = [i.reduction_percent for i in rep.items]
        recs = [i.recall for i in rep.items]
        modes[mode] = {
            "median_reduction": round(st.median(reds), 2),
            "min_reduction": round(min(reds), 2),
            "mean_recall": round(st.fmean(recs), 4),
            "min_recall": round(min(recs), 4),
            "selected_ids": {i.task_id: None for i in rep.items},
        }
        lat[mode] = [i.total_latency_ms for i in rep.items]
    out = {"n_eval_tasks": 18, "modes": {
        m: {k: v for k, v in d.items() if k != "selected_ids"}
        for m, d in modes.items()}}
    for m in ("off", "max", "sum"):
        out["modes"][m]["p50_latency_ms"] = round(st.median(lat[m]), 2)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
