"""Phase 5: end-to-end A/B evaluation (thesis §16).

Arms:
  A. baseline — full context (every indexed chunk presented to the model),
  B. harness  — deterministic pipeline selection (redaction applied),
  C. harness + Core ML reranker — measured only when a qualified Core ML
     artifact + calibration report are available (P3.6 evidence); otherwise
     reported as NOT RUN behind the P3.6 gate.

Latency and memory figures are measured on this host. Token counts are exact
for the fixtures. Cost and TTFT figures are DERIVED under explicitly stated
assumptions and are never presented as measurements. Every report carries the
required provenance: hardware, OS, model/policy versions, provider, prompt-cache
state, repository set, and methodology (thesis: no unqualified claims).
"""
from __future__ import annotations

import json
import os
import platform as _pf
import statistics as st
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import tokens as tokens_mod
from .benchmark import (DEFAULT_NEVER_READ, BenchmarkTask, FIXTURE_REPO_PATHS,
                        baseline_full_context_tokens, required_chunks_covered)
from .coreml.evaluation import METRIC_DEFINITIONS, relevance_labels
from .platform.discovery import discover
from .telemetry.metrics import Timer, peak_rss_mb

DEFAULT_USD_PER_MILLION_INPUT = 3.00
DEFAULT_PREFILL_RATES = (2000, 8000, 20000)  # tokens/s, illustrative only


@dataclass
class TaskOutcome:
    task_id: str
    baseline_tokens: int
    harness_tokens: int
    reduction_percent: float
    recall: float
    task_success: bool
    helpful_included: float
    irrelevant_excluded: float
    baseline_prep_ms: float
    harness_p50_ms: float
    harness_p95_ms: float
    latency_samples: list
    peak_rss_mb: float | None
    redactions: int
    reranker_backend: str | None = None
    reranker_fallback: bool | None = None
    # Ranking metrics over the package emission order (arm A has no ranking;
    # these are None for baseline-only views). Relevant = required + helpful
    # labels, corpus-wide denominator — see METRIC_DEFINITIONS.
    ranked_chunk_ids: list = field(default_factory=list)
    recall_at_1: float | None = None
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    ndcg_at_10: float | None = None
    mrr: float | None = None
    # Cold vs warm: the first select on a fresh pipeline includes model/facade
    # construction; only the first task per arm records these.
    select_first_ms: float | None = None
    reranker_first_ms: float | None = None
    reranker_warm_p50_ms: float | None = None


@dataclass
class EvaluationReport:
    label: str
    provenance: dict
    assumptions: dict
    outcomes: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    recommendation: dict = field(default_factory=dict)


def cost_usd(tokens: int, usd_per_million: float) -> float:
    """Derived input-token cost under a stated price assumption."""
    return round(tokens * usd_per_million / 1_000_000, 6)


def ttft_sensitivity_ms(token_delta: int, prefill_rates) -> dict:
    """Derived TTFT reduction for dropping ``token_delta`` input tokens at the
    given illustrative prefill rates. Not a measurement."""
    return {str(rate): round(abs(token_delta) / rate * 1000, 2)
            for rate in prefill_rates}


def _label_rate(haystack: list, labels: list) -> float:
    if not labels:
        return 1.0
    hits = sum(1 for lab in labels
               if any(lab.get("path") == e.get("path") for e in haystack))
    return hits / len(labels)


