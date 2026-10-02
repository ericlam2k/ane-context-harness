"""Integration: Phase 5 end-to-end A/B evaluation (thesis §16).

Asserts the report is complete, provenance-bound, and free of unqualified
claims: derived figures (cost/TTFT) are labelled, the Core ML arm is reported
as not-run behind the P3.6 gate, and energy is explicitly not measured.
"""
from __future__ import annotations

import json

import pytest

from src.ane_context_harness.benchmark import (load_task_split, FIXTURE_REPO_PATHS,
                                               DEFAULT_NEVER_READ)
from src.ane_context_harness.config import build_config
from src.ane_context_harness.evaluation import (cost_usd, recommend,
                                                report_json, report_markdown,
                                                run_evaluation, summarize,
                                                ttft_sensitivity_ms, write_report)
from src.ane_context_harness.pipeline import Pipeline

# Frozen eval split (benchmarks/splits.json) — dev is for tuning only.
EVAL_TASKS = load_task_split("eval")
EVAL_COUNT = len(EVAL_TASKS)


@pytest.fixture(scope="module")
def evaluation(tmp_path_factory):
    cfg = build_config({"index": {"storage_path": str(tmp_path_factory.mktemp("p5"))},
                        "privacy": {"never_read": list(DEFAULT_NEVER_READ)}})
    pipe = Pipeline(cfg)
    return run_evaluation(EVAL_TASKS, pipe, FIXTURE_REPO_PATHS, repeats=2, warmup=0)


def test_cost_is_derived_math():
    assert cost_usd(1_000_000, 3.00) == 3.0
    assert cost_usd(0, 3.00) == 0.0
    assert cost_usd(500_000, 0.5) == 0.25


def test_ttft_sensitivity_is_monotonic():
    d = ttft_sensitivity_ms(2785, [2000, 8000, 20000])
    assert set(d) == {"2000", "8000", "20000"}
    assert d["2000"] > d["8000"] > d["20000"]


def test_evaluation_runs_all_tasks(evaluation):
    assert evaluation.label == "phase5-ab-evaluation"
    assert len(evaluation.outcomes) == EVAL_COUNT
    for o in evaluation.outcomes:
        assert o.baseline_tokens >= o.harness_tokens
        assert 0.0 <= o.recall <= 1.0
        assert isinstance(o.task_success, bool)
        assert o.harness_p50_ms >= 0


def test_provenance_identifies_everything(evaluation):
    prov = evaluation.provenance
    for key in ("hardware", "os", "model_versions", "provider",
                "prompt_cache_state", "repository_set", "methodology",
                "generated_at_utc"):
        assert key in prov
    assert set(prov["repository_set"]) == set(FIXTURE_REPO_PATHS.values())
    assert prov["model_versions"]["bundled_coreml_model"] is None
    assert "network" in prov["provider"] or "none" in prov["provider"]
    assert prov["methodology"]["energy"].startswith("not measured")


def test_coreml_arm_is_not_run_behind_p36(evaluation):
    c = evaluation.summary["arms"]["C_harness_coreml"]
    assert c["status"] == "not_run" and c["measured"] is False
    assert "P3.6" in c["blocked_by"]


def test_derived_figures_are_labelled(evaluation):
    asm = evaluation.assumptions
    assert asm["cost_status"].startswith("DERIVED")
    assert asm["ttft_status"].startswith("DERIVED")
    assert evaluation.summary["energy"]["status"] == "not_measured"


def test_recommendation_is_qualified(evaluation):
    reco = evaluation.recommendation
    ane = reco["ane_coreml_value"]
    assert ane["verdict"] == "undetermined"
    assert "P3.6" in ane["reason"]
    assert "P3.6" in ane["next_step"]
    hv = reco["harness_vs_baseline"]
    assert hv["verdict"] in ("adopt", "hold")
    assert hv["qualified_by"]  # never an unqualified claim
    assert "derived" in reco["claims_policy"] or "assumptions" in reco["claims_policy"]


def test_markdown_report_structure(evaluation):
    md = report_markdown(evaluation)
    assert md.startswith("# Phase 5")
    for section in ("## Provenance", "## Assumptions", "## Arms",
                    "## Per-task results", "## Derived analyses",
                    "## Thesis reference gates", "## Metric definitions",
                    "## Recommendation"):
        assert section in md
    assert "not_run" in md and "P3.6" in md
    assert "| task |" in md
    for o in evaluation.outcomes:
        assert o.task_id in md


def test_json_report_and_write_report(evaluation, tmp_path):
    payload = report_json(evaluation)
    assert set(payload) == {"label", "provenance", "assumptions",
                            "metric_definitions", "outcomes",
                            "summary", "recommendation"}
    json.dumps(payload, default=str)
    paths = write_report(evaluation, tmp_path)
    assert (tmp_path / "phase5-ab-evaluation.json").exists()
    assert (tmp_path / "phase5-ab-evaluation.md").exists()
    on_disk = json.loads(open(paths["json"]).read())
    assert on_disk["summary"]["n"] == EVAL_COUNT


def test_metric_definitions_are_embedded(evaluation):
    payload = report_json(evaluation)
    defs = payload["metric_definitions"]
    for key in ("recall_at_k", "ndcg_at_k", "mrr", "required_evidence_recall"):
        assert key in defs and defs[key]


