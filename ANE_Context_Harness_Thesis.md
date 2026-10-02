# Thesis and Implementation Specification: ANE Context Harness for Coding Agents

**Document status:** Implementation-ready design thesis  
**Target platform:** Apple Silicon Mac, optimized first for M1 8 GB and 16 GB  
**Primary interface:** Local HTTP service and optional CLI  
**Primary consumers:** Claude Code, Codex, open-weight coding agents, and custom agent frameworks  
**Core principle:** Use the Apple Neural Engine (ANE) as a low-power context-selection and privacy layer—not as the main generative LLM runtime.

---

## 1. Executive Summary

This project will build a lightweight, provider-independent **context harness** that sits between a coding agent and its target language model. The harness accepts a coding task and candidate repository context, identifies the minimum high-value evidence required by the main LLM, removes irrelevant or duplicated content, detects/redacts secrets, and returns a compact evidence package.

The harness must support both:

- **Cloud models:** Claude, Codex/OpenAI, and other APIs.
- **Local open-weight models:** MLX, Ollama, llama.cpp, or other Metal/GPU runtimes.

The harness must not attempt to run proprietary cloud models on the M1 Neural Engine. Claude and Codex model inference remains server-side. Likewise, the first implementation must not attempt to convert arbitrary generative LLMs to Core ML. Instead, the harness uses compact Core ML models for predictable tasks suited to ANE execution:

1. Relevance classification.
2. Code-chunk reranking.
3. Sensitive-content detection.
4. Optional context-compression decisions.

The expected result is **40–60% fewer input tokens** on typical multi-turn coding tasks while preserving at least **95% of task-relevant evidence**. The target local filtering latency is **500 ms or less** for a typical request after indexing and model warm-up. End-to-end interactive latency should improve by approximately **20–40%** in context-heavy workflows, subject to provider caching, network conditions, repository size, and model behavior.

The project is a **context service**, not an IDE, autonomous code editor, terminal agent, or model-training platform.

---

## 2. Problem Statement

Coding agents accumulate excessive context. A single task can repeatedly send:

- System and project instructions.
- Tool definitions.
- Repository maps.
- Complete source files.
- Previously read file fragments.
- Terminal output.
- Build and test logs.
- Git diffs.
- Conversation history.
- Failed attempts and stale observations.

Much of this material is irrelevant, duplicated, obsolete, or low-signal. It increases input-token usage, cloud cost, prompt-processing latency, local KV-cache size, unified-memory pressure, and the probability that the main model overlooks important evidence.

Provider prompt caching helps with stable, identical prefixes, but does not fully solve changing file selections, tool outputs, new test logs, altered prompts, or irrelevant context admitted in the first place. The harness therefore operates before prompt caching: it reduces and stabilizes the context presented to any main model.

The central engineering question is:

> Can a compact, local, ANE-capable context-selection service reduce coding-agent context substantially without lowering task success?

The hypothesis is:

> A hybrid retrieval pipeline combining deterministic search, repository structure, and a compact Core ML reranker can remove 40–60% of input tokens while retaining at least 95% of relevant evidence, adding less latency than it saves.

---

## 3. Goals

### 3.1 Primary goals

1. Provide one provider-neutral API for selecting coding context.
2. Reduce input-token volume by at least 40% on the representative evaluation set.
3. Preserve at least 95% recall of human-labelled relevant evidence.
4. Keep p50 filtering latency at or below 500 ms after warm-up for typical candidate sets.
5. Keep p95 filtering latency at or below 1.5 seconds on the target M1.
6. Run all repository inspection, ranking, redaction, and compression locally.
7. Support Core ML execution with `.all` compute units, allowing compatible operations to use ANE, GPU, or CPU.
8. Expose telemetry showing token reduction, latency, selected evidence, redactions, and—where observable—compute configuration.
9. Fall back safely when the Core ML model is unavailable or unsupported.
10. Produce deterministic, inspectable evidence packages with provenance.

