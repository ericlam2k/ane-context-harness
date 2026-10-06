"""Conversation bench on the frozen EVAL split (never dev — dev is for tuning).

Same 3-turn working conversation per task, three ways:

  1. raw    — no harness: full context re-sent every turn (3x baseline).
  2. origin — first-slice trim only: one harness pack (today's one-shot).
  3. multi  — first slice + carried conversation: T1 packs the task as-is,
              T2 appends "implement the fix" and carries forward ALL T1
              evidence paths as explicit pins, T3 appends "verify against
              the tests" and carries all T1+T2 paths. Carry is full
              evidence, not mandatory-only — pins protect only what was
              mandatory before, so mandatory-only carry-forward sheds files
              when the focus shifts.

Turns differ by task text plus carried pins (public line has no packing
profiles — the carry rule is the lever being measured). Tokens are counted
the same way in all arms (pinned estimator over the exact bytes that
would be sent). The fair end-to-end question is multi vs raw-doing-the-
same-3-turns; origin is shown as the one-shot reference.

Gates: min required-evidence recall 1.0 on every measured turn (a turn
that loses required evidence derails the conversation); multi total must
stay below 3x baseline total (the conversation must still save vs raw).

Writes benchmarks/reports/conversation-bench-eval.json (+ .md). Eval
only by construction: any task id outside splits.json "eval" aborts.
"""
from __future__ import annotations

import json
import shutil
import statistics
import tempfile

from ane_context_harness import schemas
from ane_context_harness.benchmark import (
    FIXTURE_REPO_PATHS,
    baseline_full_context_tokens,
    load_task_split,
    required_chunks_covered,
)
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness import tokens as tokens_mod

T2_SUFFIX = " — implement the fix"
T3_SUFFIX = " — verify against the tests"


def _pack_tokens(evidence) -> int:
    return sum(tokens_mod.count(e["content"]) for e in evidence)


def _measure(pipeline, repo_id: str, task, task_text,
             explicit: list) -> dict:
    req = schemas.SelectRequest(
        repository_id=repo_id,
        task=task_text,
        token_budget=task.token_budget,
        explicit_paths=list(explicit or []),
        options={},
    )
    pkg = pipeline.select_context(req)
    chunks = pipeline._storage_for(repo_id).load_chunks()
    base = baseline_full_context_tokens(chunks)
    return {
        "tokens": _pack_tokens(pkg.evidence),
        "baseline": base,
        "recall": round(required_chunks_covered(
            pkg.evidence, task.required_chunks, chunks), 4),
        "paths": sorted({e["path"] for e in pkg.evidence}),
    }


