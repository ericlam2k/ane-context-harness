"""Phase 0/1 measurement runner. Runs the labelled benchmark tasks and writes a
measured JSON report to benchmarks/reports/. No external calls; local fixtures only.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

REPO_PATHS = {
    "synthetic_py_project": "tests/fixtures/synthetic_py_project",
    "synthetic_ts_project": "tests/fixtures/synthetic_ts_project",
}


def main():
    from ane_context_harness.config import build_config
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness.benchmark import run_benchmark, report_summary, load_benchmark_tasks

    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": ["**/.env*", "**/.aws/**", "**/.ssh/**", "**/*.pem", "**/.EnvLocal"]},
    })
    pipe = Pipeline(cfg)
    tasks = load_benchmark_tasks("benchmarks/tasks")
    report = run_benchmark(tasks, pipe, REPO_PATHS)
    summary = report_summary(report)

    out_dir = Path("benchmarks/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [i.__dict__ for i in report.items]
    payload = {
        "label": report.label,
        "generated_by": "scripts/measure_phase1.py",
        "summary": summary,
        "items": items,
        "note": "Measured on host hardware (see summary.measured_on_platform). Synthetic fixtures; tight token budgets. ANE not claimed.",
    }
    out_path = out_dir / "phase1-measurement.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(json.dumps(summary, indent=2))
    print(f"\nReport written to {out_path}")
    return summary


if __name__ == "__main__":
    main()
