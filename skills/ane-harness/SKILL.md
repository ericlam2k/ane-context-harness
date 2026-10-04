---
name: ane-harness
description: Show per-task evidence-trim totals after each coding task and cumulative totals at session end. Use after completing any coding task in a repository, and once when the session ends. Trimmed% is local evidence reduction, never a billing claim.
---

## When to Use
- After finishing a coding task: run one evidence check and show its one-line summary.
- At session end: show the daily totals.
- Skip silently if `ane-harness` is not on PATH. Never fail the session over this skill.

## Steps
1. Ensure the repo is indexed (once per repo; cheap to repeat):
   `ane-harness index --repo <path> --repo-id <repo>`
2. After the task, run:
   `ane-harness select --repo-id <repo> --task "<task>" --budget 2000`
3. Read the top-level `summary` line from its stdout JSON and show that
   single line to the user. Example:
    `ane-harness: evidence 7.1k of 211.2k retrievable · trimmed 96.6% in 165 ms`
4. At session end, run `ane-harness daily` and show both lines.

## Guidelines
- Never paste the full JSON output; the `summary` line is the whole report.
- For with/without comparison, `select --full` packs the whole repo — it
  bypasses selection AND redaction, so treat its output as secret-bearing
  and never paste it into chats; compare its token count only.
- The budget governs discretionary context only; required evidence is always
  kept. You never need to set or explain it.
- No other skills, configs, or network access required: the `ane-harness`
  binary installed from this repo is the only dependency.