### 3.2 Secondary goals

1. Leave the GPU available for a local generative model whenever practical.
2. Improve prompt-cache hit probability by producing stable ordering and canonical serialization.
3. Reduce the accidental transmission of secrets and sensitive repository data.
4. Support incremental indexing so repeated requests are inexpensive.
5. Allow model-independent benchmarking and A/B evaluation.

---

## 4. Non-Goals

The first implementation must **not**:

1. Build a new IDE.
2. Implement a complete autonomous coding agent.
3. Execute arbitrary shell commands.
4. Modify source files.
5. Commit, push, merge, or deploy code.
6. Run Claude or Codex inference locally.
7. Guarantee that every Core ML operation runs on ANE.
8. Convert arbitrary large generative LLMs to Core ML.
9. Replace MLX, Ollama, llama.cpp, Claude Code, or Codex.
10. Train a new foundation model.
11. Upload repository content to a remote embedding or ranking service.
12. Claim latency or energy improvements without direct measurement.

---

## 5. Key Design Decision

The most valuable use of the M1 Neural Engine is an independent **Context Intelligence Layer**:

```text
Coding task + repository + tool output
                  │
                  ▼
      Deterministic local retrieval
        grep + symbols + recency
                  │
                  ▼
     Core ML relevance/reranking model
       ANE/GPU/CPU selected by Core ML
                  │
                  ▼
       Secret detection and redaction
                  │
                  ▼
      Token-budgeted evidence package
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
      Claude    Codex    Local GPU LLM
```

This architecture is preferable to attempting universal ANE generation because:

- Proprietary model weights are unavailable locally.
- Open-weight architectures change frequently.
- Autoregressive decoding is dynamic and often memory-bandwidth constrained.
- Core ML conversion requires architecture-specific work.
- Compact classifiers and rerankers have predictable inputs and outputs.
- A provider-neutral context layer benefits every downstream LLM.

---

## 6. Functional Requirements

### FR-1: Repository registration

The service shall register a local repository root and create an incremental index containing:

- Relative file path.
- Language/file type.
- File size.
- Content hash.
- Chunk boundaries.
- Symbol names when parsers are available.
- Import/reference hints when parsers are available.
- Git recency metadata when Git is available.

The index must exclude:

- `.git/` internals.
- Binary files.
- Build artifacts.
- Dependency/vendor directories by default.
- Paths denied by policy.
- Files exceeding configurable size limits unless explicitly requested.

### FR-2: Candidate generation

Given a task, the service shall produce an initial candidate set using deterministic methods:

1. Exact term and path matching.
2. Lexical/BM25-style retrieval.
3. Symbol-name matching.
4. Import/dependency adjacency where available.
5. Git recency as a low-weight signal.
6. Explicitly referenced files as mandatory candidates.

The system must not rely exclusively on embeddings or an ML model.

### FR-3: ML reranking

The service shall rerank candidate chunks with a compact local model converted to Core ML. Inputs should include:

- Task/query text.
- File path.
- Symbol name, if any.
- Chunk text.
- Optional deterministic retrieval score.

The output shall be a relevance score between 0 and 1.

The Core ML model configuration should initially use all available compute units. The service must support fallback modes:

- Core ML `.all`.
- Core ML CPU+GPU.
- CPU-only deterministic ranking.

### FR-4: Sensitive-content detection

Before producing the final package, the service shall detect and redact likely secrets using layered controls:

1. Denied path rules, such as `.env`, private keys, credential stores, and signing assets.
2. Known credential patterns.
3. High-entropy token detection.
4. Optional compact Core ML sensitivity classifier.

Redactions must use stable placeholders within one request, for example:

```text
<REDACTED_API_KEY_1>
<REDACTED_EMAIL_2>
<REDACTED_DATABASE_URL_1>
```

The service must never log the original secret value.

### FR-5: Token-budgeted selection

The service shall select evidence under a configurable token budget. Selection must account for:

