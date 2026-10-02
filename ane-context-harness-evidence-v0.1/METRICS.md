# Evidence classification

This bundle separates four kinds of statements. Every number in the included
reports belongs to exactly one category.

## Measured

Produced by executing code on the tested host and reading counters/clocks:

- agreement cosines and raw-logit differences (Gate A, 1000 pairs)
- warm p50/p95 latency per compute unit and failure rates
- phase5 selection latency (p50/p95), peak RSS
- arm A/B/C token counts, required-evidence recall, gate-B ranking metrics
- cold model-load latency, prediction counts

## Calculated

Deterministic functions of measurements or inputs:

- token-reduction percentages; every aggregate names its method
  (mean/median/min/max of per-task values, weighted total, totals ratio)
- checksums, fingerprints, task-set hash, configuration hash

## Estimated

Explicitly assumed, never presented as measurements:

- derived cost figures (stated $/M-token price)
- TTFT sensitivity (token delta at illustrative prefill rates)

## Unmeasured

Recorded as unknown; never inferred:

- energy, real-provider TTFT/cost/tool behavior
- Neural Engine execution share (backend `coreml_all` requests all compute
  units; it does not attribute where ops ran)
- performance on any machine other than the tested configuration
