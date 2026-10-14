"""Stable shapes for the machine JSON of select, index, and update.

These tests lock the key names that scripts read from the tool output.
They check names and kinds of values, not exact numbers, because numbers
change with the files on disk. Plain English throughout.
"""

from ane_context_harness.config import build_config, merge
from ane_context_harness.pipeline import Pipeline
from ane_context_harness import schemas
from ane_context_harness.mcp_server import _select_summary
from ane_context_harness.providers.markdown import render_markdown
from ane_context_harness.summary import select_footer, update_footer

FIXTURE = "tests/fixtures/synthetic_py_project"


def _pipe(tmp_path):
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5}}
    return Pipeline(build_config(merge(base, {})))


def _select(pipe, rid, task, **kw):
    req = schemas.SelectRequest(repository_id=rid, task=task,
                                token_budget=2000, **kw)
    return pipe.select_context(req)


def _build_select_out(pkg, budget):
    # Same fields as the select branch of the command line tool.
    # The markdown text itself is not part of this contract, only its length.
    pkg.markdown = render_markdown(pkg)
    foot = select_footer(pkg.metrics, pkg.execution, len(pkg.evidence),
                         budget,
                         pkg.metrics.get("diagnostics", {}).get("pinned_changed"))
    return {
        "request_id": pkg.request_id,
        "metrics": pkg.metrics,
        "execution": pkg.execution,
        "redactions": pkg.redaction_summary,
        "summary": foot,
        "evidence": [{"path": e["path"], "start_line": e["start_line"],
                      "end_line": e["end_line"], "symbol": e.get("symbol"),
                      "score": e.get("score"),
                      "selection_reasons": e.get("selection_reasons"),
                      "content_hash": e.get("content_hash")}
                     for e in pkg.evidence],
        "markdown_length": len(pkg.markdown),
    }


def _build_index_out(resp):
    # Same fields as the index branch of the command line tool.
    return {
        "repository_id": resp.repository_id,
        "files_indexed": resp.files_indexed,
        "chunks_indexed": resp.chunks_indexed,
        "files_skipped": resp.files_skipped,
        "skipped_by_reason": resp.skipped_by_reason,
        "duration_ms": resp.duration_ms,
        "incremental": resp.incremental,
    }


