# Changelog

Reconstructed from read-only `git log --oneline` and `--stat` output. Dates are commit dates, not separate release announcements.

## Unreleased

Packing:

- Select packs claims first under the token budget. Evidence your task names — a symbol or path, or the matching test file when the task asks about tests — is admitted while it fits; then the pack fills with the best chunk from each remaining path, then deeper coverage per path, then a small reserved tail for small, high-value chunks. Only explicit pins (`--explicit-path` or an authority rule) may push the pack past the requested budget; the harness never infers past it. Claims that cannot fit are counted in the output (`claims_dropped_budget`, `claims_capped`), never silently dropped.
- Claims are admitted in task-aware order: when claims compete for the last fitting slot, the claim whose evidence the task text actually asks about wins — the shared rare terms it accounts for weigh more than common ones.

Saying what you need:

- `--stated-symbol` (repeatable) and `--stated-need` (free text) let you declare what the task needs. Each stated symbol or path is checked against the index at no model cost; resolved items join the pack under the same budget rules — no override. Unresolved items are never packed; the output reports them with the nearest indexed symbols to try.
- Free-text needs must anchor to the index: a mined `--stated-need` term counts only when it matches an indexed symbol name, a plain symbol subtoken, or an indexed file path. Terms that do not anchor are dropped, and the drops are disclosed in the `stated_need_resolution_note` diagnostic.

When evidence is missing:

- The output carries a `recovery` block — up to five missed items with the path, the symbol, why each did not fit, and a ready-to-run search command (`rg -n` when ripgrep is on your PATH, a `grep -nE` equivalent without it, or an empty command with a `recovery_tool` note when neither exists). The harness prints these commands; it never runs them.
- The output can ask you back: when the pack cut required evidence or a stated symbol was unresolved, a one-line `recovery_prompt` names what was missed and the flags to re-state the need, and the end-of-run note gains the clause `· ask: re-select with --stated-symbol if evidence misses`. When nothing is missing, the output is unchanged.
- Aim accounting: when you use the stated-needs flags, the output carries a `stated_claim_summary` with per-origin counts of packed chunks that entered through the claims-first pass while citing a stated term. Counts are per cited origin, not disjoint, and their sum is not the pack size; a stated term that also appears verbatim in the task text is credited as stated.

Docs:

- The README and its translations document stated needs, recovery hints, and the claims-first packing contract in plain English; every localized README now notes that English is the canonical README and translations may lag.

Agent wiring:

- `ane-harness install` detects OpenCode, Claude Code, and agents-compatible hosts (~/.agents/skills) and wires the skill (and the OpenCode usage plugin) additively: nothing is overwritten silently — differing files are backed up next to the original and recorded in a 0600 manifest at ~/.ane_context_harness/install-manifest.json, and `--undo` restores byte-identically. `--dry-run` previews the exact plan; a concurrent run is refused via a short-lived lock; the manifest records every step before the file it describes is written, so a crash never leaves an installed file unrecorded. 100% offline; on Windows, real writes are refused with a clear message until the paths are verified (detection and --dry-run work everywhere).
- `ane-harness install mcp` wires the ane-harness MCP server: for Claude Code it adds the entry under `mcpServers` in ~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json) with the same backup/manifest/undo guarantees, never touching foreign keys; for OpenCode it prints the exact config block instead of writing, because opencode.json is JSONC-tolerant (comments allowed) and the installer never risks reformatting it.

Packaging:

- The package now ships everything the installer needs: the agent skill (`skills/ane-harness/SKILL.md`) and the OpenCode usage plugin (`integrations/opencode/ane-harness-usage.ts`) are included in both wheel and sdist, so `pip install ane-context-harness` gives a working `ane-harness install` / `install mcp` with no editable checkout. A LICENSE file now matches the MIT license the metadata already declared.
- One test fixture is deliberately left out of the sdist only: `tests/fixtures/synthetic_hard_project/secret_link` is a symlink to `/etc/passwd`, and installers reject tarballs that contain absolute-path symlinks, so without this the sdist could not be installed at all. The fixture is unchanged in the repository. Tests run from an unpacked sdist will fail on the one symlink-escape case; every other test is unaffected.

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
