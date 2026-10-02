# Models

Phase 1 (this checkout) ships **no Core ML model**. The `metadata.json` defines the
schema for backends that will be benchmark-qualified in later phases.

- `reranker`: currently `cpu_deterministic`; Core ML backends are defined as
  eligible but are only activated after calibration.
- No model weights are bundled or downloaded.
