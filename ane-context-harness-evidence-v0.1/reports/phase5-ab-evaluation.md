# Phase 5 — A/B end-to-end evaluation report

**Generated:** 2026-10-02T08:07:23Z | **Label:** `phase5-ab-evaluation`

## Provenance

- Hardware: arm64 (Apple Silicon: True), unified memory 8 GiB, chip model: not reported by stdlib discovery
- OS/Python: macOS-26.5-arm64-arm-64bit-Mach-O, macOS 26.5, Python 3.13.15
- Model versions: {"service": "0.2.0-phase0-2", "policy": "phase0-2-deterministic+rules", "index": "1", "reranker_backend": "cpu_deterministic", "coreml_arm_backend": "coreml_all", "bundled_coreml_model": "cross-encoder/ms-marco-MiniLM-L6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a"}
- Provider: none invoked (local evaluation; no network)
- Prompt-cache state: local evaluation — no provider prompt cache involved; index built once into a fresh temp store (cold index), OS page cache not flushed
- Repository set: tests/fixtures/synthetic_hard_project, tests/fixtures/synthetic_py_project, tests/fixtures/synthetic_ts_project
- Methodology: {"repeats": 5, "warmup_runs_excluded": 1, "clock": "time.perf_counter via telemetry.metrics.Timer", "memory": "peak_rss_mb (process peak resident set)", "energy": "not measured (requires elevated privileges; not attempted)", "policy_version": "phase0-2-deterministic+rules", "index_version": "1", "service_version": "0.2.0-phase0-2", "coreml_arm": {"backend": "coreml_all", "enabled": true, "backend_observed": ["coreml_all"], "fallback_count": 0, "artifact": "cross-encoder/ms-marco-MiniLM-L6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a", "seq_len": 128}}

## Assumptions (derived figures only)

- DERIVED from token counts under the stated price; not a billed amount @ $3.0/M input tokens
- DERIVED token-delta sensitivity; no model was invoked, TTFT was not measured at illustrative prefill rates [2000, 8000, 20000] tok/s
- Baseline arm: full context = every indexed chunk concatenated; preparation latency measured, inference not run

## Arms

- **A — baseline (full context):** median 3213 tokens, prep 0.01 ms, derived cost $0.009639/task; ranking metrics: not_applicable
- **B — harness (deterministic):** median 782 tokens (60.47% median reduction), latency p50 3.83 ms / p95 8.67 ms, recall min 1.0, derived cost $0.002346/task; ranking R@10 mean 0.9306, nDCG@10 mean 0.8491, MRR mean 0.9074; reranker cold 0.0 ms (first task) / warm p50 0.0 ms, fallbacks 0
- **C — harness + Core ML (coreml_all):** median 782 tokens (60.52% median reduction), latency p50 31.34 ms / p95 33.88 ms, recall min 0.0, derived cost $0.002346/task, artifact `cross-encoder/ms-marco-MiniLM-L6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a`; ranking R@10 mean 0.875, nDCG@10 mean 0.781, MRR mean 0.8241; reranker cold 125.78 ms (first task) / warm p50 27.06 ms, fallbacks 0

## Per-task results

| task | baseline tokens | harness tokens | reduction % | recall | R@10 | nDCG@10 | MRR | success | p50 ms |
|---|---|---|---|---|---|---|---|---|---|
| hard-apply-discount-001 | 3213 | 1547 | 51.85 | 1.0 | 1.0 | 0.906 | 1.0 | yes | 4.46 |
| hard-buried-quote-001 | 3213 | 1459 | 54.59 | 1.0 | 1.0 | 0.818 | 1.0 | yes | 3.45 |
| hard-cart-apply-001 | 3213 | 2146 | 33.21 | 1.0 | 1.0 | 0.7487 | 0.5 | yes | 4.38 |
| hard-doc-concession-001 | 3213 | 1820 | 43.36 | 1.0 | 1.0 | 0.8772 | 1.0 | yes | 5.65 |
| hard-rules-vs-readme-001 | 3213 | 445 | 86.15 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 4.22 |
| hard-settings-001 | 3213 | 311 | 90.32 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 3.88 |
| hard-similarnames-001 | 3213 | 1535 | 52.23 | 1.0 | 1.0 | 0.8772 | 1.0 | yes | 3.41 |
| hard-stock-clearance-001 | 3213 | 1251 | 61.06 | 1.0 | 1.0 | 0.8503 | 1.0 | yes | 22.78 |
| hard-types-line-001 | 3213 | 720 | 77.59 | 1.0 | 0.5 | 0.3066 | 0.3333 | yes | 3.78 |
| hard-vat-apply-001 | 3213 | 1350 | 57.98 | 1.0 | 0.5 | 0.6131 | 1.0 | yes | 5.81 |
| py-calculator-001 | 3189 | 844 | 73.53 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 5.22 |
| py-discount-001 | 3189 | 1112 | 65.13 | 1.0 | 0.75 | 0.7366 | 1.0 | yes | 3.46 |
| py-discount-report-001 | 3189 | 629 | 80.28 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 3.72 |
| py-inventory-sku-001 | 3189 | 606 | 81.0 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 8.67 |
| ts-discount-001 | 1236 | 369 | 70.15 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 1.84 |
| ts-inventory-reconcile-001 | 1236 | 583 | 52.83 | 1.0 | 1.0 | 1.0 | 1.0 | yes | 2.57 |
| ts-math-total-001 | 1236 | 643 | 47.98 | 1.0 | 1.0 | 0.9197 | 1.0 | yes | 2.0 |
| ts-reporting-stats-001 | 1236 | 496 | 59.87 | 1.0 | 1.0 | 0.6309 | 0.5 | yes | 2.65 |

