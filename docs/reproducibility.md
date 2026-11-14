# Reproducing the numbers

Every figure in the README comes from a committed script and a committed
report under `benchmarks/reports/`. Nothing here is hand-written. This page
explains the metrics on first use and lists the exact commands.

## Ground rules

- One token counter, pinned. Counts come from a built-in deterministic
  estimator (`TOKEN_ESTIMATOR_VERSION = "2"`, regex-based), so the same text
  counts the same everywhere; there is no downloaded tokenizer to drift.
- Reports are measured on one machine and labelled with platform, Python
  version, and policy versions. Latency figures move with your hardware.
- The frozen split (`benchmarks/splits.json`, seed `20261002`) assigns 12
  development tasks and 18 evaluation tasks. Tuning is quarantined to the
  development split; reported figures use the evaluation split. The 18
  evaluation tasks were exposed during tuning, so they are a regression set,
  not an independent estimate of how the tool generalises.
- Re-running a measurement script rewrites the committed report and
  `docs/*.png` in place. Do that on a clean tree and review the diff.

## The metrics, in plain words

- **Required-evidence recall** — of the evidence a task is labelled as
  requiring (a specific file and scope), how much made it into the pack.
  1.0 means nothing required was left out. This is the load-bearing number.
- **recall@k** — of all the relevant entries in the corpus, how many appear
  in the first *k* entries the pack emits.
- **nDCG@10** — how close the emission order is to the ideal order. 1.0
  means relevant entries are in exactly the order an ideal ranker would
  produce; lower means relevant entries drifted down the list. (nDCG =
  normalized discounted cumulative gain; the "@10" means only the first ten
  emitted entries count.)
- **MRR** — 1 divided by the rank of the first relevant entry; 0 if none was
  selected. (MRR = reciprocal rank.)

Aggregation methods are stated per figure inside each report
(`aggregation_methods`); means are macro-means over tasks, medians and minima
are over tasks. Per-task outcomes and `ranked_chunk_ids` are in the JSON. The
same definitions are embedded as `metric_definitions` in each report and
summarised in `benchmarks/reports/README.md`.

## Commands

| What you get | Command | Output |
|---|---|---|
| Token savings table + chart | `PYTHONPATH=src python3 scripts/measure_token_savings.py` then `PYTHONPATH=src python3 scripts/plot_token_savings.py` | rewrites `benchmarks/reports/token-savings.json` and `docs/token-savings.png` |
| Same-exercise comparison vs outside tools | `pip install headroom-ai toon-format` then `PYTHONPATH=src python3 scripts/bench_same_exercise.py` | rewrites `benchmarks/reports/same-exercise-bench.json` |
| Three-turn conversation carried forward | `PYTHONPATH=src python3 scripts/bench_conversation.py` | rewrites `benchmarks/reports/conversation-bench-eval.json` |
| Release evidence bundle checksums | `ane-harness evidence verify ane-context-harness-evidence-v0.1` | pass/fail per checksummed file |
| Proof on your own repo (unlabelled; no recall claim) | `ane-harness prove --repo /path/to/your/project --repo-id my-project` | median reduction + p50 latency; `recall: not_applicable` unless you pass `--tasks-file` with labelled tasks |
| Test suite | `python3 -m pytest -q` | pass/fail |

## What is not reproduced here

Ranking quality figures such as nDCG@10 (0.849) and MRR (0.907) live in
`benchmarks/reports/ranking_fusion.json`, written by
`scripts/ranking_fusion.py`; they compare ranking strategies, not end-to-end
outcomes. They are reported for completeness, not as a headline. No number in
this repository stands in for task completion; outcome evidence
(patch success with vs without the harness) has not been measured yet.

## Evidence bundles

`ane-context-harness-evidence-v0.1` is a checksummed bundle of the release
reports. `ane-harness evidence verify` recomputes the checksums and reports
any drift. A bundle that verifies proves the committed reports match what was
measured at release time; it does not prove the numbers generalise to your
repository.