def main() -> dict:
    tasks = load_task_split("eval")
    with open("benchmarks/splits.json", encoding="utf-8") as f:
        eval_ids = set(json.load(f)["eval"])
    stray = [t.task_id for t in tasks if t.task_id not in eval_ids]
    if stray:
        raise SystemExit(f"refusing: non-eval tasks in bench run: {stray}")

    storage = tempfile.mkdtemp(prefix="aneh-convbench-")
    cfg = build_config({"index": {"storage_path": storage}})
    pipeline = Pipeline(cfg)
    try:
        rows = []
        for task in tasks:
            pipeline.register_repository(
                FIXTURE_REPO_PATHS[task.repository_id],
                task.repository_id, False)
            hints = bool(getattr(task, "use_explicit_path_hints", False))
            hint_paths = ([rc.get("path") for rc in task.required_chunks]
                          if hints else [])
            # Origin: one harness pack, the one-shot reference.
            origin = _measure(pipeline, task.repository_id, task,
                              task.task, hint_paths)
            # Multi: carried conversation with accumulating pins.
            t1 = _measure(pipeline, task.repository_id, task, task.task,
                          hint_paths)
            t2 = _measure(pipeline, task.repository_id, task,
                          task.task + T2_SUFFIX,
                          t1["paths"] or hint_paths)
            accumulated = sorted(set(t1["paths"]) | set(t2["paths"])
                                 or set(hint_paths))
            t3 = _measure(pipeline, task.repository_id, task,
                          task.task + T3_SUFFIX, accumulated)
            multi_total = t1["tokens"] + t2["tokens"] + t3["tokens"]
            rows.append({
                "task_id": task.task_id,
                "baseline_1x": origin["baseline"],
                "raw_3turn": origin["baseline"] * 3,
                "origin_1pack": origin["tokens"],
                "origin_recall": origin["recall"],
                "t1_tokens": t1["tokens"], "t1_recall": t1["recall"],
                "t2_tokens": t2["tokens"], "t2_recall": t2["recall"],
                "t3_tokens": t3["tokens"], "t3_recall": t3["recall"],
                "multi_total": multi_total,
                "t1_vs_origin_pct": round(
                    (t1["tokens"] - origin["tokens"]) / origin["tokens"]
                    * 100, 2) if origin["tokens"] else 0.0,
                "multi_vs_raw_pct": round(
                    (origin["baseline"] * 3 - multi_total)
                    / (origin["baseline"] * 3) * 100, 2)
                if origin["baseline"] else 0.0,
                "overhead_vs_origin": round(multi_total / origin["tokens"], 2)
                if origin["tokens"] else 0.0,
            })
        tot_raw = sum(r["raw_3turn"] for r in rows)
        tot_origin = sum(r["origin_1pack"] for r in rows)
        tot_multi = sum(r["multi_total"] for r in rows)
        min_rec = min(r[k] for r in rows for k in
                      ("origin_recall", "t1_recall", "t2_recall", "t3_recall"))
        med = lambda k: round(statistics.median([r[k] for r in rows]), 2)
        ok = min_rec >= 1.0 and tot_multi < tot_raw
        report = {
            "split": "eval", "n_tasks": len(tasks),
            "turns": ["first slice (task as-is)", "implement (T1 pins)",
                      "verify (accumulated pins)"],
            "totals": {
                "raw_3turn_tokens": tot_raw,
                "origin_1pack_tokens": tot_origin,
                "multi_3turn_tokens": tot_multi,
                "saved_multi_vs_raw": tot_raw - tot_multi,
                "saved_multi_vs_raw_pct": round(
                    (tot_raw - tot_multi) / tot_raw * 100, 2),
                "saved_origin_vs_raw1x": (sum(r["baseline_1x"] for r in rows)
                                          - tot_origin),
            },
            "medians_per_task": {
                "baseline_1x": med("baseline_1x"),
                "origin_1pack": med("origin_1pack"),
                "multi_total": med("multi_total"),
                "overhead_vs_origin": med("overhead_vs_origin"),
            },
            "min_recall_all_turns": min_rec,
            "verdict": ("carried conversation saves vs raw doing the same "
                        "turns, recall held on every turn"
                        if ok else "REGRESSION — see rows"),
            "notes": [
                "Raw = full context re-sent per turn (what no-harness pays "
                "for the same 3-turn conversation); origin = today's "
                "one-shot pack; multi = 3 carried packs summed.",
                "Pins accumulate caller-side (all T1 evidence paths -> T2, "
                "all T1+T2 -> T3) through the public --explicit-path "
                "mechanism. Full-evidence carry (not mandatory-only): pins "
                "protect only what was mandatory before, so mandatory-only "
                "carry sheds files when the focus shifts.",
                "T1 is the first slice (original task text, packed once — "
                "the t1_vs_origin_pct column proves it tracks the origin "
                "pack); T2/T3 are the conversation on top.",
                "Boundary (what this bench is not): no model reads these "
                "packs, follow-ups are fixed strings not agent reactions, "
                "nothing is billed, no task is completed. Full end-to-end "
                "needs the live loop — the half this harness feeds but "
                "never runs.",
            ],
            "tasks": rows,
        }
        with open("benchmarks/reports/conversation-bench-eval.json", "w",
                   encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        lines = ["# Conversation bench (eval split)",
                 "",
                 f"tasks: {len(tasks)} | verdict: {report['verdict']}",
                 "",
                 "| setup | total tokens |",
                 "|---|---|",
                 f"| 1. raw (full context x3 turns) | {tot_raw} |",
                 f"| 2. origin (one pack) | {tot_origin} |",
                 f"| 3. multi (3 carried packs) | {tot_multi} |",
                 "",
                 f"multi vs raw: saved {tot_raw - tot_multi} tokens "
                 f"({report['totals']['saved_multi_vs_raw_pct']}%)",
                 f"min recall all turns: {min_rec}",
                 ""]
        with open("benchmarks/reports/conversation-bench-eval.md", "w",
                   encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"raw={tot_raw} origin={tot_origin} multi={tot_multi} "
              f"saved_vs_raw={tot_raw - tot_multi} min_recall={min_rec}")
        print(f"verdict: {report['verdict']}")
        return report
    finally:
        pipeline.close()
        shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()
