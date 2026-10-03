"""Optional MCP server adapter for ane-harness.

Exposes the same core functions as the CLI (select, update, evidence verify)
over the MCP protocol. This module is an *optional add-on* — the CLI/`ane-`
harness` entrypoint remains the primary interface and never depends on `mcp`.
Install with `pip install 'ane-context-harness[mcp]'`.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from . import schemas, tokens
from .config import build_config
from .evidence import verify_bundle as _verify_bundle
from .pipeline import Pipeline
from .summary import select_footer, update_footer
from . import usage as usage_log


def _select_summary(pkg: schemas.EvidencePackage) -> dict[str, Any]:
    m = pkg.metrics
    return {
        "request_id": pkg.request_id,
        "policy_version": pkg.policy_version,
        "model_version": pkg.model_version,
        "candidate_tokens": m["candidate_tokens"],
        "selected_tokens": m["selected_tokens"],
        "tokens_removed": m["tokens_removed"],
        "reduction_percent": m["reduction_percent"],
        "required_tokens": m.get("required_tokens", 0),
        "discretionary_tokens": m.get("discretionary_tokens", 0),
    }


def _select_human(pkg: schemas.EvidencePackage, budget: int) -> str:
    return select_footer(pkg.metrics, pkg.execution, len(pkg.evidence),
                         budget)


async def select_context_tool(repo_id: str, task: str, budget: int = 12000) -> str:
    """MCP tool: select context for a single task (Arm B deterministic)."""
    cfg = build_config()
    pipe = Pipeline(cfg)
    req = schemas.SelectRequest(repository_id=repo_id, task=task,
                                token_budget=budget, explicit_paths=[])
    pkg = pipe.select_context(req)
    out = _select_summary(pkg)
    out["summary"] = _select_human(pkg, budget)
    if usage_log.log_enabled():
        usage_log.record("select", pkg.metrics["candidate_tokens"],
                         pkg.metrics["selected_tokens"],
                         pkg.metrics.get("total_latency_ms"))
    return json.dumps(out, indent=2)


async def update_tool(repo_id: str, budget: int, tasks: list[str]) -> str:
    """MCP tool: batch-select context for many tasks; report token savings.

    Mirrors `ane-harness update` — local only, no network/redaction guarantee.
    """
    cfg = build_config()
    pipe = Pipeline(cfg)
    per_task: list[dict[str, Any]] = []
    for task in tasks:
        req = schemas.SelectRequest(repository_id=repo_id, task=task,
                                    token_budget=budget, explicit_paths=[])
        pkg = pipe.select_context(req)
        per_task.append({
            "task": task,
            **_select_summary(pkg),
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
        "reduction_percent_median": (
            round(sorted(reductions)[len(reductions) // 2], 2)
            if reductions else 0.0),
        "per_task": per_task,
    }
    summary["summary"] = update_footer(
        summary["before_tokens_total"], summary["after_tokens_total"],
        summary["reduction_percent_median"], summary["tasks"], budget,
        summary["required_tokens_total"])
    if usage_log.log_enabled():
        usage_log.record("update", summary["before_tokens_total"],
                         summary["after_tokens_total"],
                         tasks=summary["tasks"])
    return json.dumps(summary, indent=2)


async def verify_tool(bundle_dir: str) -> str:
    """MCP tool: verify a release-evidence bundle's checksums and metadata."""
    return json.dumps(_verify_bundle(bundle_dir), indent=2)


def count_tokens_tool(text: str) -> int:
    """MCP tool: deterministic token estimate for a string (pinned backend)."""
    return tokens.count(text)


def build_server() -> Any:
    """Build a FastMCP server with ane-harness tools registered.

    Returns the server instance; caller invokes `.run()` with transport args.
    """
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("ane-harness")

    @server.tool()
    async def select(repo_id: str, task: str, budget: int = 12000) -> str:
        """Select context for a single task (Arm B deterministic)."""
        return await select_context_tool(repo_id, task, budget)

    @server.tool()
    async def update(repo_id: str, budget: int, tasks: list[str]) -> str:
        """Batch-select context for many tasks; report token savings.

        Local only, no network. Mirrors `ane-harness update`."""
        return await update_tool(repo_id, budget, tasks)

    @server.tool()
    async def verify(bundle_dir: str) -> str:
        """Verify a release-evidence bundle's checksums + metadata."""
        return await verify_tool(bundle_dir)

    @server.tool()
    def tokens(text: str) -> int:
        """Deterministic token estimate for a string (pinned regex-heuristic)."""
        return count_tokens_tool(text)

    return server
