# Architecture Decision Record 003 — Arm C (Core ML reranker): adopt / disable

**Status:** accepted (measured, not adopted as default; shipped default stays
deterministic)
**Context:** P3.6 qualified the Core ML reranker toolchain (agreement on 1,000
pairs: min cosine 1.0, max abs logit 0.044 <= 0.05; all compute units warm p50
1.7-8.2 ms <= 500 ms; qualified backend `coreml_all`). This ADR records the
end-to-end adoption decision on the frozen eval split, which supersedes the
earlier pre-split arm C figures quoted in AGENTS.md (70.15% median token
reduction, recall 1.0): those were measured before the token estimator was
pinned (tiktoken-dependent counts) and before the split was frozen, and are
not comparable to the numbers below.

## Decision

- **Shipped default: arm B (deterministic) — adopted.** `coreml_enabled`
  stays `False` in the default configuration.
- **Arm C: measured on this host, NOT enabled by default (disabled pending
  gates).** It remains fully wired, opt-in, and reported by
  `scripts/run_phase5.py` whenever a qualified calibration report + built
  artifact exist.
- The deterministic fallback is never suppressed; arm C's fallback count in
  this run was 0 (zero fallbacks, `coreml_all`).

## Measurement (eval split, 18 tasks, macOS arm64, Python 3.13 venv
`~/.venvs/ane-p36`, artifact `cross-encoder/ms-marco-MiniLM-L6-v2@233902d`,
backend `coreml_all`; aggregation methods as named)

| figure | arm B (deterministic) | arm C (Core ML) |
|---|---|---|
| median token reduction | **60.47%** (median over 18 eval tasks) | 60.52% (median over 18 eval tasks) |
| min required-evidence recall | **1.0** (minimum over tasks) — gate PASS | **0.0** (minimum over tasks) — gate **FAIL** |
| p50 select latency | 3.83 ms (median over tasks) | 31.34 ms (median over tasks) — gate PASS (<= 500 ms) |
| mean Recall@10 | 0.9306 (macro-mean over tasks) | 0.875 (macro-mean over tasks) |
| mean nDCG@10 | 0.8491 (macro-mean over tasks) | 0.781 (macro-mean over tasks) |
| mean MRR | 0.9074 (macro-mean over tasks) | 0.8241 (macro-mean over tasks) |
| reranker cold (first task) / warm p50 | 0.0 / 0.0 ms (no model) | 125.78 ms / 27.06 ms (first select including model load: 11.4 s) |
| reranker fallbacks | 0 | 0 |

Reports: `benchmarks/reports/phase5-ab-evaluation.{json,md}` (JSON includes
`metric_definitions` and per-task `ranked_chunk_ids`).

## Why arm C fails the recall gate (not a numerical error)

One eval task, `hard-rules-vs-readme-001`, loses its required chunk
(`docs/pricing-rules.md`) under arm C: the blended score (0.45 deterministic +
0.55 Core ML) ranks `src/discounts/apply.ts` first; at token budget 450 both
do not fit (311 + ~254 estimated tokens), so the doc is never admitted.
The deterministic arm ranks the doc first and passes. The model itself is
faithful (P3.6 agreement above); the failure is the ranking/budget
interaction, measured honestly and left un-tuned because the task is on the
frozen eval split.

## Consequences / next step (dev-split only)

- Default recommendation stays: adopt harness with deterministic backend;
  arm C verdict `inconclusive` until `min_recall >= 0.95` passes on the frozen
  eval split.
- Revisit by recalibrating the deterministic/ML blend weight or adding a
  required-coverage budget floor, tuned on the **dev** split only, then
  re-running the eval split once per configuration.
- Claims policy unchanged: `coreml_all` is a qualified backend on this host;
  no ANE execution is claimed from `computeUnits = all`.