def _percentile(samples: list, pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def _dcg_binary(rel: list, k: int) -> float:
    """Binary-gain DCG: sum of 1/log2(rank+1) over relevant items in top k."""
    import math
    return sum(1.0 / math.log2(i + 2) for i, r in enumerate(rel[:k]) if r)


def package_ranking_metrics(evidence: list, chunks: list, task) -> dict:
    """Ranking quality of the PACKAGE emission order against corpus labels.

    The ranking is the order evidence is presented in (category-stable, then
    score descending). Recall@k uses the corpus-wide relevant total as the
    denominator, so unselected relevant chunks stay misses; nDCG@10 compares
    against the ideal order of ALL corpus labels (unselected relevant rank
    after everything selected). Relevant = required + helpful (METRIC_DEFINITIONS).
    """
    labels = relevance_labels(chunks, task)
    idx_by = {(c.path, c.start_line): i for i, c in enumerate(chunks)}
    ranked_idx, ids = [], []
    for e in evidence:
        i = idx_by.get((e["path"], e["start_line"]))
        if i is None:
            continue
        ranked_idx.append(i)
        ids.append(f"{e['path']}:{e['start_line']}-{e['end_line']}"
                   if e.get("end_line") else f"{e['path']}:{e['start_line']}")
    rel = [labels[i] for i in ranked_idx]
    total_rel = sum(labels)
    out = {"ranked_chunk_ids": ids}
    for k in (1, 5, 10):
        hits = sum(rel[:k])
        out[f"recall_at_{k}"] = round(hits / total_rel, 4) if total_rel else 1.0
    idcg = _dcg_binary(sorted(labels, reverse=True), 10)
    out["ndcg_at_10"] = round(_dcg_binary(rel, 10) / idcg, 4) if idcg > 0 else 0.0
    mrr = 0.0
    for pos, r in enumerate(rel, start=1):
        if r:
            mrr = 1.0 / pos
            break
    out["mrr"] = round(mrr, 4)
    return out


def _task_outcome(task: BenchmarkTask, pipeline, repeats: int, warmup: int,
                  run_state: dict | None = None) -> TaskOutcome:
    from . import schemas
    # Path hints are OFF by default: passing required paths as explicit_paths
    # would force-include them (mandatory) and make required-evidence recall
    # trivial. A task opts in with "use_explicit_path_hints": true.
    hints = bool(getattr(task, "use_explicit_path_hints", False))
    req = schemas.SelectRequest(
        repository_id=task.repository_id,
        task=task.task,
        token_budget=task.token_budget,
        explicit_paths=[rc.get("path") for rc in task.required_chunks] if hints else [],
    )
    storage = pipeline._storage_for(task.repository_id)
    chunks = storage.load_chunks()
    baseline_tokens = baseline_full_context_tokens(chunks)

    with Timer("baseline") as t_base:
        "\n\n".join(c.content for c in chunks)
    baseline_prep_ms = t_base.elapsed_ms

    # Cold select: the first call on a fresh pipeline includes lazy facade /
    # model construction. Recorded only for the first task of an arm; every
    # later task's select is warm by construction and stays None here.
    select_first_ms = reranker_first_ms = None
    if run_state is not None and run_state.get("first", True):
        run_state["first"] = False
        with Timer("cold") as t_cold:
            first_pkg = pipeline.select_context(req)
        select_first_ms = round(t_cold.elapsed_ms, 2)
        reranker_first_ms = round(
            ((first_pkg.metrics or {}).get("stage_ms") or {}).get("reranker_ms", 0.0), 2)

    for _ in range(warmup):
        pipeline.select_context(req)

    samples, warm_rerank, pkg = [], [], None
    for _ in range(repeats):
        with Timer("harness") as t_h:
            pkg = pipeline.select_context(req)
        samples.append(t_h.elapsed_ms)
        rr = ((pkg.metrics or {}).get("stage_ms") or {}).get("reranker_ms")
        if rr is not None:
            warm_rerank.append(rr)

    harness_tokens = sum(tokens_mod.count(e["content"]) for e in pkg.evidence)
    reduction = (round((baseline_tokens - harness_tokens) / baseline_tokens * 100, 2)
                 if baseline_tokens else 0.0)
    recall = required_chunks_covered(pkg.evidence, task.required_chunks, chunks) \
        if task.required_chunks else 1.0
    helpful = _label_rate(pkg.evidence, task.helpful_chunks)
    irrelevant = 1.0 - _label_rate(pkg.evidence, task.irrelevant_chunks)
    redactions = int((pkg.redaction_summary or {}).get("count", 0)) \
        if isinstance(pkg.redaction_summary, dict) else 0
    execution = getattr(pkg, "execution", None) or {}
    rank = package_ranking_metrics(pkg.evidence, chunks, task)
    return TaskOutcome(
        task_id=task.task_id,
        baseline_tokens=baseline_tokens,
        harness_tokens=harness_tokens,
        reduction_percent=reduction,
        recall=round(recall, 4),
        task_success=recall >= 0.95,
        helpful_included=round(helpful, 4),
        irrelevant_excluded=round(irrelevant, 4),
        baseline_prep_ms=round(baseline_prep_ms, 2),
        harness_p50_ms=round(st.median(samples), 2),
        harness_p95_ms=_percentile(samples, 95),
        latency_samples=[round(s, 2) for s in samples],
        peak_rss_mb=peak_rss_mb(),
        redactions=redactions,
        reranker_backend=execution.get("reranker"),
        reranker_fallback=execution.get("fallback_used"),
        ranked_chunk_ids=rank["ranked_chunk_ids"],
        recall_at_1=rank["recall_at_1"],
        recall_at_5=rank["recall_at_5"],
        recall_at_10=rank["recall_at_10"],
        ndcg_at_10=rank["ndcg_at_10"],
        mrr=rank["mrr"],
        select_first_ms=select_first_ms,
        reranker_first_ms=reranker_first_ms,
        reranker_warm_p50_ms=(round(st.median(warm_rerank), 2)
                              if warm_rerank else None),
    )


def _provenance(label: str, repo_paths: dict, repeats: int, warmup: int,
                methodology_extra: dict) -> dict:
    disc = discover()
    return {
        "label": label,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": {
            "architecture": disc["hardware"]["architecture"],
            "is_apple_silicon": disc["hardware"]["is_apple_silicon"],
            "unified_memory_bytes": disc["hardware"]["unified_memory_bytes"],
            "machine": _pf.machine(),
            "chip_model": "not reported by stdlib discovery",
        },
        "os": {
            "platform": _pf.platform(),
            "macos_version": disc["software"]["macos_version"],
            "python_version": _pf.python_version(),
        },
        "model_versions": {
            "service": methodology_extra.get("service_version", "phase5-eval"),
            "policy": methodology_extra.get("policy_version"),
            "index": methodology_extra.get("index_version"),
            "reranker_backend": "cpu_deterministic",
            "coreml_arm_backend": (methodology_extra.get("coreml_arm") or {}).get("backend"),
            "bundled_coreml_model": (methodology_extra.get("coreml_arm") or {}).get("artifact"),
        },
        "provider": "none invoked (local evaluation; no network)",
        "prompt_cache_state": (
            "local evaluation — no provider prompt cache involved; index built "
            "once into a fresh temp store (cold index), OS page cache not flushed"),
        "repository_set": sorted(repo_paths.values()),
        "methodology": {
            "repeats": repeats,
            "warmup_runs_excluded": warmup,
            "clock": "time.perf_counter via telemetry.metrics.Timer",
            "memory": "peak_rss_mb (process peak resident set)",
            "energy": "not measured (requires elevated privileges; not attempted)",
            **methodology_extra,
        },
    }


