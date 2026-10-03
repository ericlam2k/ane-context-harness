"""Performance benchmark run on the current host. Results are measured here,
not fabricated. Asserts Phase 1 acceptance gates.
"""
from __future__ import annotations

import json
import statistics

import pytest

from src.ane_context_harness.benchmark import (run_benchmark, report_summary,
                                               load_task_split, FIXTURE_REPO_PATHS,
                                               DEFAULT_NEVER_READ)
from src.ane_context_harness.config import build_config
from src.ane_context_harness.pipeline import Pipeline

# Gates run on the FROZEN eval split only (benchmarks/splits.json): dev tasks
# are for tuning and must never inform these assertions.
EVAL_SPLIT = "eval"


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    cfg = build_config({"index": {"storage_path": str(tmp_path_factory.mktemp("bench"))},
                        "privacy": {"never_read": list(DEFAULT_NEVER_READ)}})
    pipe = Pipeline(cfg)
    tasks = load_task_split(EVAL_SPLIT)
    report = run_benchmark(tasks, pipe, FIXTURE_REPO_PATHS)
    summary = report_summary(report)
    return report, summary


def test_benchmark_runs_all_tasks(bench):
    report, summary = bench
    assert summary["n"] >= 3
    for item in report.items:
        print(f"[bench] {item.task_id}: reduction={item.reduction_percent}% recall={item.recall} latency={item.total_latency_ms}ms rss={item.peak_rss_mb}")


def test_phase1_median_reduction_at_least_25_percent(bench):
    report, summary = bench
    assert summary["median_reduction_percent"] >= 25.0, summary


def test_phase1_required_evidence_recall_at_least_95(bench):
    report, summary = bench
    assert summary["min_recall"] >= 0.95, summary


def test_phase1_no_accelerator_surface(bench):
    report, summary = bench
    disc = report.platform["discovery"]
    assert disc["devices"] == {}
    # compute_mode must stay conservative
    assert report.platform["discovery"]["runtime"]["compute_mode"] == "deterministic_only"


def test_phase1_latency_within_target(bench):
    report, summary = bench
    print(f"[bench] p50 latency = {summary['p50_latency_ms']} ms; p95 = {summary['p95_latency_ms']} ms")
    assert summary["p50_latency_ms"] <= 500.0
