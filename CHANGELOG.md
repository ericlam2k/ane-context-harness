# Changelog

Reconstructed from read-only `git log --oneline` and `--stat` output. Dates are commit dates, not separate release announcements.

## Unreleased

- Budget-honest claims-first packing: named evidence (a symbol or path the task names, or the matching test file when the task asks about tests) is admitted first while it fits the budget — then breadth (the best chunk of each remaining path), then depth, then a small reserved tail for small, high-value chunks crowded out of the core budget. Only explicit pins (`--explicit-path` or an authority rule) may push the pack past the requested budget; inferred evidence never can. Claims that do not fit are counted (`claims_dropped_budget`, `claims_capped`) in the output, never silently dropped.
- Claim extraction and a deterministic shortlist seam: the selector identifies claim candidates before the per-file and budget caps and scores every one of them before capping, so a claim outside the top candidates still reaches the shortlist. The shortlist diagnostics (`rerank_shortlist`) are inert on the deterministic backend.
- Recovery hints: when the pack misses required evidence, the output carries a `recovery` block — up to five missed items with path, symbol, why each did not fit (`budget`, `capped`, or `dropped`), and a ready-to-run search command (`rg -n` when ripgrep is on PATH, a `grep -nE` equivalent without it, or an empty command with a `recovery_tool` diagnostic when neither exists). The harness prints these commands; it never runs them. The block is additive and appears only on a miss.
- Stated needs: `--stated-symbol` (repeatable) and `--stated-need` (free text) let the caller declare what it needs. Each stated symbol or path is validated against the index at no model cost (exact match up to case, identifier separators, and inflection forms, or an exact repository path); resolved items merge into claim candidates under the same budget-honest rules — no budget override. Unresolved items are never packed and are reported in the `stated_need_resolution` diagnostic with nearest indexed symbols to try.
- Ask affordance: a `recovery_prompt` line, present only when the pack cut required evidence or a stated symbol was unresolved, naming what was missed and the flags to re-state the need. On those runs the end-of-run note gains the clause `· ask: re-select with --stated-symbol if evidence misses`. Absent the firing condition the output is unchanged.
- Need-text gate: mined `--stated-need` terms become claim terms only when they anchor to the index (symbol name up to case/separators/inflections, a plain symbol subtoken without inflection folds, or an indexed file path). Dropped terms are disclosed in the `stated_need_resolution_note` diagnostic.
- Claim-origin tagging: the output carries a `stated_claim_summary` (`stated_symbol`, `stated_path`, `stated_need`) counting packed chunks the claims-first pass admitted while citing a stated-origin term, present only when stated flags were given. Counts are per cited origin — not disjoint, and not the pack size. A stated term that also appears verbatim in the task text is credited as stated.

## 0.2.0 — 2026-10-14

- Select now refreshes the file index first, so picks never use out-of-date files.
- Update can handle many tasks at once and limit search to chosen folders (scope paths are folder limits for one run).
- You can exclude whole folders with `--exclude-path`, and get a warning when an exclude pattern matches nothing.
- The end-of-run note (footer) now states the over-budget amount with a must-keep versus extra split when picks pass the token budget (token budget means the size limit for picked text).
- New `ane-harness meter` command checks real provider-measured input size with and without packing, using only free models.
- Index output now reports `skipped_by_reason`, which counts skipped files by cause such as binary, too large, or blocked.
- You now see a plain warning when excludes remove every candidate so nothing is left to send.
- Opening the local store now fails with a plain path-and-permission hint instead of a raw database error.
- Compact evidence view (TOON-subset, a shorter formatting-only layout) is available as an opt-in rendering choice.
- Same-task comparison reports now include real headroom and TOON format numbers using only public functions.

## 0.1.0a1 — approximate 2026-10-02

- First public release candidate with the portable file-search and packing engine that picks evidence for a task.
- Initial version string `0.1.0a1` seen in the 2026-10-02 initial commit; `v0.1.0` tag added the same day for CI (approximate: tag points outside the main line in this checkout).
