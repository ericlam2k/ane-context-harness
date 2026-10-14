# Changelog

Reconstructed from read-only `git log --oneline` and `--stat` output. Dates are commit dates, not separate release announcements.

## Unreleased

No new user-facing changes yet.

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