- Mandatory chunks.
- Relevance score.
- Diversity across files/symbols.
- Dependency completeness.
- Test/source pairing.
- Redundancy.
- Per-file maximum allocation.

The selector must avoid choosing ten near-identical chunks while excluding a required interface or test.

### FR-6: Evidence package

Every selected chunk must include provenance:

```json
{
  "path": "src/example.py",
  "start_line": 20,
  "end_line": 68,
  "content_hash": "sha256:...",
  "symbol": "calculate_total",
  "score": 0.91,
  "selection_reasons": [
    "symbol_match",
    "called_by_failing_test",
    "ml_reranker_high_score"
  ],
  "content": "..."
}
```

The final package must have stable ordering to improve reproducibility and caching:

1. Project instructions.
2. Explicitly requested files.
3. Interfaces/types.
4. Primary implementation chunks.
5. Relevant tests.
6. Recent errors/tool output.
7. Supporting context.

### FR-7: Tool-output compression

The service shall accept terminal, build, lint, and test output. It shall preserve:

- Command name.
- Exit status.
- Error and warning messages.
- Stack traces near the failure.
- Referenced paths and line numbers.
- Test names and assertions.
- A configurable amount of surrounding context.

It shall remove or collapse:

- Repeated progress output.
- Duplicate stack frames.
- Successful test listings when not needed.
- Repeated warnings.
- Long dependency installation logs.

The original output must be representable by a hash and optional local reference; it must not be sent downstream automatically.

### FR-8: Provider adapters

The harness shall return provider-neutral context. Optional adapters may format it for:

- Anthropic Messages.
- OpenAI Responses.
- A generic OpenAI-compatible local endpoint.
- Plain Markdown for manual use.

Provider adapters must not own retrieval logic.

### FR-9: Explainability

The service shall expose:

- Why each chunk was selected.
- Why each chunk was excluded when requested.
- Original versus final estimated tokens.
- Reduction percentage.
- Filtering time by stage.
- Detected/redacted item counts.
- Model/fallback mode used.

### FR-10: Incremental updates

When files change, only changed files shall be re-chunked and re-indexed. The service shall use hashes and modification metadata while avoiding incorrect reuse when content changes.

---

## 7. API Specification

### 7.1 Health endpoint

```http
GET /v1/health
```

Example response:

```json
{
  "status": "ok",
  "platform": "apple-silicon",
  "coreml_model_loaded": true,
  "compute_mode": "all",
  "index_version": "1",
  "service_version": "0.1.0"
}
```

Do not claim ANE execution merely because `compute_mode` is `all`. Report only what is directly observable. Use wording such as `coreml_compute_units_requested: all` if actual unit attribution cannot be verified.

### 7.2 Register/index repository

```http
POST /v1/repositories/index
Content-Type: application/json
```

```json
{
  "repository_path": "/absolute/local/path",
  "repository_id": "optional-stable-id",
  "force_rebuild": false
}
```

Response:

```json
{
  "repository_id": "repo_123",
  "files_indexed": 482,
  "chunks_indexed": 3281,
  "files_skipped": 113,
  "duration_ms": 2840
}
```

### 7.3 Select context

```http
POST /v1/context/select
Content-Type: application/json
```

Request:

```json
{
  "repository_id": "repo_123",
  "task": "Fix the incorrect discount calculation and update its tests",
  "token_budget": 12000,
  "explicit_paths": [],
  "tool_outputs": [],
  "conversation_summary": null,
  "options": {
    "include_tests": true,
    "redact_secrets": true,
    "use_ml_reranker": true,
    "stable_order": true
  }
}
```

Response:

