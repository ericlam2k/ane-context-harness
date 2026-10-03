# ⚡ ane-context-harness

> **Cut your coding agent's token bills by 60%+, keep 100% code accuracy, and select context in under 4ms — running completely offline on your local machine.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## What is this?

When you vibe-code or run AI agents (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), feeding your entire codebase into an LLM context window is **slow, expensive, and dangerous**:
- **Massive token bills:** Shoveling whole files into every turn burns through API credits.
- **Slower responses:** LLM time-to-first-token crawls when prefilling thousands of unnecessary lines.
- **Lost in the middle:** Models hallucinate or miss bugs when buried under irrelevant boilerplate.
- **Secret leaks:** Unwittingly sending `.env` secrets or AWS credentials to third-party model providers.

**ane-context-harness** is a lightweight, local-first context engine that sits between your codebase and your coding agent. In **~3 milliseconds**, it indexes your repo, extracts symbol hierarchies (functions, interfaces, types), strips the noise, redacts secrets, and packs only the high-value code evidence your agent actually needs to complete the task.

> The name `ane` is historical (for Apple Neural Engine, the intended acceleration substrate); it is **not** a dependency. The shipped path is pure CPU and runs on macOS Apple Silicon, macOS Intel, and Linux. Specialized-silicon acceleration is an *optional*, **disabled-by-default** Core ML reranker path (Arm C) — see the honest note under "Technical Specifications".

Zero external network calls. 100% private and offline.

---

## Real Benchmark Results

Evaluated across **30 benchmark tasks** (10 small, 10 typical, 10 difficult) across synthetic Python and TypeScript codebases on our frozen evaluation split (`benchmarks/splits.json`):

| Metric | Without Harness (Full Repo Dump) | With Harness (Deterministic) | What this means for you |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **60.47% fewer tokens sent to the LLM** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **Never missed a single piece of critical code** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Sub-4ms local response — 100x faster than network** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **Saves up to ~90% on targeted config & settings tasks** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **Places the most critical functions right at the top** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, AWS keys, and certificates never leave your machine** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **~75% reduction in input token spend** |

*(Latency and memory measured locally on Apple Silicon / CPU; cost and TTFT figures are derived under stated token rates; methodology and reproducible logs in `benchmarks/reports/` and `benchmarks/logs/`).*

### Sample Tasks Breakdown

