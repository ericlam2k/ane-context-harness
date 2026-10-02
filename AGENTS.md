# Project: ane-context-harness

Generation-neutral local context-intelligence harness for coding agents.

## Commands

- Install: `pip install -e .[test]`
- Run tests: `python3 -m pytest -q`
- Serve API: `python3 -m ane_context_harness.cli serve --port 8765`
- Build Core ML artifact (Python <= 3.13, needs `.[build]`):
  `~/.venvs/ane-p36/bin/python scripts/convert_model.py --seq-len 128 256`
- Validate (agreement + benchmarks + qualification, writes
  `~/.ane_context_harness/calibration_report.json`):
  `~/.venvs/ane-p36/bin/python scripts/calibrate_phase3.py`
- Phase 5 with arm C (frozen eval split): `~/.venvs/ane-p36/bin/python scripts/run_phase5.py`
  (needs coremltools on the interpreter; without it arm C is skipped, not faked)
- Re-validate a built artifact (write-once evidence, defaults to
  `--entry miniLM-L6-MMR1`): `~/.venvs/ane-p36/bin/python scripts/revalidate_artifact.py`
- Freeze/refresh evidence bundle: `python3 scripts/freeze_evidence.py`
  (verify with `ane-harness evidence verify`)

## Phase scope

Implemented: foundation (discovery/profiles/calibration), Phase 0 measurement
scaffold, Phase 1 deterministic indexing/retrieval, Phase 2 security layer,
Phase 3 Core ML reranker toolchain (manifest, conversion, HF-faithful tokenizer,
runtime fallback, calibration, evaluation; artifacts built at
`~/.ane_context_harness/phase3/build_cache/artifacts/`), Phase 4
tool-output compression (`compression/`, `/v1/context/compress-output`)
and provider adapters (`providers/`: Anthropic, OpenAI Responses,
OpenAI-compatible, Markdown — format-only, no network calls), Phase 5 end-to-end
A/B evaluation (`evaluation.py`, `scripts/run_phase5.py` →
`benchmarks/reports/phase5-ab-evaluation.*`; arms A/B/C measured).

Benchmark: 30 labelled tasks (10 small / 10 typical / 10 difficult) over three
fixture repos incl. `tests/fixtures/synthetic_hard_project/` (18 hard cases);
schema v2 with whole-repo-fits budget rejection; **frozen split**
`benchmarks/splits.json` (seed 20261002: dev 12 / eval 18, stratified,
write-once via `task_set_hash`) — **all gates run on the eval split only;
tuning happens on dev only**. Retrieval includes identifier subtoken splitting,
plural folding, file-level `file_symbols` (interface/type declarations
extracted), symbol-micro-term guards and score-first packing with
mandatory retention. Token counting is **pinned** to one deterministic backend
(`regex-heuristic`, `TOKEN_ESTIMATOR_VERSION="2"` — optional deps must never
move counts). Reports embed `METRIC_DEFINITIONS` (Recall@K, nDCG@10, MRR,
required-evidence recall) with per-task `ranked_chunk_ids` and named
aggregation methods.

Release gate **P3.6 passed** (2026-10-02): build on Python 3.13, 1,000-pair
agreement (min cosine 1.0, max abs logit 0.044 <= 0.05), all compute units
warm p50 1.7-8.2 ms <= 500 ms; qualified backend `coreml_all`.
Arm C end-to-end adoption is decided on the frozen eval split
(`docs/adr-003-arm-c-adoption.md`): measured, **not adopted as default**
(min required-evidence recall 0.0 on one eval task; median reduction 60.52%,
p50 31.34 ms, zero fallbacks). Arm B (deterministic) passes all gates
(median reduction 60.47%, min recall 1.0, p50 3.83 ms over the 18 eval tasks)
and is the shipped default. The earlier pre-split arm C figure (70.15% /
recall 1.0 / `supported`) is superseded — it predates the pinned token
estimator and the frozen split.

Decisions: `docs/adr-001-capability-based-runtime.md`,
`docs/adr-002-embedding-go-no-go.md` (embeddings no-go for v0.1),
`docs/adr-003-arm-c-adoption.md`, `docs/provider-evaluation-stages.md`
(stages 0-1 mock/dry-run implemented with `limits.max_provider_spend_usd`
default 0.0 = live disabled; stage 2 spec-only, not executed).

Not implemented: embeddings, outbound provider API calls (stage 2 not run),
source editing, shell execution.

## Test command

`python3 -m pytest -q` (config in `pyproject.toml`; `pythonpath=["src"]`).
Schema/split guards: `tests/test_task_schema.py`; eval-split gates:
`tests/performance/test_benchmark.py`, `tests/integration/test_phase5_evaluation.py`.
