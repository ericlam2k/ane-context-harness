# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Cut the context your agent reads by 60%+, keep every required line, and select context in under 4ms — running completely offline on your local machine.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## What is this?

When you vibe-code or run AI agents (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), feeding your entire codebase into an LLM context window is **slow, wasteful, and dangerous**:
- **Bloated context:** Shoveling whole files into every turn buries the model in irrelevant boilerplate — and the provider counts every token, reused or not.
- **Slower responses:** LLM time-to-first-token crawls when prefilling thousands of unnecessary lines.
- **Lost in the middle:** Models hallucinate or miss bugs when buried under irrelevant boilerplate.
- **Secret leaks:** Unwittingly sending `.env` secrets or AWS credentials to third-party model providers.

**ane-context-harness** is a lightweight, local-first context engine that sits between your codebase and your coding agent. In **~3 milliseconds**, it indexes your repo, extracts symbol hierarchies (functions, interfaces, types), strips the noise, redacts secrets, and packs only the high-value code evidence your agent actually needs to complete the task.

> The name `ane` is historical; it is **not** a dependency. The shipped path is pure CPU and runs on macOS Apple Silicon, macOS Intel, and Linux. Hardware acceleration lives in a separate private distribution.

Zero external network calls. 100% private and offline.

---

## Real Benchmark Results

Evaluated across **30 benchmark tasks** (10 small, 10 typical, 10 difficult) across synthetic Python and TypeScript codebases on our frozen evaluation split (`benchmarks/splits.json`):

| Metric | Without Harness (Full Repo Dump) | With Harness (Deterministic) | What this means for you |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **Sends 60.47% less to the LLM** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **Never missed a single piece of critical code** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Sub-4ms local response — 100x faster than network** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **Saves up to ~90% on targeted config & settings tasks** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **Places the most critical functions right at the top** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, AWS keys, and certificates never leave your machine** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Sends ~75% less per task at the stated rate — your bill itself moves with how much the provider reuses instead of re-reading** |

*(Latency and memory measured locally on Apple Silicon / CPU; cost and TTFT figures are derived under stated token rates; methodology and reproducible logs in `benchmarks/reports/` and `benchmarks/logs/`).*

### Sample Tasks Breakdown

