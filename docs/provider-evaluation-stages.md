# Provider evaluation — staged plan (stages 0-1 implemented, stage 2+ NOT EXECUTED)

Status: **stages 0 and 1 implemented and tested; stage 2 (live) deliberately not
executed in this release candidate.** No outbound provider call has been made or
is made by the test suite. Cost figures anywhere in this plan are DERIVED from
token counts × a stated price; they are never billed amounts.

## Stage 0 — mock serialization (implemented)

Provider adapters (`providers/anthropic.py`, `providers/openai.py`,
`providers/openai_compat.py`, `providers/markdown.py`) build request bodies or
rendered prompts from an `EvidencePackage` only. They import no network
libraries; `tests/integration/test_provider_adapters.py` asserts deterministic,
equivalent evidence across adapters, and `tests/test_provider_dryrun.py`
AST-checks the package for network imports.

## Stage 1 — dry-run with derived cost and spend cap (implemented)

`providers/dryrun.py::dry_run()` serializes a package for a provider,
reports the token count and the **derived** cost under a stated price, and
answers whether a live call *would* be allowed under
`limits.max_provider_spend_usd`. It performs **zero network calls**
(`network_calls: 0`); a test runs it with `socket.socket` patched to raise.

Spend cap semantics (config `limits`):

- `max_provider_spend_usd: 0.0` (default) — live provider calls are
  **disabled**; only stages 0-1 may run.
- The cap is a per-run ceiling for the future stage 2, checked against the
  derived pre-flight estimate before any call could be placed.

## Stage 2 — controlled live evaluation (SPEC ONLY, NOT EXECUTED)

Preconditions, all required:

1. Explicit human approval of the run and of the cap value; config sets
   `max_provider_spend_usd > 0` deliberately (default remains 0.0).
2. Credentials come from environment variables only, never from repository
   files or benchmark fixtures; the evidence bundle records that no key
   material is stored.
3. Pre-flight: run stage 1 for every task, sum the derived estimates, and
   refuse the run when the sum exceeds the cap. Record the estimate next to
   the measured spend.
4. The evaluation reuses the frozen eval split
   (`benchmarks/splits.json`) and reports per-task results with the
   `METRIC_DEFINITIONS` aggregation methods; baseline (arm A) remains
   "full context" as measured locally — provider inference quality numbers
   are reported separately and never merged with local latency/memory
   figures.
5. Hard limits: fixed task list (no ad-hoc prompts), fixed model ids recorded
   in provenance, max_tokens bounded, retries capped, and abort on first
   spend-cap breach. Every call logs provider, model, tokens, derived cost.

Out of scope for this milestone: executing stage 2, any provider performance
claim, and any TTFT/provider-cost number presented as measured.
