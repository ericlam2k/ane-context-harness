# Architecture Decision Record 001 — Capability-based runtime (generation-neutral)

**Status:** accepted (implemented)
**Context:** Early planning was written against specific machine profiles and
implied that a feature could be enabled from what the machine is called. That
is wrong: every feature must be offered on any supported host (macOS Apple
Silicon, macOS Intel, Linux), and must be earned by measurement rather than
assumed from hardware names. Enabling a feature goes through a fixed loop:
discover the environment, validate correctness, benchmark it, set a profile,
activate it, and degrade gracefully under pressure.

## Decision

- The harness is **generation-neutral**. Machine details (architecture,
  memory, OS version) are recorded for **diagnostics only** and are **never**
  a feature gate.
- Features are mapped to **backends**, each independently activatable:
  - Lexical retrieval -> CPU (deterministic)
  - Symbol extraction -> CPU (deterministic)
  - Code reranking -> `CPU_DETERMINISTIC`
  - Embeddings -> CPU
  - Secret classification -> rules-based CPU
- A backend is **enabled only** when it passes correctness validation AND measured
  gates: warm p95 <= feature latency limit, peak memory <= profile limit, measured
  speedup >= 15%, failure rate < 0.1%, numerical agreement.
- Behavioral profiles are derived from measurements, not chip names:
  `DETERMINISTIC_ONLY -> CONSTRAINED -> BALANCED -> HIGH_CAPACITY`, degrading under
  memory/thermal/reliability pressure.
- The public line ships **`DETERMINISTIC_ONLY`**: the deterministic CPU backend
  is the only backend, and the capability profile never enables anything else.
- The health endpoint reports only the *requested* compute configuration.

## Consequences

- On any supported host, the deterministic path works without a model. An
  unknown future host starts conservative and self-calibrates.
- No hard-coded chip-name table exists; activation is data-driven by
  measurement results and capability profiles.
- Token-reduction/latency targets are **hypotheses measured on real hardware**,
  not asserted from documentation.

## Measurement (frozen record, host = macOS 26.5 arm64, Python 3.14.5)

See `benchmarks/reports/phase1-measurement.json` (frozen in-tree record):
median token reduction 69.15% (synthetic fixtures, tight budgets, n=3),
min required-evidence recall 1.0, p50 select latency 2.09 ms,
peak RSS ~72.8 MB.