```json
{
  "request_id": "ctx_456",
  "repository_id": "repo_123",
  "task": "Fix the incorrect discount calculation and update its tests",
  "metrics": {
    "candidate_tokens": 30142,
    "selected_tokens": 11862,
    "tokens_removed": 18280,
    "reduction_percent": 60.65,
    "total_latency_ms": 421,
    "candidate_generation_ms": 71,
    "reranking_ms": 238,
    "redaction_ms": 19,
    "packing_ms": 93
  },
  "execution": {
    "reranker": "coreml",
    "coreml_compute_units_requested": "all",
    "fallback_used": false
  },
  "redactions": {
    "count": 2,
    "types": ["api_key", "email"]
  },
  "evidence": [],
  "markdown": "# Selected repository context\n..."
}
```

### 7.4 Compress tool output

```http
POST /v1/context/compress-output
Content-Type: application/json
```

```json
{
  "kind": "test",
  "command": "pytest -q",
  "exit_code": 1,
  "content": "...",
  "token_budget": 2000
}
```

### 7.5 Feedback endpoint

```http
POST /v1/feedback
Content-Type: application/json
```

```json
{
  "request_id": "ctx_456",
  "useful": true,
  "missing_paths": [],
  "irrelevant_paths": ["docs/legacy.md"],
  "task_succeeded": true,
  "notes": "Optional local note"
}
```

Feedback must remain local by default.

---

## 8. Ranking and Packing Strategy

### 8.1 Initial scoring

Begin with an interpretable weighted score:

```text
initial_score =
    0.35 × lexical_score
  + 0.25 × symbol_score
  + 0.15 × path_score
  + 0.10 × dependency_score
  + 0.10 × test_pair_score
  + 0.05 × git_recency_score
```

These are starting values, not universal truths. Make them configurable and tune them against the evaluation set.

### 8.2 ML score integration

Use the Core ML reranker only on the top deterministic candidates, not the entire repository.

```text
final_score = 0.45 × initial_score + 0.55 × ml_relevance_score
```

The service should rerank approximately 50–200 candidates per request, depending on chunk size and latency budget.

### 8.3 Mandatory inclusion rules

A chunk becomes mandatory when:

- The user explicitly names its path.
- A selected stack trace points to it.
- It defines a directly named symbol.
- It is a required public interface for a selected implementation.
- It is the nearest relevant test for the selected source.

Mandatory content still passes through redaction and path policy.

### 8.4 Diversity controls

Apply maximal marginal relevance or an equivalent diversity mechanism:

```text
selection_value = relevance - lambda × similarity_to_already_selected
```

Use a configurable `lambda`, initially 0.2–0.35. Do not remove structurally necessary repeated context solely for diversity.

### 8.5 Token budgeting

Reserve the budget by category:

```yaml
budget:
  instructions_percent: 5
  interfaces_percent: 15
  implementation_percent: 45
  tests_percent: 20
  tool_output_percent: 10
  contingency_percent: 5
```

Unused category budget may flow to the highest-ranked remaining evidence.

---

## 9. Model Strategy

### 9.1 First model class

Use a compact cross-encoder or sequence-classification model suitable for scoring `(task, chunk)` pairs. The first model should prioritize:

- Core ML convertibility.
- Fixed maximum sequence length.
- Stable supported operators.
- Small memory footprint.
- Fast warm inference.
- Acceptable code/text relevance quality.

Do not begin with a generative model. The output must be a scalar relevance score.

### 9.2 Conversion pipeline

The implementation should provide an offline model-build command:

```text
source model
   → load in evaluation mode
   → wrap task/chunk inputs
   → trace/export with fixed shapes
   → convert with coremltools
   → optional quantization
   → validate numerical agreement
   → benchmark compute configurations
   → package model and tokenizer metadata
```

### 9.3 Model validation

Before shipping a converted model:

1. Compare source-framework and Core ML scores on at least 1,000 pairs.
2. Define an acceptable maximum deviation.
3. Test empty, short, maximum-length, Unicode, and code-heavy inputs.
4. Verify deterministic output within expected tolerance.
5. Benchmark cold load, warm p50, warm p95, peak memory, and batch-size effects.
6. Verify fallback behavior when Core ML loading fails.