## Derived analyses

- Aggregation methods: `{"reduction_percent": "per task: (baseline_tokens - harness_tokens) / baseline_tokens * 100, then aggregated as named below", "median_*": "median over the tasks of the evaluated split", "mean_*": "macro-mean over the tasks of the evaluated split (each task weighted equally)", "min_*": "minimum over the tasks of the evaluated split", "total_*": "sum over the tasks of the evaluated split", "rate_*_success": "fraction of tasks meeting the predicate", "cost_*_derived": "DERIVED from token counts \u00d7 the stated price; not billed"}`
- Cost delta (median/task, derived): $0.007293
- TTFT sensitivity (derived, token-delta at illustrative rates): `{"2000": 1215.5, "8000": 303.88, "20000": 121.55}`
- Memory: {"peak_rss_mb_max": 210.515625, "status": "measured"}
- Energy: {"status": "not_measured", "reason": "macOS energy counters require elevated privileges; not attempted"}

## Thesis reference gates

- median_reduction_ge_40: PASS
- min_recall_ge_0_95: PASS
- p50_latency_le_500ms: PASS
- arm C (Core ML):
  - median_reduction_ge_40: PASS
  - min_recall_ge_0_95: FAIL
  - p50_latency_le_500ms: PASS

## Metric definitions

- **recall_at_k**: Proportion of ALL labelled relevant entries (required + helpful) found within the first k ranked results: hits_in_top_k / total_relevant.
- **ndcg_at_k**: Ranking quality of the labelled relevant entries in the first k positions: DCG@k divided by the ideal DCG@k for the same labels (binary gains, log2 discount).
- **mrr**: Reciprocal rank of the FIRST labelled relevant result in the ranking: 1 / rank_of_first_relevant, 0.0 when none is ranked.
- **required_evidence_recall**: Proportion of mandatory (required) evidence entries retained in the final token-budgeted package: a required entry counts only when a selected chunk matches its path and, when the selected chunk is symbol-scoped, its symbol/line scope as well.
- **gate_b_quality**: Gate-B ranking quality of one scorer over ALL indexed chunks of a task, computed from raw sigmoid relevance scores against relevance_labels (required + helpful = relevant).
- Ranking metrics are scored on the package emission order (category-stable, then score descending); arm A presents full context and emits no ranking, so its ranking metrics are not applicable. `ranked_chunk_ids` for every task and arm B/C is in the JSON report.

## Recommendation

- Harness vs baseline: **adopt** — median token reduction 60.47%, min required-evidence recall 1.0, median select latency 3.83 ms (qualified by: synthetic fixture repositories on this host; no live model invocation in this run)
- ANE/Core ML value: **inconclusive** — Arm C measured on-device with backend coreml_all (artifact cross-encoder/ms-marco-MiniLM-L6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a): median token reduction 60.52%, p50 select latency 31.34 ms, min recall 0.0; one or more arm C thesis-reference gates fail: {"median_reduction_ge_40": true, "min_recall_ge_0_95": false, "p50_latency_le_500ms": true}
- Next step: investigate the failing arm C gate(s) before adopting the Core ML reranker
- Claims policy: all latency/memory figures measured on this host; cost and TTFT figures derived under stated assumptions; no ANE or provider-performance claim is made