def run_evaluation(tasks: list, pipeline, repo_paths: dict, *, repeats: int = 5,
                   warmup: int = 1,
                   usd_per_million: float = DEFAULT_USD_PER_MILLION_INPUT,
                   prefill_rates=DEFAULT_PREFILL_RATES,
                   coreml_pipeline=None) -> EvaluationReport:
    """Run the A/B evaluation. Arm C executes only when a ``coreml_pipeline``
    (configured with a qualified calibration report + artifact) is supplied."""
    outcomes = []
    from .pipeline import POLICY_VERSION, SERVICE_VERSION
    index_version = None
    state_b = {"first": True}  # tracks the cold select of arm B
    for task in tasks:
        pipeline.register_repository(repo_paths[task.repository_id],
                                     task.repository_id, False)
        if index_version is None:
            index_version = pipeline._storage_for(task.repository_id).index_version()
        outcomes.append(_task_outcome(task, pipeline, repeats, warmup, state_b))

    coreml_outcomes = None
    coreml_meta = None
    if coreml_pipeline is not None:
        coreml_outcomes = []
        state_c = {"first": True}  # cold select of arm C on its own fresh pipeline
        for task in tasks:
            coreml_pipeline.register_repository(repo_paths[task.repository_id],
                                                task.repository_id, False)
            coreml_outcomes.append(_task_outcome(task, coreml_pipeline, repeats,
                                                 warmup, state_c))
        feat = coreml_pipeline._profile().get("features", {}).get("reranker", {})
        art = coreml_pipeline._reranker_artifact()
        observed = sorted({o.reranker_backend for o in coreml_outcomes
                           if o.reranker_backend})
        coreml_meta = {
            "backend": feat.get("backend"),
            "enabled": feat.get("enabled"),
            "backend_observed": observed,
            "fallback_count": sum(1 for o in coreml_outcomes if o.reranker_fallback),
            "artifact": (f"{art.model_id}@{art.revision}" if art else None),
            "seq_len": art.seq_len if art else None,
        }

    methodology = {
        "policy_version": POLICY_VERSION,
        "index_version": index_version,
        "service_version": SERVICE_VERSION,
    }
    if coreml_meta is not None:
        methodology["coreml_arm"] = coreml_meta
    prov = _provenance("phase5-ab-evaluation", repo_paths, repeats, warmup, methodology)
    assumptions = {
        "cost_usd_per_million_input_tokens": usd_per_million,
        "cost_status": "DERIVED from token counts under the stated price; not a billed amount",
        "prefill_rates_tps": list(prefill_rates),
        "ttft_status": "DERIVED token-delta sensitivity; no model was invoked, "
                       "TTFT was not measured",
        "baseline_arm": "full context = every indexed chunk concatenated; "
                        "preparation latency measured, inference not run",
    }
    report = EvaluationReport(label="phase5-ab-evaluation", provenance=prov,
                              assumptions=assumptions, outcomes=outcomes)
    report.summary = summarize(outcomes, usd_per_million, prefill_rates,
                               coreml_outcomes=coreml_outcomes,
                               coreml_meta=coreml_meta)
    report.recommendation = recommend(report.summary)
    return report


