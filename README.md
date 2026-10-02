# ANE Context Harness — local context-intelligence harness for coding agents.

This is a **generation-neutral** local service that sits in front of any coding-agent LLM
(cloud Claude/Codex or local MLX/Metal GPU) and returns a compact, provenance-rich,
secret-redacted evidence package.

It is **not** an IDE, autonomous coding agent, source editor, or model-training platform.
It does **not** execute arbitrary shell commands and does **not** transmit repository
content to external services during normal operation.

## Phases implemented in this checkout

- Foundation: runtime discovery + capability-profile schema + calibration interface.
- Phase 0: measurement scaffold (token/latency instrumentation, benchmark task format,
  synthetic fixtures, baseline full-context runner).
- Phase 1: deterministic repository indexing (safe incremental), chunking with line
  provenance + content hashes, symbol-aware retrieval (Python + JS/TS), BM25 lexical
  retrieval, token-budgeted packing with mandatory-inclusion + diversity + stable order,
  JSON + Markdown output, local HTTP API, deterministic-only runtime profile.
- Phase 2: security layer — denied-path policy, regex + classifier secret detection,
  stable redaction placeholders, fail-closed behavior, security test suites.
- Phase 3 (code-complete): Core ML reranker toolchain — manifest + license policy,
  pinned-revision conversion orchestrator, HF-faithful tokenizer, CoreML runtime with
  safe fallback, capability-profile calibration, evaluation harness, calibration script.
- Phase 4: tool-output compression (test/build/lint/terminal; command, exit status,
  errors, warnings, tracebacks and context preserved, noise collapsed, original
  represented by SHA-256 only) via `POST /v1/context/compress-output`; provider
  adapters — Anthropic Messages (prompt-cache breakpoints), OpenAI Responses,
  generic OpenAI-compatible chat, and Markdown — over a shared stable,
  thesis-ordered, canonical prompt layout. Adapters format only; retrieval and
  ranking stay provider-neutral.
- Phase 5: end-to-end A/B evaluation (`scripts/run_phase5.py` →
  `benchmarks/reports/phase5-ab-evaluation.{json,md}`) — full-context baseline
  vs deterministic harness, plus the Core ML arm (C), on the **frozen eval
  split** (`benchmarks/splits.json`, 18 of 30 tasks; dev 12 for tuning only):
  tokens, required-evidence recall/task success, ranking metrics
  (Recall@1/5/10, nDCG@10, MRR with per-task `ranked_chunk_ids`), latency
  (p50/p95), cold/warm reranker timing, fallback counts, peak RSS. Every
  aggregate names its method (median/mean/min/sum over the eval tasks) and
  `metric_definitions` is embedded in the JSON and Markdown. Cost and TTFT
  figures are derived under stated assumptions and labelled as such; energy is
  explicitly not measured. Verdicts are provenance-bound (hardware, OS,
  model/policy versions, provider, prompt-cache state, repository set,
  methodology).

## Release gate: P3.6 — passed

**P3.6 (on-device hardware validation) passed on 2026-10-02**; the first
performance-qualified release is unblocked:

- Built on real hardware with Python 3.13 + coremltools (tokenizer fidelity
  gate: 8/8 probes; numerical validation: max abs logit 0.016, min cosine 1.0),
- numerical agreement vs. the source model on 1,000 pairs
  (min cosine 1.0, max abs logit 0.044 <= 0.05),
- `.all`, CPU+GPU and CPU-only benchmarks all within the acceptance gate
  (warm p50 <= 500 ms; measured 1.7-8.2 ms across units and sequence lengths),
- qualified backend `coreml_all`, calibration report at
  `~/.ane_context_harness/calibration_report.json`, release gate PASS.

End-to-end arm C adoption is decided on the frozen eval split, not on P3.6
agreement alone: the deterministic arm (B) passes all thesis-reference gates
(median reduction 60.47%, min recall 1.0, p50 3.83 ms — medians/minima over
the 18 eval tasks) and is the shipped default; arm C is **measured but not
adopted by default** (min required-evidence recall 0.0 on one eval task).
See `docs/adr-003-arm-c-adoption.md` and
`benchmarks/reports/phase5-ab-evaluation.{json,md}`. The earlier pre-split
arm C figure (70.15% / recall 1.0) is superseded: it predates the pinned
token estimator and the frozen split and is not comparable.

## What is NOT implemented yet

- Embeddings / embedding-based retrieval — **no-go for v0.1** with explicit
  revisit criteria (`docs/adr-002-embedding-go-no-go.md`).
- Outbound provider API calls (serializers build payloads; nothing is sent).
  Provider evaluation is staged: stages 0-1 (mock/dry-run with derived cost
  and a spend cap that defaults to 0.0 = live disabled) are implemented;
  stage 2 (controlled live) is spec-only and **not executed**
  (`docs/provider-evaluation-stages.md`).

A NEURAL ENGINE (ANE) IS NOT REQUIRED OR CLAIMED. Selection of any ANE-capable backend
requires benchmark qualification; see `ANE_Context_Harness_Adaptive_Amendment.md`. The default profile is
`DETERMINISTIC_ONLY` whenever no qualified Core ML backend exists.

## Quick start

```bash
pip install -e .[test]
ane-harness health
ane-harness index   --repo tests/fixtures/synthetic_py_project
ane-harness select  --repo-id <id> --task "Fix the discount calculation"
ane-harness serve   --port 8765
```

API: `GET /v1/health`, `POST /v1/repositories/index`, `POST /v1/context/select`,
`POST /v1/context/compress-output`, `POST /v1/feedback`.

Provider payload rendering (library):

```python
from ane_context_harness.providers import serialize
payload = serialize("anthropic", package)  # or "openai", "openai-compatible", "markdown"
```
