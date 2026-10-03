"""Phase 0 measurement scaffold: benchmark task format + runners.

Benchmark task JSON (labelled):
{
  "task_id": "py-discount-001",
  "task": "Fix the incorrect discount calculation and update its tests",
  "repository_id": "synthetic_py_project",
  "task_language": "python",
  "token_budget": 12000,
  "required_chunks": [ {"path":..., "symbol":..., "lines":...}, ... ],
  "helpful_chunks": [...],
  "irrelevant_chunks": [...],
  "sensitive_fixtures": [...],
  "tags": ["bug-fix","python"]
}
"""
from __future__ import annotations

import json
import platform as _pf
from dataclasses import dataclass, field
from pathlib import Path

from . import tokens as tokens_mod
from .platform.discovery import discover
from .telemetry.metrics import Timer, peak_rss_mb

# Bumped when the task JSON shape changes incompatibly. Recorded in release
# evidence and validated by load_benchmark_tasks/validate_task.
BENCHMARK_SCHEMA_VERSION = "2"

# Fields every task must carry (schema v2): provenance + difficulty metadata so
# reports can say exactly which set a number came from.
REQUIRED_TASK_FIELDS = ("task_id", "task", "repository_id", "difficulty",
                        "category", "token_budget", "required_chunks",
                        "challenge", "expected_retrieval_behavior",
                        "expected_final_package", "ground_truth_provenance")
DIFFICULTIES = ("small", "typical", "difficult")


class TaskSchemaError(ValueError):
    """A benchmark task failed schema validation."""

# Local fixture repositories referenced by repository_id in benchmark tasks.
# Paths are relative to the repo root (evaluation/calibration run from there).
FIXTURE_REPO_PATHS = {
    "synthetic_py_project": "tests/fixtures/synthetic_py_project",
    "synthetic_ts_project": "tests/fixtures/synthetic_ts_project",
    "synthetic_hard_project": "tests/fixtures/synthetic_hard_project",
}

# Default never-read patterns (mirrors config.DEFAULT_CONFIG.privacy.never_read;
# files matching these are not indexed, so they do not count toward repository
# totals). Kept in lockstep with config.py — never-read is a privacy boundary,
# not a benchmark knob.
DEFAULT_NEVER_READ = ["**/.git/**", "**/.env*", "**/.EnvLocal",
                      "**/.aws/**", "**/.ssh/**", "**/*.pem"]


def estimate_repo_total_tokens(repo_path: str | Path,
                               never_read: list | None = None) -> int:
    """Estimated tokens of the ELIGIBLE repository (as the indexer sees it)."""
    from .indexing.repository import scan_repository
    plan = scan_repository(repo_path, 10_000_000,
                           DEFAULT_NEVER_READ if never_read is None else never_read)
    return sum(tokens_mod.estimate(fi.content) for fi in plan.files)


def estimate_repo_totals(repo_paths: dict | None = None,
                         never_read: list | None = None) -> dict:
    """repository_id -> eligible token total, for whole-repo-fits validation."""
    repo_paths = repo_paths or FIXTURE_REPO_PATHS
    return {rid: estimate_repo_total_tokens(p, never_read)
            for rid, p in repo_paths.items()}


# ---- dev/eval split (write-once) -------------------------------------------
# Task-level, stratified by difficulty (~40% dev / ~60% eval). Budget tuning is
# allowed on dev only; eval tasks must never be moved after freezing.
SPLIT_FILE = "benchmarks/splits.json"
SPLIT_SCHEMA_VERSION = "split-1"
SPLIT_SEED = 20261002
DEV_FRACTION = 0.4

# Legacy assignment intent (frozen): these must not move regardless of the
# seeded draw.
PINNED_ASSIGNMENTS = {
    "py-discount-001": "eval",
    "py-discount-full-002": "dev",   # compact-budget tuning case
    "ts-discount-001": "eval",
}