### 9.4 ANE attribution

Core ML may partition work across available compute resources. Therefore:

- Never equate an Apple Silicon binary with ANE use.
- Never equate `computeUnits = all` with proof that all layers execute on ANE.
- Record the requested compute configuration.
- If using Apple profiling tools, document the measurement method and OS version.
- Compare `.all`, `.cpuAndGPU`, and `.cpuOnly` latency and energy where possible.
- Retain the ANE-capable route only if measured results justify its complexity.

---

## 10. Data Structures

### RepositoryChunk

```text
id: stable chunk identifier
repository_id: repository identifier
path: normalized relative path
language: detected language
start_line: inclusive line
end_line: inclusive line
symbol: optional symbol name
content: original local text
content_hash: SHA-256
estimated_tokens: integer
lexical_terms: normalized terms
metadata: imports, references, git recency, test/source relation
```

### CandidateScore

```text
chunk_id
lexical_score
symbol_score
path_score
dependency_score
test_pair_score
git_recency_score
initial_score
ml_relevance_score
final_score
selection_reasons
```

### EvidencePackage

```text
request_id
repository_id
task
policy_version
index_version
model_version
metrics
redaction_summary
evidence[]
markdown
```

---

## 11. Security and Privacy Requirements

1. Bind the service to `127.0.0.1` by default.
2. Reject repository paths outside explicitly registered roots.
3. Normalize paths and block traversal with `..` or symlink escape.
4. Do not expose arbitrary file-read endpoints outside repository policy.
5. Do not execute shell commands.
6. Do not transmit repository content unless an explicit provider adapter is invoked.
7. Keep raw content out of normal logs.
8. Store hashes, sizes, scores, and paths in telemetry—not source text.
9. Protect the local index with user-only filesystem permissions.
10. Make telemetry disablement available.
11. Never persist unredacted tool output unless explicitly configured.
12. Add a maximum request size and maximum file/chunk size.
13. Treat generated Markdown as untrusted data when consumed by other tools.
14. Clearly label redacted and truncated evidence.
15. Include a “fail closed” mode: if redaction fails, do not return cloud-ready context.

---

## 12. Performance Model and Targets

### 12.1 Representative scenarios

#### Small task

```text
Candidate context per call: 12,000 tokens
Selected context per call:  7,000 tokens
Calls per task:              6
Nominal tokens saved:        30,000
Reduction:                   about 42%
```

#### Typical task

```text
Candidate context per call: 30,000 tokens
Selected context per call:  12,000 tokens
Calls per task:              10
Nominal tokens saved:        180,000
Reduction:                   60%
```

#### Large task

```text
Candidate context per call: 70,000 tokens
Selected context per call:  22,000 tokens
Calls per task:              15
Nominal tokens saved:        720,000
Reduction:                   about 69%
```

These are planning scenarios, not guaranteed production results.

### 12.2 Target metrics

```yaml
targets:
  token_reduction_median: ">= 40%"
  relevant_evidence_recall: ">= 95%"
  task_success_degradation: "0 percentage points preferred; <= 2 points maximum during pilot"
  filtering_latency_p50_ms: "<= 500"
  filtering_latency_p95_ms: "<= 1500"
  index_update_latency_small_change_ms: "<= 500"
  secret_redaction_recall_on_test_set: ">= 99%"
  service_memory_8gb_profile_mb: "<= 1200 after warm-up"
  crash_free_requests: ">= 99.9%"
```

### 12.3 End-to-end latency expectation

The harness should target **20–40% lower end-to-end interactive latency** for context-heavy tasks. It may provide little benefit for tiny prompts or workloads dominated by compilation and tests. Measure:

```text
net_saving = baseline_task_time - filtered_task_time
```

Do not report only reranker speed. Include indexing amortization, filter overhead, provider TTFT, generation, and tool time.

---

## 13. Evaluation Methodology

### 13.1 Dataset

Create a local benchmark containing at least:

