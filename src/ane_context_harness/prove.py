"""Prove-it one-liner: unlabelled reduction/latency proof on any repo.

Labelled recall gates need hand-labelled tasks (frozen split machinery);
without labels only reduction/latency are meaningful and recall is
reported as not_applicable — never claimed.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

CANNED_TASKS = (
    "Find discount calculation logic and rounding rules",
    "Where is inventory SKU lookup implemented?",
    "How are analytics totals computed?",
    "Show reporting stats output formatting",
    "Find configuration and settings handling",
)

# Per-repo-type canned tasks, drawn from the frozen benchmark task wording
# (benchmarks/tasks/*.json). run_prove picks one set by cheap extension
# census; --tasks-file always overrides. Generic stays the default when
# the census is inconclusive.
PY_TASKS = (
    "Fix the incorrect discount calculation and update its tests",
    "How does the inventory module generate the next SKU identifier?",
    "Fix outlier detection in the analytics module",
    "Fix grouping of report rows when a row is missing the grouping key",
    "Fix division-by-zero handling in the calculator and update its tests",
)
TS_TASKS = (
    "Fix the discount calculation bug in math.ts and verify its tests",
    "Fix inventory reconciliation so missing SKUs report zero on both sides",
    "Fix the moving-average window calculation",
    "Fix the summary statistics computation so empty inputs behave",
    "Fix summation of items and update its test",
)
DOC_TASKS = (
    "What is the authoritative rounding rule and the order in which charges are applied?",
    "What caps apply to the customer's price concession at checkout?",
    "Fix VAT application for customers in countries that already include VAT in prices",
    "Which storefront feature flags are configured for this environment?",
    "Where is the CartLine shape defined for cart lines?",
)


def detect_repo_kind(repo: str) -> str:
    """Cheap extension census: python | typescript | docs-mixed | generic.

    Stdlib only, capped scan, skips .git. Deterministic for a given tree.
    """
    root = Path(repo)
    py = ts = md = other = 0
    seen = 0
    for p in sorted(root.rglob("*")):
        if seen >= 500:
            break
        if not p.is_file():
            continue
        if ".git" in p.parts:
            continue
        seen += 1
        sfx = p.suffix.lower()
        if sfx == ".py":
            py += 1
        elif sfx in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"):
            ts += 1
        elif sfx in (".md", ".rst", ".txt"):
            md += 1
        else:
            other += 1
    code = py + ts
    if code == 0:
        return "generic"
    # docs-mixed = the pricing-rules archetype: TS-heavy with a real docs
    # layer (authoritative-rules-vs-stale-README tasks), or balanced
    # python+typescript with docs. Python+docs stays python (design notes).
    if py == 0 and ts >= 3 and md >= 3:
        return "docs-mixed"
    if py >= 2 and ts >= 2:
        if md >= 2 and max(py, ts) < 2 * min(py, ts):
            return "docs-mixed"
        return "python" if py > ts else "typescript"
    if py == 0 and ts >= 3 and md >= 3:
        return "docs-mixed"
    if py >= ts * 2 and py >= 2:
        return "python"
    if ts >= py * 2 and ts >= 2:
        return "typescript"
    if py and ts:
        return "docs-mixed" if md >= 3 else "generic"
    return "python" if py > ts else "typescript" if ts > py else "generic"


def canned_tasks_for(repo: str) -> list:
    kind = detect_repo_kind(repo)
    if kind == "python":
        return list(PY_TASKS)
    if kind == "typescript":
        return list(TS_TASKS)
    if kind == "docs-mixed":
        return list(DOC_TASKS)
    return list(CANNED_TASKS)

METRIC_NOTE = (
    "reduction_percent per task = (candidate - selected) / candidate * 100; "
    "median over tasks. Recall needs labelled required chunks and is "
    "not_applicable for unlabelled runs."
)


def load_tasks(tasks_file: str | None, repo: str | None = None) -> list:
    if not tasks_file:
        if repo is not None:
            return canned_tasks_for(repo)
        return list(CANNED_TASKS)
    tasks = []
    for line in Path(tasks_file).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                tasks.append(json.loads(line)["task"])
                continue
            except (json.JSONDecodeError, KeyError):
                pass
        tasks.append(line)
    if not tasks:
        return list(CANNED_TASKS)
    return tasks


def _median(xs: list) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return float(s[len(s) // 2])


def run_prove(repo: str, repo_id: str | None, budget: int = 2000,
              tasks_file: str | None = None, out: str | None = None,
              profile: str | None = None) -> dict:
    from .config import build_config
    from .pipeline import Pipeline, SERVICE_VERSION
    from . import schemas, tokens as tokens_mod
    from .summary import update_footer

    from .setup import default_repo_id

    root = str(Path(repo).resolve())
    rid = repo_id or default_repo_id(root)
    tasks = load_tasks(tasks_file, root)
    cfg = build_config()
    pipe = Pipeline(cfg)
    pipe.register_repository(root, rid)

    per_task = []
    for task in tasks:
        req = schemas.SelectRequest(
            repository_id=rid, task=task, token_budget=budget,
            options={"profile": profile} if profile else {})
        pkg = pipe.select_context(req)
        m = pkg.metrics
        per_task.append({
            "task": task,
            "candidate_tokens": m["candidate_tokens"],
            "selected_tokens": m["selected_tokens"],
            "tokens_removed": m["tokens_removed"],
            "reduction_percent": m["reduction_percent"],
            "latency_ms": m.get("total_latency_ms", 0.0),
        })
    reductions = [r["reduction_percent"] for r in per_task]
    latencies = [r["latency_ms"] for r in per_task]
    summary = {
        "repo_id": rid,
        "repo": root,
        "budget": budget,
        "profile": profile,
        "tasks": len(per_task),
        "task_kind": detect_repo_kind(root),
        "labelled": False,
        "recall": "not_applicable",
        "before_tokens_total": sum(r["candidate_tokens"] for r in per_task),
        "after_tokens_total": sum(r["selected_tokens"] for r in per_task),
        "tokens_removed_total": sum(r["tokens_removed"] for r in per_task),
        "reduction_percent_median": round(_median(reductions), 2),
        "latency_ms_p50": round(_median(latencies), 2),
        "per_task": per_task,
        "provenance": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "service_version": SERVICE_VERSION,
            "token_estimator": f"{tokens_mod.BACKEND} v{tokens_mod.TOKEN_ESTIMATOR_VERSION}",
        },
        "metric_note": METRIC_NOTE,
    }
    summary["summary"] = update_footer(
        summary["before_tokens_total"], summary["after_tokens_total"],
        summary["reduction_percent_median"], summary["tasks"], budget)
    if out:
        outdir = Path(out)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "prove.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        rows = "\n".join(
            f"| {r['task'][:48]} | {r['candidate_tokens']} | "
            f"{r['selected_tokens']} | {r['reduction_percent']} | "
            f"{r['latency_ms']} |" for r in per_task)
        (outdir / "prove.md").write_text(
            f"# Prove-it report\n\n{summary['summary']}\n\n"
            f"Recall: not_applicable (unlabelled run; {METRIC_NOTE})\n\n"
            f"| task | before | after | reduction % | latency ms |\n"
            f"|---|---|---|---|---|\n{rows}\n",
            encoding="utf-8")
        summary["out"] = str(outdir)
    return summary
