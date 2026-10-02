"""Concurrent with/without-harness benchmark runner (one eval-split half per process).

Usage: python3 scripts/run_concurrent_ab.py <group: 1|2> <out_dir>
- Loads the frozen eval split, splits by sorted task_id into two halves.
- Each process builds its own temp index (no shared storage -> no lock contention).
- Arms: A (baseline full context) + B (harness select). No arm C here.
- Stdout is the run log: callers redirect it to benchmarks/logs/<run>/group<N>.log.
- Writes a JSON+Markdown report into <out_dir> via evaluation.write_report.
Temp storage is removed in `finally` so runs never leak $TMPDIR dirs.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time

sys.path.insert(0, "src")

from ane_context_harness.benchmark import (  # noqa: E402
    DEFAULT_NEVER_READ, FIXTURE_REPO_PATHS, load_task_split)
from ane_context_harness.config import build_config  # noqa: E402
from ane_context_harness.evaluation import run_evaluation, write_report  # noqa: E402
from ane_context_harness.pipeline import Pipeline  # noqa: E402


def main(group: int, out_dir: str) -> int:
    tasks = sorted(load_task_split("eval"), key=lambda t: t.task_id)
    half = tasks[: len(tasks) // 2] if group == 1 else tasks[len(tasks) // 2:]
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{stamp}] group {group}: {len(half)} tasks "
          f"({', '.join(t.task_id for t in half)})", flush=True)
    storage = tempfile.mkdtemp(prefix="aneh-conc-")
    cfg = build_config({
        "index": {"storage_path": storage},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)},
    })
    pipe = Pipeline(cfg)
    try:
        report = run_evaluation(half, pipe, dict(FIXTURE_REPO_PATHS),
                                repeats=5, warmup=1)
        paths = write_report(report, out_dir)
        arms = report.summary["arms"]
        b = arms["B_harness_deterministic"]
        print(f"[{time.strftime('%H:%M:%S')}] group {group} done: "
              f"B median {b['median_tokens']} tok "
              f"({b['median_reduction_percent']}% red), min recall "
              f"{b['min_recall']}, p50 {b['median_latency_ms']} ms", flush=True)
        print(f"[{time.strftime('%H:%M:%S')}] reports: {paths}", flush=True)
        print(json.dumps(report.summary, indent=2, default=str), flush=True)
        return 0
    finally:
        pipe.close()
        shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]), sys.argv[2]))