- 30 small tasks.
- 30 typical tasks.
- 20 large or cross-file tasks.
- Multiple languages and repository sizes.
- Bug fixes, feature changes, test failures, documentation questions, and refactors.

For each task, label:

- Required files.
- Required symbols/line ranges where practical.
- Helpful but nonessential evidence.
- Irrelevant distractors.
- Sensitive-content fixtures.
- Expected task outcome.

Use real repositories only when licensing and privacy permit. Otherwise use public repositories or purpose-built fixtures. Do not fabricate performance results.

### 13.2 Baselines

Compare:

1. Full candidate context.
2. Lexical-only retrieval.
3. Lexical + symbols.
4. Lexical + symbols + embeddings/reranker on CPU/GPU.
5. Full proposed Core ML pipeline.
6. Proposed pipeline with provider prompt caching where measurable.

### 13.3 Core metrics

```text
Token reduction
Required-evidence recall
Precision of selected evidence
Mean reciprocal rank / nDCG for labelled chunks
Filter p50/p95 latency
Cold-start latency
Peak memory
Main-model TTFT
Total task time
Input-token billing categories when APIs expose them
Task success rate
Redaction recall and false-positive rate
```

### 13.4 Quality gate

A token reduction result is invalid if required-evidence recall falls below 95%. The project must optimize in this order:

1. Safety and privacy.
2. Required-evidence recall.
3. Task success.
4. Latency.
5. Token reduction.

---

## 14. Observability

Emit local structured events without source content:

```json
{
  "event": "context_selection_completed",
  "request_id": "ctx_456",
  "repository_id": "repo_123",
  "candidate_chunks": 127,
  "selected_chunks": 19,
  "candidate_tokens": 30142,
  "selected_tokens": 11862,
  "latency_ms": 421,
  "reranker": "coreml",
  "coreml_compute_units_requested": "all",
  "fallback_used": false,
  "redaction_count": 2
}
```

Provide a benchmark mode that writes CSV or JSONL containing only permitted metrics.

---

## 15. Failure and Fallback Behavior

### Core ML model fails to load

Fallback to deterministic ranking and report:

```text
fallback_used: true
fallback_reason: coreml_model_load_failed
```

### Request exceeds token or candidate limit

Use bounded candidate generation, return a truncation warning, and preserve mandatory evidence.

### Index is stale

Detect changed hashes, refresh affected files, and mark package metadata with the refreshed index version.

### Redaction system errors

In cloud-ready mode, fail closed and return no unredacted evidence.

### Unsupported or binary file

Skip it and report a structured reason.

### No relevant evidence found

Return a low-confidence package with suggested deterministic searches. Do not fill the budget with unrelated files.

---

## 16. Implementation Phases

### Phase 0: Measurement scaffold

Deliver:

- Benchmark task format.
- Token estimator.
- Latency instrumentation.
- Repository fixture set.
- Baseline full-context runner.

Acceptance criteria:

- Reproducible metrics from a fixed task set.
- No ML model required.

### Phase 1: Deterministic context service

Deliver:

- Repository registration/indexing.
- Chunking.
- Lexical retrieval.
- Symbol extraction for at least two priority languages.
- Token-budgeted packing.
- Provenance-rich Markdown and JSON output.
- Local HTTP API.

Acceptance criteria:

- At least 25% median token reduction.
- At least 95% required-evidence recall on fixtures.
- No arbitrary shell execution.

### Phase 2: Security layer

Deliver:

- Denied-path policy.
- Pattern and entropy detection.
- Stable redaction placeholders.
- Fail-closed cloud-ready mode.
- Security tests.

Acceptance criteria:

- At least 99% secret recall on the controlled test set.
- No raw secret values in logs.

### Phase 3: Core ML reranker

Deliver:

- Source model evaluation harness.
- Core ML conversion script.
- Numerical agreement tests.
- `.all`, CPU+GPU, and CPU-only benchmarks.
- Runtime integration and fallback.

