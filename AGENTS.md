# Project: ane-context-harness

Generation-neutral local context-intelligence harness for coding agents.

## Commands

- Install: `pip install -e .[test]`
- Run tests: `python3 -m pytest -q`
- Serve API: `python3 -m ane_context_harness.cli serve --port 8765`
- Verify release evidence: `ane-harness evidence verify ane-context-harness-evidence-v0.1`

## Public vs private boundary (read first)

- **PUBLIC** (this repo): portable cpu+gpu line. Deterministic retrieval
  engine, symbol-aligned chunking, multi-pass query expansion, summaries and
  the daily usage ledger, provider adapters, MCP, frozen-split eval gates.
  No accelerator code, no model artifacts, no ANE blobs anywhere in history.
  CI on Ubuntu without any ML stack proves portability.
- **PRIVATE** (commercial distribution, separate repo): everything here PLUS
  the Core ML toolchain, conditional ANE reranker, Phase 5/6 harnesses and
  ANE reports, arm-C adoption docs. ANE-capable code never merges here.

## Phase scope

Implemented: foundation (discovery/profiles), Phase 0 measurement
scaffold, Phase 1 deterministic indexing/retrieval (symbol-aligned greedy
chunking, multi-pass query expansion with max fusion), Phase 2 security
layer, Phase 4 tool-output compression (`compression/`,
`/v1/context/compress-output`) and provider adapters (`providers/`: Anthropic,
OpenAI Responses, OpenAI-compatible, Markdown — format-only, no network
calls), savings UX (`summary.py` one-line footers, `usage.py` daily ledger,
`daily`/`shell-init` commands, `skills/ane-harness/SKILL.md`).

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

Deterministic arm: median reduction ~60-63%, min required-evidence recall 1.0,
p50 single-digit ms over the 18 eval tasks; shipped default on every host.

Decisions: `docs/adr-001-capability-based-runtime.md`,
`docs/adr-002-embedding-go-no-go.md` (embeddings no-go for v0.1),
`docs/provider-evaluation-stages.md`
(stages 0-1 mock/dry-run implemented with `limits.max_provider_spend_usd`
default 0.0 = live disabled; stage 2 spec-only, not executed).

Not implemented: embeddings, hardware acceleration (private distribution),
outbound provider API calls (stage 2 not run),
source editing, shell execution.

## Test command

`python3 -m pytest -q` (config in `pyproject.toml`; `pythonpath=["src"]`).
Schema/split guards: `tests/test_task_schema.py`; eval-split gates:
`tests/performance/test_benchmark.py` (frozen eval split: reduction, recall, latency).

## Dogfood: show savings after each task

After every task in this repo, run one
`ane-harness select --repo-id <repo> --task "<task>" --budget 2000`, read the
top-level `summary` line from its stdout JSON, and show that single line to
the user. Never paste full JSON. At session end, run `ane-harness daily`.
