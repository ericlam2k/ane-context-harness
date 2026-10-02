# Architecture Decision Record 002 — Embedding go/no-go for v0.1

**Status:** accepted (no-go for v0.1)
**Context:** ADR-001 maps "Embeddings -> CPU or benchmark-qualified Core ML" as a
possible backend. This release candidate must decide whether to ship one. The
milestone guardrails forbid embedding implementation in this cycle, and the
evidence must answer "measured need", not roadmap intent.

## Decision

**No-go for v0.1.** No embedding backend is implemented, configured, or
implied by any report. Retrieval is lexical (BM25) + structural (symbol/path/
dependency/test-pair) + optional Core ML cross-encoder reranking only.

Reasoning, from the frozen eval split of the ane-context-harness v0.1 benchmark
(`benchmarks/splits.json`, 18 tasks):

- The deterministic arm (arm B) achieves **min required-evidence recall 1.0**
  (minimum over the 18 eval-split tasks) and **median token reduction 60.47%**
  (median over the 18 eval-split tasks) with **p50 select latency 3.83 ms**
  (median over tasks) on this host. There is no labelled eval failure
  attributable to lexical candidate generation, so an embedding model would add
  a second model class, artifact storage, conversion/calibration surface, and
  privacy questions without a measured gap to close.
- Mean Recall@10 of arm B is 0.9306 (macro-mean over the 18 eval-split tasks),
  mean nDCG@10 0.8491, mean MRR 0.9074 — the residual ranking imperfections are
  in *ordering within the package*, which the cross-encoder arm already targets
  directly at ~31 ms p50 select latency (median over tasks, arm C, this host).

## Criteria for revisiting (all required)

1. A labelled failure on the **frozen eval split** is traced to lexical
   candidate-generation recall (a required chunk absent from candidates), not
   to packing or ordering.
2. An embedding candidate generator beats BM25+structural on the frozen eval
   split on required-evidence recall @ equal token budget, measured with the
   same aggregation methods recorded in `METRIC_DEFINITIONS`.
3. The embedding backend passes the ADR-001 gate set: numerical agreement,
   warm p95 within its feature latency limit, measured speedup >= 15% versus
   the deterministic path it replaces, failure rate < 0.1%.
4. No outbound network: embedding runs locally or not at all.

Tuning for (1)/(2) may use the dev split only; eval numbers are reported once
per configuration.

## Consequences

- v0.1 ships a single retrieval stack with a smaller attack/verification
  surface; capability profile gains no embedding feature to calibrate.
- Evidence bundles record `embedding_backend: not_implemented` rather than a
  qualified value.