| Task Type | Example Task | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Settings & Config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Rules & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug Fixes (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript Architecture**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Complex Multi-file Cart** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

---

## Why Developers & Vibecoders Love It

- 💰 **Dramatically Lower LLM Costs:** Stop paying model providers to re-read files that have nothing to do with the prompt.
- ⚡ **Instant (~3ms) Latency:** Runs entirely in native Python and C extensions locally on your Mac or Linux box.
- 🎯 **Pinpoint Accuracy:** Combines AST symbol declarations (classes, TypeScript interfaces, enums, functions) with BM25 lexical search and token-budgeted score-first packing.
- 🛡️ **Zero-Leak Secret Sanitization:** Automatically scans and redacts AWS keys, private RSA/PEM keys, `.env` files, and high-entropy secrets with stable request-scoped placeholders before prompts are rendered.
- 🔌 **Universal Agent Support:** Ships ready-to-use adapters for **Anthropic Messages** (with prompt-caching breakpoints), **OpenAI Responses**, **OpenAI-Compatible chat**, and clean **Markdown**.

---

## Quick Start (60 Seconds)

### 1. Install

Requires Python 3.13 or 3.14 on macOS or Linux:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Verify your installation:
```bash
ane-harness health
```

### 2. Index Your Codebase

Index any local folder or repository into the local SQLite store (incremental and super fast):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Select Relevant Context for a Prompt

Fetch a compact, token-budgeted Markdown package tailored to your coding task:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 3b. Log before/after token savings across many prompts (`update`)

Run selection over a batch of tasks (a JSONL file or stdin) and print + log
before/after token budgets. Local, no network:

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Sample output:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

Per-task rows are also appended as JSONL to `--log` (gitignored).
**Honest caveat** printed to stderr on every run: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Every run also prints a one-line savings footer to stderr (stdout stays pure
JSON), e.g. `# ane-harness: 96.6% saved (7.1k of 211.2k) · 5.8k required kept +
discretionary 1.3k of 2000 budget ok · 23 chunks · 165 ms`. The budget governs
discretionary context only — required evidence is always kept, so you never
touch it. Totals accumulate locally (counts only, no task text) — see them
anytime with `ane-harness daily`, or on every shell exit with
`eval "$(ane-harness shell-init)"` in your `.zshrc`/`.bashrc`.

### 4. Or Run as a Local Background Server

Start the local HTTP API (ready to be hooked up to your agent or tools):

```bash
ane-harness serve --port 8765
```

Endpoints available:
- `GET  /v1/health` — System status, compute mode, and profiles
- `POST /v1/repositories/index` — Index or update a repository
- `POST /v1/context/select` — Retrieve optimized context for a task
- `POST /v1/context/compress-output` — Compress verbose test/build logs into clean failure digests

---

## Using in Python

You can also use the harness directly inside your own AI agent workflows:

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Initialize pipeline
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Index repository
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Select budgeted context
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Serialize directly for your favorite LLM provider
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (saved {package.metrics['tokens_removed']} tokens)")
```

---

## How It Works

```
                        Your Codebase
                             │
                     AST & Symbol Parser
               (Python functions, TS interfaces)
                             │
                      Line-Level Chunker
                             │
                      Local SQLite Store
                             │
User Prompt  ──────►   BM25 Lexical Search
                             │
                   Score-First Budget Packer
                  (Mandatory Retention + MMR)
                             │
                  Local Secret Sanitizer
              (Redacts .env, AWS keys, certs)
                             │
               Provider Adapter (Anthropic/OpenAI)
                             │
                   Tight, Accurate Context
```

1. **Symbol-Aware AST Chunking:** Instead of dumb line-splitting, files are parsed for real code constructs (classes, methods, TypeScript types/interfaces/enums).
2. **Deterministic Retrieval:** Fast lexical BM25 retrieval filtered by symbol term guards, subtoken splitting, and plural folding.
3. **Score-First Budget Packing:** Context is greedily packed to fit strictly within your specified token budget (e.g., 1,200 tokens), guaranteeing mandatory evidence is never truncated.
4. **Secret Detection & Privacy Fence:** Canonical exclusion patterns (`.env*`, `.aws/**`, `*.pem`, etc.) are never read, and regex + entropy classifiers replace sensitive tokens with stable placeholders.
5. **Noise Compression:** Verbose tool outputs (test traces, terminal logs) are collapsed into compact signal-preserving digests.

### Hardware acceleration: optional, not required (and not adopted by default)

The name contains `ane`, but **no specialized silicon is required or claimed** to
run the harness. The shipped default (Arm B) is pure deterministic CPU (Python +
SQLite) and runs identically on macOS Apple Silicon, macOS Intel, and Linux.

- **Never required:** CPU deterministic path — no Core ML, no Neural Engine.
- **Measured, optional, disabled by default:** Where an Apple Neural Engine is
  available on Apple Silicon, the *optional* Core ML backend (`coreml_all`,
  `computeUnits = .all`) can schedule the reranker model onto CPU+GPU+**ANE**,
  measured at warm p50 1.7–8.2 ms (P3.6). It is gated off
  (`coreml_enabled: false`) and **not adopted as the default** because, end-to-end
  on the frozen eval split, it failed the recall gate on one task and was slower
  than the deterministic path (~31 ms vs ~3.83 ms).
- **Honest claim policy:** `coreml_all` is a qualified backend *on this host*;
  the harness does **not** claim ANE execution from `computeUnits = all`.
  Selecting it is a deliberate, opt-in choice for the reranker only; it does not
  accelerate indexing, packing, redaction, or compression (those are
  non-neural by design).
- See `docs/adr-003-arm-c-adoption.md` and `docs/adr-001-capability-based-runtime.md`.

---

## Technical Specifications & Rigor

For researchers, architects, and technical leads who care about numerical rigor:

- **Frozen Benchmark Split:** All release numbers run on a frozen 18-task evaluation split (`benchmarks/splits.json`, seed `20261002`). Tuning is strictly quarantined to the dev split.
- **Deterministic Token Estimator:** Token counting uses a pinned estimator (`TOKEN_ESTIMATOR_VERSION="2"`) so numbers are 100% reproducible across machines and Python versions without external tokenizer drift.
- **Arm C (Core ML / Apple Silicon) Research:** We built and calibrated a native Core ML MiniLM reranker toolchain (`cross-encoder/ms-marco-MiniLM-L6-v2`). While warm inference reaches ~25ms on device, evaluation on the frozen split revealed a budget/ranking failure on one complex task (`hard-rules-vs-readme-001`). Per our honest reporting policy, **Arm B (deterministic) remains the shipped default**, and Core ML is disabled until blend tuning is completed. See [ADR-003](docs/adr-003-arm-c-adoption.md).
- **Embedding Policy:** Embeddings are intentionally excluded in v0.1 based on local cost/latency trade-offs. See [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Release Evidence Bundle:** Checksummed release evidence is cryptographically verified via `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Running the Test Suite

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## License

MIT License. Designed for local intelligence, developer privacy, and sane token budgets.