Acceptance criteria:

- At least 40% median token reduction.
- At least 95% required-evidence recall.
- Typical warm p50 total filter latency at or below 500 ms, or documented hardware-adjusted result if the M1 cannot achieve it.

### Phase 4: Tool-output compression and provider formatting

Deliver:

- Test/build/log compressor.
- Anthropic, OpenAI, generic OpenAI-compatible, and Markdown serializers.
- Stable prompt ordering.
- Prompt-cache-aware prefix layout.

Acceptance criteria:

- No provider-specific logic inside retrieval/ranking.
- At least one end-to-end integration test per adapter.

### Phase 5: End-to-end evaluation

Deliver:

- A/B benchmark report.
- Token, TTFT, total latency, task success, and cost analysis.
- Memory/energy observations where measurable.
- Recommendation on whether ANE/Core ML adds value versus CPU/GPU alternatives.

Acceptance criteria:

- No unqualified performance claims.
- All conclusions tied to measured hardware, OS, repository set, model versions, and cache conditions.

---

## 17. Suggested Project Layout

```text
ane-context-harness/
├── README.md
├── THESIS.md
├── pyproject.toml
├── config/
│   ├── default.yaml
│   ├── privacy.yaml
│   └── ignore-patterns.yaml
├── models/
│   ├── README.md
│   └── metadata.json
├── scripts/
│   ├── convert_model.py
│   ├── benchmark_model.py
│   └── build_eval_dataset.py
├── src/
│   └── ane_context_harness/
│       ├── api.py
│       ├── cli.py
│       ├── config.py
│       ├── schemas.py
│       ├── indexing/
│       │   ├── repository.py
│       │   ├── chunking.py
│       │   ├── symbols.py
│       │   └── storage.py
│       ├── retrieval/
│       │   ├── lexical.py
│       │   ├── structural.py
│       │   ├── reranker.py
│       │   └── selector.py
│       ├── privacy/
│       │   ├── paths.py
│       │   ├── secrets.py
│       │   └── redaction.py
│       ├── compression/
│       │   ├── logs.py
│       │   └── conversation.py
│       ├── providers/
│       │   ├── markdown.py
│       │   ├── anthropic.py
│       │   ├── openai.py
│       │   └── openai_compatible.py
│       ├── coreml/
│       │   ├── runtime.py
│       │   └── tokenizer.py
│       └── telemetry/
│           ├── metrics.py
│           └── events.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── performance/
└── benchmarks/
    ├── tasks/
    ├── labels/
    └── reports/
```

---

## 18. Configuration Example

```yaml
server:
  host: 127.0.0.1
  port: 8765

index:
  storage: sqlite
  max_file_bytes: 1000000
  chunk_target_tokens: 350
  chunk_overlap_tokens: 40
  incremental: true

retrieval:
  max_initial_candidates: 500
  max_rerank_candidates: 120
  lexical_weight: 0.35
  symbol_weight: 0.25
  path_weight: 0.15
  dependency_weight: 0.10
  test_pair_weight: 0.10
  git_recency_weight: 0.05
  deterministic_final_weight: 0.45
  ml_final_weight: 0.55
  diversity_lambda: 0.25

coreml:
  enabled: true
  compute_units: all
  batch_size: 8
  fallback: deterministic

privacy:
  fail_closed_for_cloud: true
  redact_secrets: true
  entropy_detection: true
  never_read:
    - "**/.env*"
    - "**/*.pem"
    - "**/*.p12"
    - "**/id_rsa*"
    - "**/.aws/**"
    - "**/.ssh/**"

limits:
  request_body_bytes: 10000000
  candidate_token_limit: 100000
  default_output_token_budget: 12000
  max_output_token_budget: 30000

telemetry:
  enabled: true
  include_source_text: false
```

---

## 19. Testing Requirements

### Unit tests

