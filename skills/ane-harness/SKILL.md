---
name: ane-harness
description: Show context-token savings after each coding task and daily totals at session end. Use after completing any coding task in a repository, and once when the session ends.
---

## When to Use
- After finishing a coding task: run one savings check and show its one-line summary.
- At session end: show the daily totals.
- Skip silently if `ane-harness` is not on PATH. Never fail the session over this skill.

## Steps
1. Ensure the repo is indexed (once per repo; cheap to repeat):
   `ane-harness index --repo <path> --repo-id <repo>`
2. After the task, run:
   `ane-harness select --repo-id <repo> --task "<task>" --budget 2000`
3. Read the top-level `summary` line from its stdout JSON and show that
   single line to the user. Example:
   `# ane-harness: 96.6% saved (7.1k of 211.2k) · 61 chunks · 165 ms`
4. At session end, run `ane-harness daily` and show both lines.

## Guidelines
- Never paste the full JSON output; the `summary` line is the whole report.
- The budget governs discretionary context only; required evidence is always
  kept. You never need to set or explain it.
- No other skills, configs, or network access required: the `ane-harness`
  binary installed from this repo is the only dependency.
