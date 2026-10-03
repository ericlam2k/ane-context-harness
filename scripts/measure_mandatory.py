#!/usr/bin/env python3
"""Measure the mandatory-heuristic share on the frozen eval split.

For each eval task: how many selected chunks fly on a free pass
(selection_reasons contains "mandatory") vs earn their seat on score alone,
and what token share each side holds. Read-only; changes nothing.

Usage:
    python3 scripts/measure_mandatory.py
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from ane_context_harness import tokens as tokens_mod
    from ane_context_harness.benchmark import (
        FIXTURE_REPO_PATHS, load_task_split, DEFAULT_NEVER_READ)
    from ane_context_harness.config import build_config
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness.schemas import SelectRequest

    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)}})
    pipe = Pipeline(cfg)
    for repo_id, repo_path in FIXTURE_REPO_PATHS.items():
        pipe.register_repository(str(ROOT / repo_path), repo_id, True)

    tasks = load_task_split("eval", tasks_dir=str(ROOT / "benchmarks/tasks"))
    rows = []
    for t in tasks:
        pkg = pipe.select_context(SelectRequest(
            repository_id=t.repository_id, task=t.task,
            token_budget=t.token_budget))
        reasons = Counter()
        free = earned = free_tok = 0
        for e in pkg.evidence:
            rs = e.get("selection_reasons") or []
            for r in rs:
                reasons[r] += 1
            if "mandatory" in rs:
                free += 1
                free_tok += tokens_mod.count(e.get("content", ""))
        m = pkg.metrics
        rows.append({
            "task_id": t.task_id,
            "selected": len(pkg.evidence),
            "free_pass": free,
            "earned": len(pkg.evidence) - free,
            "free_token_share": round(free_tok / max(1, m["selected_tokens"]), 3),
            "reduction_percent": m["reduction_percent"],
        })
    n = len(rows)
    agg = {
        "n_tasks": n,
        "mean_selected": round(sum(r["selected"] for r in rows) / n, 1),
        "mean_free_pass": round(sum(r["free_pass"] for r in rows) / n, 1),
        "mean_earned": round(sum(r["earned"] for r in rows) / n, 1),
        "mean_free_token_share": round(
            sum(r["free_token_share"] for r in rows) / n, 3),
        "tasks_all_free": sum(1 for r in rows if r["earned"] == 0),
        "tasks_no_free": sum(1 for r in rows if r["free_pass"] == 0),
    }
    print(json.dumps({"aggregate": agg, "per_task": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