def _arm_c_block(coreml_outcomes: list, coreml_meta: dict | None,
                 usd_per_million: float) -> tuple[dict, dict | None]:
    """Arm C summary + its thesis-reference gates (or the not-run block)."""
    if not coreml_outcomes:
        return ({"status": "not_run",
                 "blocked_by": "P3.6 on-device hardware validation",
                 "measured": False}, None)
    reductions = [o.reduction_percent for o in coreml_outcomes]
    recalls = [o.recall for o in coreml_outcomes]
    h_p50 = [o.harness_p50_ms for o in coreml_outcomes]
    h_tokens = [o.harness_tokens for o in coreml_outcomes]
    rss = [o.peak_rss_mb for o in coreml_outcomes if o.peak_rss_mb is not None]
    gates = {
        "median_reduction_ge_40": round(st.median(reductions), 2) >= 40.0,
        "min_recall_ge_0_95": min(recalls) >= 0.95,
        "p50_latency_le_500ms": round(st.median(h_p50), 2) <= 500.0,
    }
    block = {
        "status": "measured",
        "measured": True,
        "median_tokens": int(st.median(h_tokens)),
        "total_tokens": sum(h_tokens),
        "median_reduction_percent": round(st.median(reductions), 2),
        "min_reduction_percent": round(min(reductions), 2),
        "median_latency_ms": round(st.median(h_p50), 2),
        "p95_latency_ms": _percentile(h_p50, 95),
        "task_success_rate": round(sum(o.task_success for o in coreml_outcomes)
                                   / len(coreml_outcomes), 4),
        "median_recall": round(st.median(recalls), 4),
        "min_recall": round(min(recalls), 4),
        "median_cost_usd_derived": cost_usd(int(st.median(h_tokens)), usd_per_million),
        "peak_rss_mb_max": max(rss) if rss else None,
        "gates_vs_thesis_reference": gates,
        "backend": (coreml_meta or {}).get("backend"),
        "artifact": (coreml_meta or {}).get("artifact"),
        "coreml_arm": coreml_meta,
        **_ranking_block(coreml_outcomes),
    }
    return block, gates