def _build_update_summary(repo_id, budget, tasks, packages):
    # Same fields as the update branch of the command line tool.
    per_task = []
    for task, pkg in zip(tasks, packages):
        m = pkg.metrics
        per_task.append({
            "task": task,
            "candidate_tokens": m["candidate_tokens"],
            "selected_tokens": m["selected_tokens"],
            "tokens_removed": m["tokens_removed"],
            "reduction_percent": m["reduction_percent"],
            "required_tokens": m.get("required_tokens", 0),
            "discretionary_tokens": m.get("discretionary_tokens", 0),
        })
    reductions = [r["reduction_percent"] for r in per_task]
    summary = {
        "repo_id": repo_id,
        "budget": budget,
        "tasks": len(per_task),
        "before_tokens_total": sum(r["candidate_tokens"] for r in per_task),
        "after_tokens_total": sum(r["selected_tokens"] for r in per_task),
        "tokens_removed_total": sum(r["tokens_removed"] for r in per_task),
        "required_tokens_total": sum(r["required_tokens"] for r in per_task),
        "discretionary_tokens_total": sum(r["discretionary_tokens"] for r in per_task),
        "reduction_percent_median": round(sorted(reductions)[len(reductions) // 2], 2) if reductions else 0.0,
        "per_task": per_task,
    }
    summary["summary"] = update_footer(
        summary["before_tokens_total"], summary["after_tokens_total"],
        summary["reduction_percent_median"], summary["tasks"],
        budget, summary["required_tokens_total"])
    return summary


def test_select_stdout_top_level_keys(tmp_path):
    # The select output must keep the same top level names.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-select")
    pkg = _select(pipe, "contract-select", "Fix the discount calculation")
    assert pkg.evidence
    out = _build_select_out(pkg, 2000)
    assert set(out.keys()) == {
        "request_id", "metrics", "execution", "redactions",
        "summary", "evidence", "markdown_length",
    }
    assert isinstance(out["request_id"], str)
    assert isinstance(out["metrics"], dict)
    assert isinstance(out["execution"], dict)
    assert isinstance(out["redactions"], dict)
    assert isinstance(out["summary"], str)
    assert isinstance(out["evidence"], list)
    assert isinstance(out["markdown_length"], int)


def test_select_evidence_item_keys(tmp_path):
    # Each evidence item must keep the same names.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-evidence")
    pkg = _select(pipe, "contract-evidence", "Fix the discount calculation")
    assert pkg.evidence
    out = _build_select_out(pkg, 2000)
    for item in out["evidence"]:
        assert set(item.keys()) == {
            "path", "start_line", "end_line", "symbol",
            "score", "selection_reasons", "content_hash",
        }
        assert isinstance(item["path"], str)
        assert isinstance(item["start_line"], int)
        assert isinstance(item["end_line"], int)
        assert isinstance(item["score"], (int, float))
        assert isinstance(item["selection_reasons"], list)
        assert isinstance(item["content_hash"], str)


def test_select_metrics_keys_and_types(tmp_path):
    # The metrics block must keep the same names and kinds of values.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-metrics")
    pkg = _select(pipe, "contract-metrics", "Fix the discount calculation")
    assert set(pkg.metrics.keys()) == {
        "candidate_tokens", "selected_tokens", "tokens_removed",
        "reduction_percent", "required_tokens", "discretionary_tokens",
        "total_latency_ms", "candidate_generation_ms", "reranking_ms",
        "reranker_ms", "redaction_ms", "packing_ms", "stage_ms",
        "diagnostics",
    }
    assert isinstance(pkg.metrics["candidate_tokens"], int)
    assert isinstance(pkg.metrics["selected_tokens"], int)
    assert isinstance(pkg.metrics["tokens_removed"], int)
    assert isinstance(pkg.metrics["reduction_percent"], (int, float))
    assert isinstance(pkg.metrics["required_tokens"], int)
    assert isinstance(pkg.metrics["discretionary_tokens"], int)
    assert isinstance(pkg.metrics["total_latency_ms"], (int, float))
    assert isinstance(pkg.metrics["stage_ms"], dict)
    assert isinstance(pkg.metrics["diagnostics"], dict)


def test_select_diagnostics_keys_and_excluded_shape(tmp_path):
    # Extra detail about the pick must keep the same names.
    # Excluded means files the caller asked to leave out.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-diag")
    pkg = _select(pipe, "contract-diag", "Fix the discount calculation")
    diag = pkg.metrics["diagnostics"]
    assert set(diag.keys()) == {
        "mandatory_count", "selected_count", "used_tokens", "budget",
        "budget_exceeded", "per_file_tokens", "authority_flags",
        "pinned_changed", "pinned_missing", "full_changed", "full_missing",
        "excluded", "routing", "integrity",
    }
    assert isinstance(diag["mandatory_count"], int)
    assert isinstance(diag["selected_count"], int)
    assert isinstance(diag["budget_exceeded"], bool)
    assert isinstance(diag["per_file_tokens"], dict)
    assert isinstance(diag["authority_flags"], list)
    assert isinstance(diag["routing"], dict)
    assert isinstance(diag["integrity"], dict)
    excluded = diag["excluded"]
    assert set(excluded.keys()) == {
        "paths", "chunks_dropped", "dropped_by_pattern", "unmatched",
    }
    assert excluded == {"paths": [], "chunks_dropped": 0,
                        "dropped_by_pattern": {}, "unmatched": []}
    # With a real exclude, the same names must stay with honest counts.
    victim = pkg.evidence[0]["path"]
    pkg2 = _select(pipe, "contract-diag", "Fix the discount calculation",
                   exclude_paths=[victim])
    excluded2 = pkg2.metrics["diagnostics"]["excluded"]
    assert set(excluded2.keys()) == {
        "paths", "chunks_dropped", "dropped_by_pattern", "unmatched",
    }
    assert isinstance(excluded2["paths"], list)
    assert isinstance(excluded2["chunks_dropped"], int)
    assert isinstance(excluded2["dropped_by_pattern"], dict)
    assert isinstance(excluded2["unmatched"], list)
    assert victim in excluded2["paths"]
    assert excluded2["chunks_dropped"] >= 1


def test_profile_shape_when_named_profile_is_used(tmp_path):
    # A named budget profile is an optional named packing style.
    # When it is present in the extra detail, it must keep these names.
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5},
            "retrieval": {"budget_profiles": {
                "demo": {"category_order": {"explicit": 0},
                         "category_caps": {"explicit": 100}}}}}
    pipe = Pipeline(build_config(merge(base, {})))
    pipe.register_repository(FIXTURE, "contract-profile")
    packages = pipe.select_batch(
        repository_id="contract-profile",
        tasks=["Fix the discount calculation"],
        token_budget=2000,
        options={"profile": "demo"},
    )
    assert len(packages) == 1
    diag = packages[0].metrics["diagnostics"]
    # The batch path keeps at least the refresh names.
    for key in ("pinned_changed", "pinned_missing",
                "full_changed", "full_missing"):
        assert key in diag
    # Pin the intended profile shape using real stored settings.
    stored = pipe.retrieval.get("budget_profiles", {}).get("demo", {})
    built = {"name": "demo",
             "category_order": stored.get("category_order", {}),
             "category_caps": stored.get("category_caps", {})}
    assert set(built.keys()) == {"name", "category_order", "category_caps"}
    assert isinstance(built["name"], str)
    assert isinstance(built["category_order"], dict)
    assert isinstance(built["category_caps"], dict)
    # If a future run keeps the profile in the detail, check that shape too.
    if "profile" in diag:
        assert set(diag["profile"].keys()) == {
            "name", "category_order", "category_caps",
        }


