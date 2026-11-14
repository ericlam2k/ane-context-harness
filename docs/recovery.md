# Recovery hints and stated needs

Sometimes the evidence the task needs does not make it into the pack — the
budget had to cut it, or the agent knows exactly what it needs but the task
text never names it. This page is the full detail behind the short version in
the README. The harness says so in plain output, and gives the agent a way to
state the need directly.

## What happens when the budget cannot fit everything

The pack never silently drops things. Admission happens in passes, in order:

1. **Claims first.** Evidence the task itself points at — a symbol or path
   named in the task, or the matching test file when the task asks about
   tests — is admitted first, in score order, while it fits the budget.
2. **Breadth.** The best chunk of each remaining path, in score order, while
   budget remains — one file's best chunk before a second chunk of any other
   file.
3. **Depth.** Further chunks in score order, under the per-file and diversity
   rules.
4. **Tail.** A small reserved slice of the budget spends on small, high-value
   chunks that were crowded out of the core budget.

Two rules keep this honest. Only what you pin explicitly (`--explicit-path` or
an authority rule) may push the pack past the requested budget; inferred
evidence never can. And anything the pack had to leave out is counted in the
output — `claims_dropped_budget`, `claims_capped`, and friends under
`metrics.diagnostics` — never hidden. Chunks are admitted whole or not at all;
nothing is truncated, summarized, or rewritten to fit.

## Recovery hints: what to search next

When the pack misses evidence it was supposed to carry — a named symbol or
required path — the output carries a `recovery` block: up to five missed
items, each with the chunk, the path, the symbol, *why* it did not fit
(`budget`, `capped`, or `dropped`), and a ready-to-run search command. The
command is `rg -n` when ripgrep is on PATH, a `grep -nE` equivalent when it is
not, or an empty string — with a `recovery_tool` diagnostic saying neither
tool was found. The harness prints these commands; it never runs them. The
totals in the block are always exact; only the itemized listing is capped.
Hints fire only on evidence the task requires — never on discretionary cuts.
The block appears in `metrics.diagnostics`, and at the top level of CLI
`select` output and the `/v1/context/select` response.

A hint is an affordance, not a promise: it tells the agent where to look
next; it does not say the pack is complete.

## Stated needs: `--stated-symbol` and `--stated-need`

When the task text is not enough, say what you need directly:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug" \
  --stated-symbol calculate_discount \
  --stated-symbol src/billing/rates.py \
  --stated-need "rounding policy for loyalty points"
```

- `--stated-symbol` is repeatable. Each item is validated against the index
  at no model cost: an exact match on a symbol name up to case, identifier
  separators (`_`, `-`, `.`, `$`) and plural/inflection forms (applied in
  both directions), or an exact repository path (NFC-normalized, forward
  slashes). A resolved item merges into the same claim candidates as
  everything else and is admitted under the same budget-honest rules — there
  is no budget override and no bypass.
- `--stated-need` takes free text, mined with the same term extraction as the
  task text. Each mined term becomes a claim term only when it anchors to the
  index — see the gate below; the rest are dropped and disclosed.
- Unresolved items are never packed. They are reported in the
  `stated_need_resolution` diagnostic — one record per item, with what
  matched (or did not) and up to three nearest indexed symbols to try (ranked
  by shared identifier subtokens; zero shared subtokens is reported honestly,
  not papered over).

Resolution is an index lookup, not inference; it costs no model calls. The
`stated_need_resolution` diagnostic is present only when a stated flag was
given.

## The ask: `recovery_prompt`

When the pack had to cut required evidence, or a stated symbol could not be
resolved, the output carries a `recovery_prompt` — a plain-English line
naming what was missed (with up to three inline pointers, plus "+N more" when the rest does not fit) and teaching the exact flags to re-state the need.
On those runs, the end-of-run note gains the clause `· ask: re-select with
--stated-symbol if evidence misses`. When nothing is missing and nothing
stated is unresolved, neither the key nor the clause appears, and the output
is unchanged. The prompt appears in `metrics.diagnostics` and at the top
level of CLI `select` output and the `/v1/context/select` response.

The ask is an affordance disclosure, not a miss detector. The harness cannot
know that the task needed evidence it cut; it can only report that it cut
something, or that a name you stated was not found in the index. If the pack
covers the task, ignore the ask — re-selecting spends a turn the provider
bills.

## The need-text gate

Free-text needs are the one place an arbitrary term could ride into the pack,
so the gate keeps `--stated-need` honest. Each mined term stays a claim term
only when it anchors to the index:

- it equals an index symbol name up to case, identifier separators, and
  inflection forms (the same matching `--stated-symbol` uses);
- it is a subtoken of an index symbol name, matched without inflection folds —
  a bare stem is not a subtoken, so a term that only appears as a folded
  stem of a longer symbol never rides in; or
- it occurs in an indexed file path.

Terms that anchor nowhere are dropped from claim identification entirely, and
both halves are disclosed in the `stated_need_resolution_note` diagnostic —
`kept` (with a `matched_chunks` count per term) and `dropped`. The note is
present whenever `--stated-need` is given, including the honest empty case.
`matched_chunks` counts packed chunks citing the term; it is a citation
count, not an aim measure.

## Aim accounting: `stated_claim_summary`

When a stated flag is given, the output carries a `stated_claim_summary` with
three counts — `stated_symbol`, `stated_path`, `stated_need` — counting
packed chunks the claims-first pass admitted while citing a stated-origin
term (a resolved stated symbol, a matched stated path, or a gate-kept
stated-need term). The counts are not disjoint — one chunk can count once per
origin it cites — and their sum is not the pack size. The basis is the final
selected set after exclusions, counted only for claims-first admissions;
task-born claims never count. The summary appears in `metrics.diagnostics`
and at the top level of CLI `select` output.

The limit, stated plainly: a stated term that also appears verbatim in the
task text is credited as stated, and an incidental rider — a stated-anchored
claim whose chunk would have been packed anyway — is indistinguishable from
an aimed admission at runtime and is never upgraded to one. A non-zero count
means "a stated need was cited by a packed claim," not "this chunk is exactly
what the agent was after."