def _ranking_block(outcomes: list) -> dict:
    """Ranking metrics + cold/warm reranker figures for one arm.

    Means are macro-averages over tasks (each task weighted equally); min_*
    are minima over tasks; the cold/warm pair reports the first task of the
    arm (only that select is cold) and the median of per-task warm p50s.
    """
    def mean(get):
        vals = [get(o) for o in outcomes if get(o) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    def mn(get):
        vals = [get(o) for o in outcomes if get(o) is not None]
        return round(min(vals), 4) if vals else None
    cold_sel = next((o.select_first_ms for o in outcomes
                     if o.select_first_ms is not None), None)
    cold_rr = next((o.reranker_first_ms for o in outcomes
                    if o.reranker_first_ms is not None), None)
    warm_rr = [o.reranker_warm_p50_ms for o in outcomes
               if o.reranker_warm_p50_ms is not None]
    return {
        "mean_recall_at_1": mean(lambda o: o.recall_at_1),
        "mean_recall_at_5": mean(lambda o: o.recall_at_5),
        "mean_recall_at_10": mean(lambda o: o.recall_at_10),
        "min_recall_at_10": mn(lambda o: o.recall_at_10),
        "mean_ndcg_at_10": mean(lambda o: o.ndcg_at_10),
        "mean_mrr": mean(lambda o: o.mrr),
        "ranking_aggregation": "macro-mean over tasks; min_* are minima over tasks",
        "ranking_relevance": "required + helpful labels (METRIC_DEFINITIONS)",
        "select_cold_ms_first_task": cold_sel,
        "reranker_cold_ms_first_task": cold_rr,
        "reranker_warm_p50_ms": (round(st.median(warm_rr), 2)
                                 if warm_rr else None),
        "reranker_fallback_count": sum(1 for o in outcomes
                                       if o.reranker_fallback),
    }


AGGREGATION_METHODS = {
    "reduction_percent": "per task: (baseline_tokens - harness_tokens) / "
                         "baseline_tokens * 100, then aggregated as named below",
    "median_*": "median over the tasks of the evaluated split",
    "mean_*": "macro-mean over the tasks of the evaluated split "
              "(each task weighted equally)",
    "min_*": "minimum over the tasks of the evaluated split",
    "total_*": "sum over the tasks of the evaluated split",
    "rate_*_success": "fraction of tasks meeting the predicate",
    "cost_*_derived": "DERIVED from token counts × the stated price; not billed",
}


def summarize(outcomes: list, usd_per_million: float, prefill_rates,
              coreml_outcomes: list | None = None,
              coreml_meta: dict | None = None) -> dict:
    if not outcomes:
        return {"n": 0}
    reductions = [o.reduction_percent for o in outcomes]
    recalls = [o.recall for o in outcomes]
    h_p50 = [o.harness_p50_ms for o in outcomes]
    b_tokens = [o.baseline_tokens for o in outcomes]
    h_tokens = [o.harness_tokens for o in outcomes]
    rss = [o.peak_rss_mb for o in outcomes if o.peak_rss_mb is not None]
    med_b = int(st.median(b_tokens))
    med_h = int(st.median(h_tokens))
    token_delta = med_b - med_h
    c_block, c_gates = _arm_c_block(coreml_outcomes, coreml_meta,
                                    usd_per_million)
    summary = {
        "n": len(outcomes),
        "aggregation_methods": dict(AGGREGATION_METHODS),
        "arms": {
            "A_baseline_full_context": {
                "median_tokens": med_b,
                "total_tokens": sum(b_tokens),
                "median_prep_ms": round(st.median([o.baseline_prep_ms for o in outcomes]), 2),
                "task_success_rate": 1.0,
                "median_cost_usd_derived": cost_usd(med_b, usd_per_million),
                "ranking_metrics": {
                    "status": "not_applicable",
                    "reason": "full context includes every indexed chunk; "
                              "the baseline emits no ranking to score",
                },
            },
            "B_harness_deterministic": {
                "median_tokens": med_h,
                "total_tokens": sum(h_tokens),
                "median_reduction_percent": round(st.median(reductions), 2),
                "min_reduction_percent": round(min(reductions), 2),
                "median_latency_ms": round(st.median(h_p50), 2),
                "p95_latency_ms": _percentile(h_p50, 95),
                "task_success_rate": round(sum(o.task_success for o in outcomes) / len(outcomes), 4),
                "median_recall": round(st.median(recalls), 4),
                "min_recall": round(min(recalls), 4),
                "median_cost_usd_derived": cost_usd(med_h, usd_per_million),
                "peak_rss_mb_max": max(rss) if rss else None,
                **_ranking_block(outcomes),
            },
            "C_harness_coreml": c_block,
        },
        "cost_delta_usd_per_task_median_derived": round(
            cost_usd(med_b, usd_per_million) - cost_usd(med_h, usd_per_million), 6),
        "ttft_sensitivity_derived_ms": ttft_sensitivity_ms(token_delta, prefill_rates),
        "memory": {"peak_rss_mb_max": max(rss) if rss else None, "status": "measured"},
        "energy": {"status": "not_measured",
                   "reason": "macOS energy counters require elevated privileges; not attempted"},
        "gates_vs_thesis_reference": {
            "median_reduction_ge_40": round(st.median(reductions), 2) >= 40.0,
            "min_recall_ge_0_95": min(recalls) >= 0.95,
            "p50_latency_le_500ms": round(st.median(h_p50), 2) <= 500.0,
        },
    }
    if c_gates is not None:
        summary["gates_vs_thesis_reference_arm_c"] = c_gates
    return summary


def recommend(summary: dict) -> dict:
    gates = summary.get("gates_vs_thesis_reference", {})
    harness_ok = all(gates.values()) if gates else False
    arms = summary.get("arms", {})
    c = arms.get("C_harness_coreml", {})
    if c.get("measured"):
        cgates = summary.get("gates_vs_thesis_reference_arm_c") or c.get(
            "gates_vs_thesis_reference") or {}
        c_ok = all(cgates.values()) if cgates else False
        ane = {
            "verdict": "supported" if c_ok else "inconclusive",
            "reason": (
                f"Arm C measured on-device with backend "
                f"{c.get('backend') or 'coreml'} (artifact {c.get('artifact')}): "
                f"median token reduction {c.get('median_reduction_percent')}%, "
                f"p50 select latency {c.get('median_latency_ms')} ms, "
                f"min recall {c.get('min_recall')}; "
                + ("all arm C thesis-reference gates pass"
                   if c_ok else
                   "one or more arm C thesis-reference gates fail: "
                   + json.dumps(cgates))),
            "next_step": (
                "adopt the qualified Core ML reranker for this host"
                if c_ok else
                "investigate the failing arm C gate(s) before adopting the "
                "Core ML reranker"),
        }
    else:
        ane = {
            "verdict": "undetermined",
            "reason": "Arm C not executed: no qualified Core ML calibration "
                      "report (P3.6 evidence: build on Python <= 3.13, "
                      ">=1000-pair numerical agreement, .all/CPU+GPU/CPU-only "
                      "benchmarks vs the <=500 ms warm-p50 gate) is available "
                      "on this host.",
            "next_step": "run scripts/calibrate_phase3.py under Python <= 3.13 "
                         "to produce the P3.6 calibration report, then re-run "
                         "this evaluation with arm C enabled",
        }
    return {
        "harness_vs_baseline": {
            "verdict": "adopt" if harness_ok else "hold",
            "gates": gates,
            "evidence": [
                f"median token reduction {summary.get('arms', {}).get('B_harness_deterministic', {}).get('median_reduction_percent')}%",
                f"min required-evidence recall {summary.get('arms', {}).get('B_harness_deterministic', {}).get('min_recall')}",
                f"median select latency {summary.get('arms', {}).get('B_harness_deterministic', {}).get('median_latency_ms')} ms",
            ],
            "qualified_by": "synthetic fixture repositories on this host; "
                            "no live model invocation in this run",
        },
        "ane_coreml_value": ane,
        "claims_policy": "all latency/memory figures measured on this host; "
                         "cost and TTFT figures derived under stated assumptions; "
                         "no ANE or provider-performance claim is made",
    }


def report_json(report: EvaluationReport) -> dict:
    return {
        "label": report.label,
        "provenance": report.provenance,
        "assumptions": report.assumptions,
        "metric_definitions": dict(METRIC_DEFINITIONS),
        "outcomes": [o.__dict__ for o in report.outcomes],
        "summary": report.summary,
        "recommendation": report.recommendation,
    }


def report_markdown(report: EvaluationReport) -> str:
    s, r, prov, asm = report.summary, report.recommendation, report.provenance, report.assumptions
    arms = s.get("arms", {})
    a, b, c = (arms.get("A_baseline_full_context", {}),
               arms.get("B_harness_deterministic", {}),
               arms.get("C_harness_coreml", {}))
    lines = ["# Phase 5 — A/B end-to-end evaluation report", ""]
    lines += [f"**Generated:** {prov['generated_at_utc']} | "
              f"**Label:** `{prov['label']}`", ""]
    lines += ["## Provenance", ""]
    lines.append(f"- Hardware: {prov['hardware']['architecture']} "
                 f"(Apple Silicon: {prov['hardware']['is_apple_silicon']}), "
                 f"unified memory {prov['hardware']['unified_memory_bytes'] // (1 << 30)} GiB, "
                 f"chip model: {prov['hardware']['chip_model']}")
    lines.append(f"- OS/Python: {prov['os']['platform']}, macOS {prov['os']['macos_version']}, "
                 f"Python {prov['os']['python_version']}")
    lines.append(f"- Model versions: {json.dumps(prov['model_versions'])}")
    lines.append(f"- Provider: {prov['provider']}")
    lines.append(f"- Prompt-cache state: {prov['prompt_cache_state']}")
    lines.append(f"- Repository set: {', '.join(prov['repository_set'])}")
    lines.append(f"- Methodology: {json.dumps(prov['methodology'])}")
    lines += ["", "## Assumptions (derived figures only)", ""]
    lines.append(f"- {asm['cost_status']} @ "
                 f"${asm['cost_usd_per_million_input_tokens']}/M input tokens")
    lines.append(f"- {asm['ttft_status']} at illustrative prefill rates "
                 f"{asm['prefill_rates_tps']} tok/s")
    lines.append(f"- Baseline arm: {asm['baseline_arm']}")
    lines += ["", "## Arms", ""]
    lines.append(f"- **A — baseline (full context):** median {a.get('median_tokens')} tokens, "
                 f"prep {a.get('median_prep_ms')} ms, derived cost "
                 f"${a.get('median_cost_usd_derived')}/task; "
                 f"ranking metrics: {a.get('ranking_metrics', {}).get('status', 'n/a')}")
    lines.append(f"- **B — harness (deterministic):** median {b.get('median_tokens')} tokens "
                 f"({b.get('median_reduction_percent')}% median reduction), latency "
                 f"p50 {b.get('median_latency_ms')} ms / p95 {b.get('p95_latency_ms')} ms, "
                 f"recall min {b.get('min_recall')}, derived cost "
                 f"${b.get('median_cost_usd_derived')}/task; ranking "
                 f"R@10 mean {b.get('mean_recall_at_10')}, nDCG@10 mean "
                 f"{b.get('mean_ndcg_at_10')}, MRR mean {b.get('mean_mrr')}; "
                 f"reranker cold {b.get('reranker_cold_ms_first_task')} ms (first task) / "
                 f"warm p50 {b.get('reranker_warm_p50_ms')} ms, fallbacks "
                 f"{b.get('reranker_fallback_count')}")
    if c.get("measured"):
        lines.append(f"- **C — harness + Core ML ({c.get('backend')}):** "
                     f"median {c.get('median_tokens')} tokens "
                     f"({c.get('median_reduction_percent')}% median reduction), latency "
                     f"p50 {c.get('median_latency_ms')} ms / p95 {c.get('p95_latency_ms')} ms, "
                     f"recall min {c.get('min_recall')}, derived cost "
                     f"${c.get('median_cost_usd_derived')}/task, artifact "
                     f"`{c.get('artifact')}`; ranking "
                     f"R@10 mean {c.get('mean_recall_at_10')}, nDCG@10 mean "
                     f"{c.get('mean_ndcg_at_10')}, MRR mean {c.get('mean_mrr')}; "
                     f"reranker cold {c.get('reranker_cold_ms_first_task')} ms (first task) / "
                     f"warm p50 {c.get('reranker_warm_p50_ms')} ms, fallbacks "
                     f"{c.get('reranker_fallback_count')}")
    else:
        lines.append(f"- **C — harness + Core ML:** {c.get('status')} — blocked by "
                     f"{c.get('blocked_by')}")
    lines += ["", "## Per-task results", ""]
    lines.append("| task | baseline tokens | harness tokens | reduction % | recall | "
                 "R@10 | nDCG@10 | MRR | success | p50 ms |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for o in report.outcomes:
        lines.append(f"| {o.task_id} | {o.baseline_tokens} | {o.harness_tokens} | "
                     f"{o.reduction_percent} | {o.recall} | {o.recall_at_10} | "
                     f"{o.ndcg_at_10} | {o.mrr} | "
                     f"{'yes' if o.task_success else 'no'} | {o.harness_p50_ms} |")
    lines += ["", "## Derived analyses", ""]
    lines.append(f"- Aggregation methods: "
                 f"`{json.dumps(s.get('aggregation_methods', {}))}`")
    lines.append(f"- Cost delta (median/task, derived): "
                 f"${s.get('cost_delta_usd_per_task_median_derived')}")
    lines.append(f"- TTFT sensitivity (derived, token-delta at illustrative rates): "
                 f"`{json.dumps(s.get('ttft_sensitivity_derived_ms'))}`")
    lines.append(f"- Memory: {json.dumps(s.get('memory'))}")
    lines.append(f"- Energy: {json.dumps(s.get('energy'))}")
    lines += ["", "## Thesis reference gates", ""]
    for k, v in s.get("gates_vs_thesis_reference", {}).items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    cg = s.get("gates_vs_thesis_reference_arm_c")
    if cg:
        lines.append("- arm C (Core ML):")
        for k, v in cg.items():
            lines.append(f"  - {k}: {'PASS' if v else 'FAIL'}")
    lines += ["", "## Metric definitions", ""]
    for name, definition in METRIC_DEFINITIONS.items():
        lines.append(f"- **{name}**: {definition}")
    lines.append("- Ranking metrics are scored on the package emission order "
                 "(category-stable, then score descending); arm A presents full "
                 "context and emits no ranking, so its ranking metrics are not "
                 "applicable. `ranked_chunk_ids` for every task and arm B/C is "
                 "in the JSON report.")
    lines += ["", "## Recommendation", ""]
    hv = r["harness_vs_baseline"]
    lines.append(f"- Harness vs baseline: **{hv['verdict']}** — {', '.join(hv['evidence'])} "
                 f"(qualified by: {hv['qualified_by']})")
    ane = r["ane_coreml_value"]
    lines.append(f"- ANE/Core ML value: **{ane['verdict']}** — {ane['reason']}")
    lines.append(f"- Next step: {ane['next_step']}")
    lines.append(f"- Claims policy: {r['claims_policy']}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: EvaluationReport, out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{report.label}.json"
    md_path = out / f"{report.label}.md"
    json_path.write_text(json.dumps(report_json(report), indent=2, default=str),
                         encoding="utf-8")
    md_path.write_text(report_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _build_coreml_pipeline():
    """Arm C pipeline: qualified calibration report + built artifact, else None."""
    from .config import build_config
    from .pipeline import Pipeline

    try:
        import coremltools  # noqa: F401
    except ImportError:
        print("arm C: not run — coremltools unavailable on this interpreter "
              "(run under Python <= 3.13 with '.[build]' installed)")
        return None
    storage_base = os.path.expanduser("~/.ane_context_harness")
    cal_report = os.path.join(storage_base, "calibration_report.json")
    if not os.path.exists(cal_report):
        return None
    try:
        with open(cal_report, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    reranker = (data.get("measurements") or {}).get("reranker") or {}
    if not (reranker.get("enabled")
            and str(reranker.get("backend", "")).startswith("coreml")):
        return None
    artifacts = os.path.join(storage_base, "phase3", "build_cache", "artifacts")
    art_path = None
    if os.path.isdir(artifacts):
        for name in sorted(os.listdir(artifacts)):
            if name.endswith("_128tok_v1"):
                art_path = os.path.join(artifacts, name)
    if not art_path or not os.path.isdir(art_path):
        return None
    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp(prefix="aneh-armc-")},
        "privacy": {"never_read": ["**/.env*", "**/.aws/**", "**/.ssh/**",
                                   "**/*.pem", "**/.EnvLocal"]},
        "coreml": {"calibration_report": cal_report, "artifact_path": art_path},
    })
    return Pipeline(cfg)


def main() -> dict:
    """Entry point used by scripts/run_phase5.py (frozen eval split)."""
    from .config import build_config
    from .pipeline import Pipeline

    repo_paths = dict(FIXTURE_REPO_PATHS)
    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp()},
        "privacy": {"never_read": list(DEFAULT_NEVER_READ)},
    })
    pipeline = Pipeline(cfg)
    # Reports run on the FROZEN eval split only; dev exists for tuning and
    # must never appear in reported figures.
    from .benchmark import load_task_split
    tasks = load_task_split("eval")
    coreml_pipeline = _build_coreml_pipeline()
    report = run_evaluation(tasks, pipeline, repo_paths, repeats=5, warmup=1,
                            coreml_pipeline=coreml_pipeline)
    paths = write_report(report, "benchmarks/reports")
    print(f"split: eval ({len(tasks)} tasks, benchmarks/splits.json)")
    print(json.dumps(report.summary, indent=2, default=str))
    print(json.dumps(report.recommendation, indent=2, default=str))
    print(f"\nReports written: {paths}")
    if coreml_pipeline is None:
        print("arm C: not run (no qualified calibration report/artifact)")
    return report.summary
