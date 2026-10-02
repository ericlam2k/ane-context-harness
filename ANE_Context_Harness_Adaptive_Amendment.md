# Adaptive Apple Neural Engine Architecture Amendment

Use this amendment to replace all M1-specific runtime assumptions in the original ANE Context Harness thesis.

## Principle

The harness is Apple-Silicon-generation-neutral. It must not enable features from a hard-coded chip-name table. It discovers the available compute devices, validates packaged models, benchmarks eligible backends, creates a local capability profile, and activates only features that meet correctness, latency, memory, and reliability thresholds.

## Why Adaptation Is Required

Apple Neural Engines differ across generations and system variants. Practical performance also depends on macOS/Core ML version, supported model operations, unified-memory capacity, GPU capability, cooling, memory pressure, model shape, quantization, and batch size. Therefore, the presence of an ANE indicates eligibility, not benefit.

## Runtime Decision Sequence

```text
Discover devices and software capabilities
                ↓
Validate model loading and numerical correctness
                ↓
Benchmark eligible backends with representative inputs
                ↓
Measure warm p50/p95 latency, memory, failures and optional energy
                ↓
Persist a capability profile keyed by hardware + OS + model version
                ↓
Activate only benchmark-qualified features
                ↓
Degrade safely when memory, thermal or reliability limits are exceeded
```

## Discovery

On supported macOS versions, query Core ML for available CPU, GPU and Neural Engine devices. Record:

- arm64/Apple Silicon availability
- machine identifier as a local hash
- macOS and Core ML/runtime versions
- total unified memory and current memory pressure
- available Core ML compute devices
- packaged model and tokenizer versions
- successful model compilation, load and warm prediction
- optional MLX/Metal or other local-generation backend

Do not report that ANE is used merely because an Apple Silicon binary is installed or because Core ML is configured with all compute units.

## Calibration Matrix

```text
Feature                 Backends to test
Lexical retrieval       CPU
Symbol extraction       CPU
Code reranking          Core ML ALL, CPU+GPU, CPU-only
Embedding generation    Core ML ALL, CPU+GPU, CPU-only
Secret classification   Core ML ALL, CPU-only
Local text generation   MLX/Metal or configured local runtime
Cloud text generation   Provider server; no local ANE inference
```

For each eligible model/backend combination, measure:

- cold load time
- warm-up time
- warm p50 and p95 latency
- throughput at representative batch sizes
- peak resident memory
- numerical agreement with the reference model
- inference failure rate
- optional energy and thermal behavior when reliable instrumentation exists

## Feature Activation Policy

```yaml
adaptive_runtime:
  calibration_required: true
  minimum_speedup_percent: 15
  maximum_failure_rate_percent: 0.1
  require_numerical_validation: true
  recalibrate_on:
    - macos_version_change
    - model_version_change
    - runtime_version_change
    - capability_profile_schema_change
    - user_request
```

Enable an ANE-capable Core ML feature only when:

```text
correctness passed
AND warm p95 is within the feature latency limit
AND peak memory is within the device profile limit
AND measured speedup is at least the configured threshold
AND failure rate is below the configured limit
```

Otherwise choose CPU, GPU, or deterministic logic.

## Behavioral Profiles

Profiles are derived from measurements, not chip names.

### DETERMINISTIC_ONLY

- Lexical and symbol retrieval
- Rule-based secret detection
- No ML reranking
- Used when Core ML is unavailable or validation fails

### CONSTRAINED

- Deterministic retrieval
- ML reranking only for a small top-candidate set
- Small batch sizes
- Strict memory limits

### BALANCED

- Benchmark-qualified Core ML reranking
- Optional compact embeddings
- Optional secret classifier
- Moderate candidate and batch limits

### HIGH_CAPACITY

- Larger reranking candidate set
- Resident embedding/classification models when beneficial
- Limited concurrency only after memory and thermal validation

## Example Capability Profile

```json
{
  "profile_version": 1,
  "machine_id": "local-hardware-hash",
  "hardware": {
    "architecture": "arm64",
    "unified_memory_bytes": 17179869184
  },
  "software": {
    "macos_version": "detected-at-runtime",
    "coreml_available": true
  },
  "devices": {
    "cpu": true,
    "gpu": true,
    "neural_engine": true
  },
  "behavioral_profile": "BALANCED",
  "features": {
    "reranker": {
      "enabled": true,
      "backend": "coreml_all",
      "batch_size": 8,
      "warm_p50_ms": 210,
      "warm_p95_ms": 390
    },
    "embedding": {
      "enabled": false,
      "reason": "no_measured_advantage"
    },
    "secret_classifier": {
      "enabled": true,
      "backend": "coreml_all"
    }
  },
  "calibration_fingerprint": "hardware-os-runtime-model-hash"
}
```

Do not persist repository text, secrets or raw benchmark inputs in this profile.

## Dynamic Degradation

When memory pressure, thermal pressure or repeated inference errors occur, degrade in one direction:

```text
HIGH_CAPACITY → BALANCED → CONSTRAINED → DETERMINISTIC_ONLY
```

Recovery requires a cooldown and successful health probe. Do not oscillate between backends on every request.

## Forward Compatibility

Unknown future Apple Silicon devices start conservatively, then run discovery, validation and calibration. A future chip must not require a hard-coded generation branch to function. Generation-specific optimizations may be distributed as optional data-driven model/backend profiles, but the generic correctness and fallback path remains mandatory.

## Revised Acceptance Criteria

1. A new or unknown Apple Silicon Mac can build a capability profile without a chip-name branch.
2. Every enabled ML feature passes numerical validation.
3. ANE/Core ML is selected only when it delivers at least the configured measured benefit.
4. Features downgrade automatically under memory, thermal or reliability pressure.
5. The deterministic path always remains functional.
6. Benchmarks identify hardware, OS, runtime, model, input shape, batch size and profile.
7. Documentation never equates Apple Silicon native execution with ANE execution.
8. Cloud providers remain generation-neutral because their main inference is remote; only local preprocessing is adapted.

## Implementing-LLM Instruction

Refactor the original thesis and implementation so all M1-specific policy becomes capability-based. Implement discovery and calibration before the Core ML feature layer. Do not create a static M1/M2/M3/M4 feature matrix as the source of truth. Chip identity may be recorded for diagnostics, but runtime activation must be based on successful validation and measured performance.