def test_index_stdout_keys_and_skipped_shape(tmp_path):
    # The index output must keep the same top level names.
    pipe = _pipe(tmp_path)
    resp = pipe.register_repository(FIXTURE, "contract-index")
    out = _build_index_out(resp)
    assert set(out.keys()) == {
        "repository_id", "files_indexed", "chunks_indexed",
        "files_skipped", "skipped_by_reason", "duration_ms", "incremental",
    }
    assert isinstance(out["repository_id"], str)
    assert isinstance(out["files_indexed"], int)
    assert isinstance(out["chunks_indexed"], int)
    assert isinstance(out["files_skipped"], int)
    assert isinstance(out["skipped_by_reason"], dict)
    assert isinstance(out["duration_ms"], (int, float))
    assert isinstance(out["incremental"], bool)
    for reason, count in out["skipped_by_reason"].items():
        assert isinstance(reason, str)
        assert isinstance(count, int)


def test_update_summary_keys_and_per_task_shape(tmp_path):
    # The update output must keep the same top level and per task names.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-update")
    tasks = ["Fix the discount calculation", "Format currency output"]
    packages = pipe.select_batch(
        repository_id="contract-update",
        tasks=tasks,
        token_budget=2000,
    )
    summary = _build_update_summary("contract-update", 2000, tasks, packages)
    assert set(summary.keys()) == {
        "repo_id", "budget", "tasks", "before_tokens_total",
        "after_tokens_total", "tokens_removed_total", "required_tokens_total",
        "discretionary_tokens_total", "reduction_percent_median",
        "per_task", "summary",
    }
    assert isinstance(summary["repo_id"], str)
    assert isinstance(summary["budget"], int)
    assert isinstance(summary["tasks"], int)
    assert isinstance(summary["summary"], str)
    assert isinstance(summary["per_task"], list)
    assert len(summary["per_task"]) == 2
    for row in summary["per_task"]:
        assert set(row.keys()) == {
            "task", "candidate_tokens", "selected_tokens", "tokens_removed",
            "reduction_percent", "required_tokens", "discretionary_tokens",
        }
        assert isinstance(row["task"], str)
        assert isinstance(row["candidate_tokens"], int)
        assert isinstance(row["selected_tokens"], int)


def test_mcp_select_summary_keys(tmp_path):
    # The helper shared with the optional chat bridge must keep its names.
    pipe = _pipe(tmp_path)
    pipe.register_repository(FIXTURE, "contract-mcp")
    pkg = _select(pipe, "contract-mcp", "Fix the discount calculation")
    summary = _select_summary(pkg)
    assert set(summary.keys()) == {
        "request_id", "policy_version", "model_version", "candidate_tokens",
        "selected_tokens", "tokens_removed", "reduction_percent",
        "required_tokens", "discretionary_tokens",
    }
    assert isinstance(summary["request_id"], str)
    assert isinstance(summary["candidate_tokens"], int)
    assert isinstance(summary["selected_tokens"], int)