def derive_split(tasks: list, seed: int = SPLIT_SEED,
                 pinned: dict | None = None) -> dict:
    """Deterministic stratified split: ~40/60 dev/eval within each difficulty.

    Returns {"dev": [task_id...], "eval": [task_id...], ...meta}. Pinned
    assignments are honoured first; remaining slots are filled from a
    per-difficulty seeded shuffle so adding a task only reshuffles its own
    difficulty band.
    """
    import random
    pinned = dict(PINNED_ASSIGNMENTS if pinned is None else pinned)
    by_diff: dict = {}
    for t in tasks:
        tid = t.task_id if hasattr(t, "task_id") else t["task_id"]
        diff = (t.difficulty if hasattr(t, "difficulty") else t.get("difficulty",
                                                                    "typical"))
        by_diff.setdefault(diff, []).append(tid)
    dev, eval_ = [], []
    for diff in sorted(by_diff):
        ids = sorted(by_diff[diff])
        band_pinned = {k: v for k, v in pinned.items() if k in ids}
        for tid, side in band_pinned.items():
            (dev if side == "dev" else eval_).append(tid)
        free = [t for t in ids if t not in band_pinned]
        rng = random.Random(f"{seed}:{diff}")
        rng.shuffle(free)
        n_dev = round(len(ids) * DEV_FRACTION) - sum(
            1 for v in band_pinned.values() if v == "dev")
        n_dev = max(0, min(len(free), n_dev))
        dev.extend(free[:n_dev])
        eval_.extend(free[n_dev:])
    split = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": seed,
        "method": ("task-level, stratified by difficulty, "
                   f"{DEV_FRACTION:.0%} dev / remainder eval, seeded shuffle "
                   "within difficulty band"),
        "pinned": pinned,
        "task_set_hash": task_set_hash(tasks),
        "counts": {"dev": len(dev), "eval": len(eval_),
                   "total": len(dev) + len(eval_)},
        "dev": sorted(dev),
        "eval": sorted(eval_),
    }
    return split


def load_task_split(split: str = "eval", tasks_dir: str | Path = "benchmarks/tasks",
                    split_file: str | Path = SPLIT_FILE,
                    validate: bool = True) -> list:
    """Load one side of the frozen split (verifies the task-set hash).

    Raises ValueError when the frozen split is missing, names an unknown side,
    or no longer matches the task set (write-once: regenerate deliberately).
    """
    if split not in ("dev", "eval"):
        raise ValueError(f"split must be 'dev' or 'eval', got {split!r}")
    path = Path(split_file)
    if not path.exists():
        raise ValueError(
            f"split file {path} not found — freeze it with derive_split() "
            "before running split-scoped gates")
    with open(path, "r", encoding="utf-8") as f:
        frozen = json.load(f)
    tasks = load_benchmark_tasks(tasks_dir, validate=validate)
    if frozen.get("task_set_hash") != task_set_hash(tasks):
        raise ValueError(
            "frozen split does not match the current task set — the split is "
            "write-once; do not edit tasks without re-deriving it on purpose")
    wanted = set(frozen.get(split, []))
    known = {t.task_id for t in tasks}
    unknown = wanted - known
    if unknown:
        raise ValueError(f"split names unknown tasks: {sorted(unknown)}")
    return [t for t in tasks if t.task_id in wanted]


@dataclass
class BenchmarkTask:
    task_id: str
    task: str
    repository_id: str
    task_language: str
    token_budget: int
    required_chunks: list
    helpful_chunks: list = field(default_factory=list)
    irrelevant_chunks: list = field(default_factory=list)
    sensitive_fixtures: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    difficulty: str = "typical"
    category: str = "unspecified"
    distractor_chunks: list = field(default_factory=list)
    challenge: str = ""
    expected_retrieval_behavior: str = ""
    expected_final_package: str = ""
    ground_truth_provenance: str = ""
    use_explicit_path_hints: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "BenchmarkTask":
        return cls(
            task_id=d["task_id"],
            task=d["task"],
            repository_id=d["repository_id"],
            task_language=d.get("task_language", ""),
            token_budget=d.get("token_budget", 12000),
            required_chunks=d.get("required_chunks", []),
            helpful_chunks=d.get("helpful_chunks", []),
            irrelevant_chunks=d.get("irrelevant_chunks", []),
            sensitive_fixtures=d.get("sensitive_fixtures", []),
            tags=d.get("tags", []),
            difficulty=d.get("difficulty", "typical"),
            category=d.get("category", "unspecified"),
            distractor_chunks=d.get("distractor_chunks", []),
            challenge=d.get("challenge", ""),
            expected_retrieval_behavior=d.get("expected_retrieval_behavior", ""),
            expected_final_package=d.get("expected_final_package", ""),
            ground_truth_provenance=d.get("ground_truth_provenance", ""),
            use_explicit_path_hints=bool(d.get("use_explicit_path_hints", False)),
        )


