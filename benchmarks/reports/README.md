# Benchmark reports

- `phase1-measurement.json` — Phase 0/1 measurement, written by
  `scripts/measure_phase1.py`.
- Frozen-split A/B evaluation (deterministic arms) runs on the eval split
  (18 tasks); cost/TTFT figures derived under stated assumptions.

## Split

`benchmarks/splits.json` (write-once, seed 20261002): dev 12 / eval 18,
stratified by difficulty, pinned legacy assignments honoured. Gates and
reported figures use **eval only**; budget/task tuning happens on dev only
and never moves eval tasks. The file is bound to the task set by
`task_set_hash` — editing a task requires deliberately re-deriving it.

## Metric definitions (also embedded in the JSON as `metric_definitions`)

- **required_evidence_recall** — fraction of mandatory (required) evidence
  retained in the final token-budgeted package (path + symbol/line scope).
- **recall_at_k** — labelled relevant (required + helpful) entries within the
  first k of the package emission order, divided by ALL relevant entries in
  the corpus (unselected relevant stay misses).
- **ndcg_at_k** — DCG@k of the emission order over ideal DCG@k of all corpus
  labels (binary gains, log2 discount).
- **mrr** — 1 / rank of the first labelled relevant entry in the emission
  order; 0.0 when none is selected.

Aggregation methods are stated per figure (`aggregation_methods` in the JSON;
means are macro-means over tasks, medians/minima/sums are over tasks). Per-task
`ranked_chunk_ids` are in the JSON outcomes.

Each report is measured on real hardware and labelled with the platform, OS,
Python version, repository set, model/policy versions, prompt-cache state, and
methodology. **No performance claim is fabricated.**
