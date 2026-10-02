# Architecture Decision Record 001 — Capability-based runtime (generation-neutral)

**Status:** accepted (Phase 0/1 implemented)
**Context:** The original thesis was written against "M1 8 GB / 16 GB" and implied
Apple-Silicon/ANE coupling. The Adaptive Amendment forbids enabling features from
chip identity and requires a discover→validate→benchmark→profile→activate→degrade
decision loop.

## Decision

- The harness is **generation-neutral**. Chip identity is recorded for **diagnostics
  only** and is **never** a feature gate.
- Features are mapped to **backends**, each independently activatable:
  - Lexical retrieval -> CPU (deterministic)
  - Symbol extraction -> CPU (deterministic)
  - Code reranking -> `CPU_DETERMINISTIC | COREML_ALL | COREML_CPU_GPU | LOCAL_GPU`
  - Embeddings -> CPU or benchmark-qualified Core ML
  - Secret classification -> rules-based CPU, optional benchmark-qualified Core ML
- A backend is **enabled only** when it passes correctness validation AND measured
  gates: warm p95 <= feature latency limit, peak memory <= profile limit, measured
  speedup >= 15%, failure rate < 0.1%, numerical agreement.
- Behavioral profiles are derived from measurements, not chip names:
  `DETERMINISTIC_ONLY -> CONSTRAINED -> BALANCED -> HIGH_CAPACITY`, degrading under
  memory/thermal/reliability pressure.
- **ANE is never claimed** because a binary is Apple Silicon or because
  `computeUnits = all`. The health endpoint reports only the *requested* compute
  configuration; `neural_engine_observed` is `False` until calibration measures it.
- **Phase 1 ships with `DETERMINISTIC_ONLY`** (no Core ML model is built yet). The
  Core ML runtime, conversion, and calibration interfaces exist but are inert.

## Consequences

- On any Apple Silicon Mac or non-Apple host, the deterministic path works without a
  model. An unknown future chip starts conservative and self-calibrates.
- No hard-coded chip-name table exists; activation is data-driven per
  `models/metadata.json` profiles plus runtime calibration.
- Token-reduction/latency targets are **hypotheses measured on real hardware**, not
  asserted from documentation.

## Measurement (this iteration, host = macOS 26.5, arm64, Python 3.14.5)

See `benchmarks/reports/`. Summary: median token reduction 69% (synthetic fixture,
tight budgets), min required-evidence recall 1.0, warm p50 selection latency
~1.8 ms, peak RSS ~86 MB. ANE not claimed.