def test_ranking_metrics_and_ranked_chunk_ids(evaluation):
    for o in evaluation.outcomes:
        assert o.ranked_chunk_ids, o.task_id
        for m in (o.recall_at_1, o.recall_at_5, o.recall_at_10,
                  o.ndcg_at_10, o.mrr):
            assert m is not None and 0.0 <= m <= 1.0, (o.task_id, m)
        # recall@k is monotonic in k
        assert o.recall_at_1 <= o.recall_at_5 <= o.recall_at_10
    s = evaluation.summary
    b = s["arms"]["B_harness_deterministic"]
    assert b["mean_recall_at_10"] is not None
    assert 0.0 <= b["mean_ndcg_at_10"] <= 1.0
    assert 0.0 <= b["mean_mrr"] <= 1.0
    assert "macro-mean" in b["ranking_aggregation"]
    # baseline arm states why ranking metrics do not apply
    a = s["arms"]["A_baseline_full_context"]
    assert a["ranking_metrics"]["status"] == "not_applicable"
    assert a["ranking_metrics"]["reason"]


def test_cold_and_warm_reranker_latency_recorded(evaluation):
    b = evaluation.summary["arms"]["B_harness_deterministic"]
    # exactly the first task per arm carries the cold select
    cold = [o for o in evaluation.outcomes if o.select_first_ms is not None]
    assert len(cold) == 1
    assert cold[0].select_first_ms >= 0
    assert b["select_cold_ms_first_task"] is not None
    assert b["reranker_cold_ms_first_task"] is not None
    assert b["reranker_warm_p50_ms"] is not None
    assert b["reranker_fallback_count"] >= 0


def test_aggregation_methods_stated(evaluation):
    agg = evaluation.summary["aggregation_methods"]
    assert "median" in agg["median_*"]
    assert "macro-mean" in agg["mean_*"]
    assert "DERIVED" in agg["cost_*_derived"]


def test_summary_gates_match_thesis_reference(evaluation):
    gates = evaluation.summary["gates_vs_thesis_reference"]
    assert gates["median_reduction_ge_40"] is True
    assert gates["min_recall_ge_0_95"] is True
    assert gates["p50_latency_le_500ms"] is True


def test_summarize_empty_is_safe():
    assert summarize([], 3.0, [2000]) == {"n": 0}
    assert recommend({"n": 0})["ane_coreml_value"]["verdict"] == "undetermined"


def _fake_outcomes(reduction, p50, recall, tokens):
    from src.ane_context_harness.evaluation import TaskOutcome
    return [TaskOutcome(task_id="t1", baseline_tokens=2000, harness_tokens=tokens,
                        reduction_percent=reduction, recall=recall,
                        task_success=recall >= 0.95, helpful_included=1.0,
                        irrelevant_excluded=1.0, baseline_prep_ms=1.0,
                        harness_p50_ms=p50, harness_p95_ms=p50 + 1,
                        latency_samples=[p50], peak_rss_mb=100.0, redactions=0),
            TaskOutcome(task_id="t2", baseline_tokens=3000, harness_tokens=tokens,
                        reduction_percent=reduction, recall=recall,
                        task_success=recall >= 0.95, helpful_included=1.0,
                        irrelevant_excluded=1.0, baseline_prep_ms=1.0,
                        harness_p50_ms=p50, harness_p95_ms=p50 + 1,
                        latency_samples=[p50], peak_rss_mb=100.0, redactions=0)]


def test_arm_c_measured_summary_and_recommendation():
    c_out = _fake_outcomes(reduction=70.0, p50=40.0, recall=1.0, tokens=700)
    meta = {"backend": "coreml_all", "enabled": True,
            "artifact": "cross-encoder/ms-marco-MiniLM-L6-v2@rev", "seq_len": 128}
    s = summarize([c_out[0]], 3.0, [2000], coreml_outcomes=c_out, coreml_meta=meta)
    c = s["arms"]["C_harness_coreml"]
    assert c["status"] == "measured" and c["measured"] is True
    assert c["median_reduction_percent"] == 70.0
    assert c["backend"] == "coreml_all"
    gates = s["gates_vs_thesis_reference_arm_c"]
    assert gates["p50_latency_le_500ms"] is True
    assert gates["min_recall_ge_0_95"] is True
    reco = recommend(s)
    assert reco["ane_coreml_value"]["verdict"] == "supported"
    assert "coreml_all" in reco["ane_coreml_value"]["reason"]


def test_arm_c_measured_but_failing_gates_is_inconclusive():
    c_out = _fake_outcomes(reduction=70.0, p50=600.0, recall=1.0, tokens=700)
    meta = {"backend": "coreml_cpu_gpu", "enabled": True,
            "artifact": "m@r", "seq_len": 128}
    s = summarize(c_out[:1], 3.0, [2000], coreml_outcomes=c_out, coreml_meta=meta)
    assert s["gates_vs_thesis_reference_arm_c"]["p50_latency_le_500ms"] is False
    reco = recommend(s)
    assert reco["ane_coreml_value"]["verdict"] == "inconclusive"


def test_arm_c_not_run_without_pipeline():
    b = _fake_outcomes(reduction=70.0, p50=40.0, recall=1.0, tokens=700)
    s = summarize(b, 3.0, [2000])
    c = s["arms"]["C_harness_coreml"]
    assert c["measured"] is False and "P3.6" in c["blocked_by"]
    assert "gates_vs_thesis_reference_arm_c" not in s