def load_benchmark_tasks(tasks_dir: str | Path, repo_total_tokens: dict | None = None,
                         validate: bool = True) -> list:
    tasks = []
    for p in sorted(Path(tasks_dir).glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if validate:
            validate_task(d, repo_total_tokens=repo_total_tokens)
        tasks.append(BenchmarkTask.from_dict(d))
    return tasks


def validate_task(d: dict, repo_total_tokens: dict | None = None) -> None:
    """Validate one raw task dict against schema v2.

    Raises TaskSchemaError. When ``repo_total_tokens`` maps repository_id to
    the repository's total estimated tokens, also rejects tasks whose budget
    would let the ENTIRE eligible repository fit — such a task passes recall
    trivially (no selection pressure) and measures nothing.
    """
    if not isinstance(d, dict):
        raise TaskSchemaError("task must be a JSON object")
    missing = [f for f in REQUIRED_TASK_FIELDS if not d.get(f)]
    if missing:
        raise TaskSchemaError(f"{d.get('task_id', '?')}: missing required fields {missing}")
    if d.get("difficulty") not in DIFFICULTIES:
        raise TaskSchemaError(
            f"{d['task_id']}: difficulty must be one of {DIFFICULTIES}, "
            f"got {d.get('difficulty')!r}")
    if not isinstance(d.get("token_budget"), int) or d["token_budget"] <= 0:
        raise TaskSchemaError(f"{d['task_id']}: token_budget must be a positive int")
    req = d.get("required_chunks")
    if not isinstance(req, list) or not req:
        raise TaskSchemaError(f"{d['task_id']}: required_chunks must be a non-empty list")
    for rc in req:
        if not isinstance(rc, dict) or not rc.get("path"):
            raise TaskSchemaError(
                f"{d['task_id']}: each required chunk needs a path")
    if not isinstance(d.get("ground_truth_provenance"), str):
        raise TaskSchemaError(f"{d['task_id']}: ground_truth_provenance must be a string")
    if repo_total_tokens is not None:
        total = repo_total_tokens.get(d["repository_id"])
        if total is None:
            raise TaskSchemaError(
                f"{d['task_id']}: unknown repository_id {d['repository_id']!r}")
        if d["token_budget"] >= total:
            raise TaskSchemaError(
                f"{d['task_id']}: token_budget {d['token_budget']} >= total repo tokens "
                f"{total} — the entire repository fits, so the task cannot fail "
                f"selection; shrink the budget")


def task_set_hash(tasks: list) -> str:
    """Stable hash over the full task set (order-independent)."""
    import hashlib
    items = sorted(
        (t.task_id if hasattr(t, "task_id") else t.get("task_id"),
         json.dumps(t if isinstance(t, dict) else t.__dict__,
                    sort_keys=True, default=str))
        for t in tasks)
    blob = json.dumps(items, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _chunk_matches(c, req: dict) -> bool:
    if c.path != req.get("path"):
        return False
    lines = req.get("lines")
    if lines and not (c.start_line <= lines[0] and c.end_line >= lines[1]):
        return False
    # Symbol scope only applies to symbol-scoped chunks (file-level chunks are
    # decided by path/lines) — mirrors metrics._matches.
    symbol = req.get("symbol")
    if symbol and c.symbol and c.symbol != symbol:
        return False
    return True


def required_chunks_covered(evidence: list, labels: list, chunks: list) -> float:
    """Required-evidence recall: fraction of required labels retained.

    A label counts as covered when a SELECTED chunk of that path matches it:
    path equality plus, when the label carries symbol/line scope and the
    selected chunk is symbol-scoped, symbol/line agreement. File-level chunks
    (symbol None) satisfy any symbol scope inside their path/lines. Duplicated
    chunks cannot inflate the result (labels are counted once each).
    """
    if not labels:
        return 1.0
    covered = 0
    for req in labels:
        path = req.get("path")
        sel_for_path = [e for e in evidence if e["path"] == path]
        if not sel_for_path:
            continue
        chunks_for_path = [c for c in chunks if c.path == path]
        sel_starts = {e["start_line"] for e in sel_for_path}
        for c in chunks_for_path:
            if c.start_line in sel_starts and _chunk_matches(c, req):
                covered += 1
                break
    return covered / len(labels)


def baseline_full_context_tokens(chunks: list) -> int:
    return sum(c.estimated_tokens for c in chunks)


@dataclass
class BenchmarkResult:
    task_id: str
    candidate_tokens: int
    selected_tokens: int
    tokens_removed: int
    reduction_percent: float
    recall: float
    total_latency_ms: float
    stage_ms: dict
    peak_rss_mb: float | None
    measured_on: dict


@dataclass
class BenchmarkReport:
    label: str
    platform: dict
    items: list = field(default_factory=list)


def run_benchmark(tasks: list, pipeline, repo_paths: dict) -> BenchmarkReport:
    """Run labelled tasks through a Phase 1 Pipeline (repos indexed on demand)."""
    report = BenchmarkReport(label="phase1-deterministic", platform={
        "platform": _pf.platform(),
        "python_version": _pf.python_version(),
        "machine": _pf.machine(),
        "discovery": discover(),
    })
    for task in tasks:
        pipeline.register_repository(repo_paths[task.repository_id], task.repository_id, False)
        from . import schemas
        hints = bool(getattr(task, "use_explicit_path_hints", False))
        req = schemas.SelectRequest(
            repository_id=task.repository_id,
            task=task.task,
            token_budget=task.token_budget,
            explicit_paths=[rc.get("path") for rc in task.required_chunks] if hints else [],
        )
        storage = pipeline._storage_for(task.repository_id)
        with Timer("total") as t_total:
            pkg = pipeline.select_context(req)
            if not pkg.markdown:
                from .providers.markdown import render_markdown
                pkg.markdown = render_markdown(pkg)
        chunks = storage.load_chunks()
        cand_tokens = sum(c.estimated_tokens for c in chunks)
        sel_tokens = sum(tokens_mod.count(e["content"]) for e in pkg.evidence)
        reduction = ((cand_tokens - sel_tokens) / cand_tokens * 100.0) if cand_tokens else 0.0
        recall = required_chunks_covered(pkg.evidence, task.required_chunks, chunks) if task.required_chunks else 1.0
        stage_ms = pkg.metrics.get("stage_ms", {}) if isinstance(pkg.metrics, dict) else {}
        report.items.append(BenchmarkResult(
            task_id=task.task_id,
            candidate_tokens=cand_tokens,
            selected_tokens=sel_tokens,
            tokens_removed=cand_tokens - sel_tokens,
            reduction_percent=round(reduction, 2),
            recall=round(recall, 4),
            total_latency_ms=round(t_total.elapsed_ms, 2),
            stage_ms=stage_ms,
            peak_rss_mb=peak_rss_mb(),
            measured_on={"hardware": report.platform["discovery"]},
        ))
    return report


def report_summary(report: BenchmarkReport) -> dict:
    if not report.items:
        return {"count": 0}
    import statistics as st
    red = [i.reduction_percent for i in report.items]
    rec = [i.recall for i in report.items]
    lat = [i.total_latency_ms for i in report.items]
    rss = [i.peak_rss_mb for i in report.items if i.peak_rss_mb is not None]
    lat_sorted = sorted(lat)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95) - 1)] if lat_sorted else 0
    return {
        "label": report.label,
        "n": len(report.items),
        "median_reduction_percent": round(st.median(red), 2),
        "mean_reduction_percent": round(st.fmean(red), 2),
        "min_reduction_percent": round(min(red), 2),
        "median_recall": round(st.median(rec), 4),
        "min_recall": round(min(rec), 4),
        "p50_latency_ms": round(st.median(lat), 2),
        "p95_latency_ms": round(p95, 2),
        "peak_rss_mb_min": min(rss) if rss else None,
        "peak_rss_mb_max": max(rss) if rss else None,
        "measured_on_platform": report.platform,
    }