| Task Type | Example Task | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Settings & Config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Rules & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug Fixes (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript Architecture**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Complex Multi-file Cart** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Token savings, measured (current main)

How to read this chart: every job asked the tool "what should the AI read for this task?". The left panel compares, by job size, how much text you'd send if you sent the whole codebase (grey) versus what the harness picked (green) — the number above each green bar is what you send now and how much smaller that is. Harder jobs need more files, so the green bar grows — but the needed files were kept **every single time**, which is the whole point: smaller is only good if nothing important is missing. The right panel shows the same choice sent three ways — full detail, a readable middle ground, and the shortest wrapping — shorter is cheaper, and the wrapping never changes *what* gets picked.

![Less to read by job size, plus three wrappings of the same answer](docs/token-savings.png)

Measure with `PYTHONPATH=src python3 scripts/measure_token_savings.py`, draw with `scripts/plot_token_savings.py` (frozen eval split, one pinned token counter).

### Same exercise against real tools (no keys, no accounts)

How to read this chart: it's a race on the same 18 jobs with the same ruler — "how many tokens does the middle job hold, and did anything needed get lost?". The first chart is the headline: sending everything is the costly default, the outside rewrite tool actually sends *more* than needed and once lost a config file the grader required (marked FAIL), while our two modes are shortest and kept the needed files every time (PASS). The second chart shows the details behind it — what selection alone saves, and how the same selection shrinks again just by choosing a shorter wrapping. PASS/FAIL here means exactly one thing: the pieces the benchmark grader says are required came back in the pack.

![Same 18 jobs: send-everything vs an outside rewrite tool vs ours](docs/head-to-head.png)

![Selection medians and the same pack in four wrappings, with per-job examples](docs/same-exercise-comparison.png)

Reproduce: `pip install headroom-ai toon-format`, then `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, draw with `scripts/plot_same_exercise.py`. Task-blind rewriting sends more than selecting and keeps no survival gate; the real TOON encoder falls back to per-row mappings on multiline code while our compact keeps CSV headers with verbatim rows.

### Conversation savings, measured

How to read this: one job is never one question — the agent asks, then follows up, then verifies. This bench replays the same 3-turn conversation per job three ways: sending the whole codebase every turn (149,490 tokens), one trimmed pack (17,094), and three carried packs where each follow-up keeps everything the earlier turns found (51,940). The carried conversation sends **about a third** of the no-harness cost — 97,550 fewer tokens, 65.3% less — and the needed files survived all 72 turns (recall 1.0 every turn; a turn that loses a needed file derails the conversation, so that gate is load-bearing, not decorative).

Reproduce: `PYTHONPATH=src python3 scripts/bench_conversation.py` (frozen eval split, one pinned token counter; writes `benchmarks/reports/conversation-bench-eval.json`). Boundary, stated plainly: no model reads these packs, follow-ups are fixed strings rather than real agent reactions, nothing is billed, no job is actually completed. It measures the half we feed — the picking and carrying — not the loop itself.

### What happens to each file

Four documented rules, no model involved, no exceptions: files you pin (or the grader requires) travel **byte-exact, always**. Code, config, and diffs keep their structure — the picker selects whole symbols, never rewrites them. Only **logs and noisy tool output** get collapsed (repeated progress lines, duplicate tracebacks, install spam fold into a summary line that says what was removed). Prose travels as picked, never reworded — there is no neural rewriter, so nothing can paraphrase your docs into something they didn't say. Every pack lists, per file, which rule applied — check `diagnostics.routing` in any report and argue with it.

![Concept illustration: comparing context-fetching approaches on one yardstick — send-everything, naive window, summarizer, and AST-guided selection](docs/ane-benchmark-concept.jpg)

*Concept illustration, not measured results — the token scale and figures inside are illustrative. All real measurements are in the tables and measured charts above.*

---

## Why Developers & Vibecoders Love It

- 💰 **Less context per task, stable output:** Skip files that have nothing to do with the prompt — and stable output lets the provider reuse what it already read instead of charging again. Cut% measures local context reduction, never your bill.
- ⚡ **Instant (~3ms) Latency:** Runs entirely in native Python and C extensions locally on your Mac or Linux box.
- 🎯 **Pinpoint Accuracy:** Combines AST symbol declarations (classes, TypeScript interfaces, enums, functions) with BM25 lexical search and token-budgeted score-first packing.
- 🛡️ **Zero-Leak Secret Sanitization:** Automatically scans and redacts AWS keys, private RSA/PEM keys, `.env` files, and high-entropy secrets with stable request-scoped placeholders before prompts are rendered.
- 🔌 **Universal Agent Support:** Ships ready-to-use adapters for **Anthropic Messages** (with prompt-caching breakpoints), **OpenAI Responses**, **OpenAI-Compatible chat**, and clean **Markdown**.

![Concept illustration: heavy baseline versus lean harness — fewer tokens, full accuracy kept](docs/ane-concept-dashboard.jpg)

*Concept illustration — the token scale and table figures inside are illustrative. Real measurements: 782 vs 3,213 median tokens (60.47% cut), recall 1.0, see the benchmark tables above.*

---

## How it works

![How your words become what the AI reads: one real benchmark job traced end to end — plain words in, every chunk scored, why each card flew, 369 of 1,236 tokens](docs/context-packing-overview.png)

One-page explainer generated from the real pipeline (`scripts/plot_packing_overview.py`): one real benchmark job traced end to end. Your words in, small words dropped, every chunk of the repo scored, the winners fly with their reasons attached — and the AI reads 369 tokens instead of the whole 1,236 (70% less, and nothing the answer key needs is missing). Every number in it is measured, not illustrated.

![Concept illustration: raw truncation breaks ASTs, imports, and references — the harness keeps code signatures, AST structure, and essential dependencies](docs/ane-concept-generic.jpg)

*Concept illustration for the idea above — the code inside is graphic art, not a real trace. The measured real trace is the chart directly above.*

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

### 1b. One-command setup + prove-it (adoption gates)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` is unlabelled: it reports median reduction + p50 latency and
`recall: not_applicable`. Recall proofs need hand-labelled tasks (the
frozen `benchmarks/splits.json` machinery); unlabelled runs never claim
recall.

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

  ### 3b. Log before/after context cuts across many prompts (`update`)

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

Every run also prints a one-line cut footer to stderr (and the same
line as the `summary` key in stdout JSON), e.g.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Plain words only —
no jargon, no `#` heading markup. Totals accumulate locally (counts only, no
task text) — see them
anytime with `ane-harness daily`, or on every shell exit with
`eval "$(ane-harness shell-init)"` in your `.zshrc`/`.bashrc`.

Agents get the same behavior dependency-free via the bundled skill:
`skills/ane-harness/SKILL.md` — copy it into your agent's skills directory
and cut totals surface automatically after each task, no other setup. For
OpenCode/Claude/agent-compatible hosts it also works globally, no per-project
install: `~/.config/opencode/skills/`, `~/.claude/skills/`, or
`~/.agents/skills/` (new sessions pick it up).

### 3c. Proxy mode for agents without native integration (`proxy`)

Pipe tasks in on stdin (one `{"task": "..."}` or bare task per line),
get evidence Markdown back on stdout — no skill, MCP, or HTTP needed:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout is pure Markdown (one doc per task, `---`-separated, with
`<!-- ane-harness task N/M ... -->` boundaries); per-task cut
footers go to stderr. Omit `--repo` when the repo-id is already indexed.

### 4. Or Run as a Local Background Server

> **Agents: do NOT run this inside an agent turn.** `serve` (like `mcp`)
> never exits — a tool call that launches it blocks forever, so the turn
> never completes and every later prompt queues behind it. Bare
> `update`/`proxy` with no `--tasks-file` on an interactive terminal exit
> 2 with a hint instead of waiting on stdin. Inside agent turns use only
> one-shot commands (`index`, `select`, `prove`, `daily`, `health`). Run
> the server detached from a real terminal
> (`nohup ane-harness serve --port 8765 &`) or not at all.

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

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
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

![Concept illustration: system prompt and payload through the filter into a clean payload — the harness filtering pipeline](docs/ane-proxy-tracker-concept.jpg)

*Concept illustration for the pipeline above — the dashboard inside is graphic art, not a screenshot of a real tool.*

### Hardware acceleration: separate private distribution

The name contains `ane`, but **no specialized silicon is required or claimed** to
run the harness. The shipped engine is pure deterministic CPU (Python +
SQLite) and runs identically on macOS Apple Silicon, macOS Intel, and Linux.
Neural-hardware acceleration is maintained separately and is not part of
this repository.

---

## Technical Specifications & Rigor

For researchers, architects, and technical leads who care about numerical rigor:

- **Frozen Benchmark Split:** All release numbers run on a frozen 18-task evaluation split (`benchmarks/splits.json`, seed `20261002`). Tuning is strictly quarantined to the dev split.
- **Deterministic Token Estimator:** Token counting uses a pinned estimator (`TOKEN_ESTIMATOR_VERSION="2"`) so numbers are 100% reproducible across machines and Python versions without external tokenizer drift.
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
