"""Token-saving measurement with public functions only (frozen eval split).

Per task: full-context baseline tokens, one harness pack (plain select —
the shipped default, no stages/profiles), required-evidence recall, and the
identical pack rendered three ways (evidence JSON, markdown, compact).
Writes benchmarks/reports/token-savings.json — the data behind
docs/token-savings.png (scripts/plot_token_savings.py).

Portable: stdlib + the ane_context_harness package only. Anyone can
reproduce: PYTHONPATH=src python3 scripts/measure_token_savings.py
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
from ane_context_harness.providers.compact import render_compact
from ane_context_harness.providers.markdown import render_markdown


def main() -> dict:
    tasks = load_task_split("eval")
    with open("benchmarks/splits.json", encoding="utf-8") as f:
        eval_ids = set(json.load(f)["eval"])
    stray = [t.task_id for t in tasks if t.task_id not in eval_ids]
    if stray:
        raise SystemExit(f"refusing: non-eval tasks: {stray}")

    storage = tempfile.mkdtemp(prefix="aneh-toksave-")
    pipeline = Pipeline(build_config({"index": {"storage_path": storage}}))
    try:
        rows = []
        for task in tasks:
            pipeline.register_repository(
                FIXTURE_REPO_PATHS[task.repository_id],
                task.repository_id, False)
            chunks = pipeline._storage_for(task.repository_id).load_chunks()
            base = baseline_full_context_tokens(chunks)
            pkg = pipeline.select_context(schemas.SelectRequest(
                repository_id=task.repository_id, task=task.task,
                token_budget=task.token_budget, explicit_paths=[]))
            recall = round(required_chunks_covered(
                pkg.evidence, task.required_chunks, chunks), 4)
            sent = sum(tokens_mod.count(e["content"]) for e in pkg.evidence)
            fmt = {
                "json": tokens_mod.count(json.dumps(
                    pkg.evidence, sort_keys=True, default=str)),
                "markdown": tokens_mod.count(render_markdown(pkg)),
                "compact": tokens_mod.count(render_compact(pkg)),
            }
            rows.append({
                "task_id": task.task_id,
                "baseline": base, "sent": sent,
                "reduction_pct": round((base - sent) / base * 100, 2)
                if base else 0.0,
                "recall": recall, "formats": fmt,
            })
        med = lambda k: round(statistics.median([r[k] for r in rows]), 1)
        report = {
            "label": "token-savings",
            "split": "eval", "n_tasks": len(tasks),
            "ruler": "pinned regex-heuristic counter (TOKEN_ESTIMATOR_VERSION=2)",
            "medians": {
                "baseline": med("baseline"), "sent": med("sent"),
                "reduction_pct": med("reduction_pct"),
            },
            "min_recall": min(r["recall"] for r in rows),
            "median_format_tokens": {
                k: round(statistics.median([r["formats"][k] for r in rows]), 1)
                for k in ("json", "markdown", "compact")
            },
            "tasks": rows,
        }
        with open("benchmarks/reports/token-savings.json", "w",
                   encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"n={len(tasks)} med_sent={report['medians']['sent']} "
              f"med_red={report['medians']['reduction_pct']}% "
              f"min_recall={report['min_recall']} "
              f"formats={report['median_format_tokens']}")
        return report
    finally:
        pipeline.close()
        shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()