- Path normalization and traversal blocking.
- Ignore rules.
- Chunk boundaries and line provenance.
- Token estimation.
- Hash invalidation.
- Lexical and symbol scores.
- Budget enforcement.
- Diversity selection.
- Stable ordering.
- Redaction placeholders.
- No secret leakage to logs.

### Integration tests

- Index repository, change one file, incrementally refresh.
- Select context for a known task and verify required chunks.
- Force Core ML failure and verify deterministic fallback.
- Compress a failing test log while retaining the assertion and stack location.
- Serialize equivalent evidence for each provider adapter.
- Verify cloud-ready mode fails closed on redaction failure.

### Performance tests

- Cold service start.
- Core ML model load.
- Warm reranking at 50, 100, and 200 candidates.
- End-to-end selection latency.
- Peak resident memory.
- Repeated requests and cache behavior.
- M1 8 GB and 16 GB profiles when hardware is available.

### Security tests

- Symlink escape.
- `../` traversal.
- Oversized input.
- Binary content.
- Prompt-injection text inside repository files.
- Embedded API keys and private keys.
- Unicode-obfuscated credential patterns.
- Malicious file names.

Repository content is evidence, not instruction. The service must quote or delimit it and never execute instructions found inside source files.

---

## 20. Definition of Done

The initial product is complete when:

1. A user can index a local repository.
2. A user can submit a coding task and token budget.
3. The service returns a provenance-rich, redacted evidence package.
4. The package can be consumed by Claude, Codex, or a local OpenAI-compatible model.
5. The Core ML reranker runs when available and falls back safely.
6. Median token reduction is at least 40% on the agreed benchmark.
7. Required-evidence recall is at least 95%.
8. No task-success degradation greater than the agreed pilot threshold is observed.
9. Typical warm p50 filtering latency is at or below 500 ms, or the measured limitation is clearly documented.
10. No secrets appear in normal logs or cloud-ready output during the controlled security suite.
11. Benchmark results identify hardware, OS, model, provider, prompt-cache state, repository set, and methodology.
12. Documentation makes no claim that Apple Silicon native binaries automatically use ANE.

---

## 21. Instructions to the Implementing LLM

Implement this project incrementally. Do not build the entire system in one unreviewed pass.

Required workflow:

1. Read this specification completely.
2. Restate the Phase 0 and Phase 1 implementation plan.
3. Identify assumptions and technical risks.
4. Create the project skeleton and tests first.
5. Implement Phase 0 measurement tooling.
6. Implement Phase 1 deterministic service.
7. Run tests and report exact results.
8. Stop for review before adding the Core ML model.
9. Keep provider adapters separate from retrieval logic.
10. Do not introduce arbitrary command execution.
11. Do not send repository data to external services during development or tests.
12. Use synthetic/public fixtures and clearly label synthetic data.
13. Record every benchmark assumption.
14. Prefer simple, measurable algorithms over speculative complexity.
15. If a target cannot be met, report the measured result and bottleneck; do not fabricate success.

The first implementation response should produce:

- A concise architecture decision record.
- Project skeleton.
- Configuration schema.
- API schemas.
- Phase 0 benchmark format.
- Phase 1 deterministic indexing/retrieval plan.
- Unit and integration test plan.
- No Core ML conversion until the deterministic baseline is functioning.

---

## 22. Final Thesis

The M1 Neural Engine should not be treated as a universal accelerator for Claude, Codex, or arbitrary open-weight generative models. Its highest-value role in a universal coding-agent harness is to run compact, repeated and privacy-sensitive context operations locally.

The proposed harness transforms the ANE from an unused specialist processor into a provider-independent context intelligence layer. It aims to reduce input tokens, prompt latency, unified-memory pressure and privacy exposure while leaving complex reasoning to the best available cloud or GPU-hosted model.

The project succeeds only if it preserves evidence and task quality. Therefore, the governing objective is not maximum compression. It is:

> **Produce the smallest safe context that retains all evidence necessary for the coding model to succeed.**
