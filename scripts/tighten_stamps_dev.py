#!/usr/bin/env python3
"""Dev-split experiment: tighten mandatory stamps, watch savings vs recall.

Variants (monkeypatched, no prod change): baseline, min symbol-match length
4->5, 4->6, test-pair pinning off, both. Reports median/min reduction and
min/mean recall per variant on the 12 dev tasks. Eval split untouched.

Usage:
    python3 scripts/tighten_stamps_dev.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(pipe, tasks):
    from ane_context_harness.benchmark import run_benchmark, FIXTURE_REPO_PATHS
    paths = {k: str(ROOT / v) for k, v in FIXTURE_REPO_PATHS.items()}
    report = run_benchmark(tasks, pipe, paths)
    reds = [i.reduction_percent for i in report.items]
    recs = [i.recall for i in report.items]
    return {
        "median_reduction": round(st.median(reds), 2),
        "min_reduction": round(min(reds), 2),
        "mean_recall": round(st.fmean(recs), 4),
        "min_recall": round(min(recs), 4),
        "min_recall_tasks": sorted(
            {i.task_id for i in report.items if i.recall < 0.95}),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ane_context_harness.benchmark import load_task_split, DEFAULT_NEVER_READ
    from ane_context_harness.config import build_config
    from ane_context_harness.pipeline import Pipeline
    import ane_context_harness.retrieval.structural as structural
    import ane_context_harness.retrieval.selector as selector

    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)}})
    pipe = Pipeline(cfg)
    tasks = load_task_split("dev", tasks_dir=str(ROOT / "benchmarks/tasks"))

    out = {"n_dev_tasks": len(tasks), "variants": {}}
    out["variants"]["baseline_minlen4_pair_on"] = _run(pipe, tasks)

    _orig_minlen = structural.SYMBOL_MATCH_MIN_LEN
    _orig_pair = selector._nearest_test_for_source
    try:
        structural.SYMBOL_MATCH_MIN_LEN = 5
        out["variants"]["minlen5_pair_on"] = _run(pipe, tasks)
        structural.SYMBOL_MATCH_MIN_LEN = 6
        out["variants"]["minlen6_pair_on"] = _run(pipe, tasks)
        structural.SYMBOL_MATCH_MIN_LEN = _orig_minlen
        selector._nearest_test_for_source = lambda *a, **k: []
        out["variants"]["minlen4_pair_off"] = _run(pipe, tasks)
        structural.SYMBOL_MATCH_MIN_LEN = 5
        out["variants"]["minlen5_pair_off"] = _run(pipe, tasks)
    finally:
        structural.SYMBOL_MATCH_MIN_LEN = _orig_minlen
        selector._nearest_test_for_source = _orig_pair
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
