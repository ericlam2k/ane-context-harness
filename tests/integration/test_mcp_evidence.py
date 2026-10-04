"""Integration: MCP select delivers the evidence package, not just stats.

Calls select_context_tool directly (no `mcp` extra needed) and asserts the
evidence round-trips: per-chunk content, markdown, and the redaction caveat.
"""
import asyncio
import json

from ane_context_harness.cli import main
from ane_context_harness.mcp_server import CONTENT_WARNING, select_context_tool

FIXTURE = "tests/fixtures/synthetic_py_project"
REPO_ID = "ut-mcp-evidence"


def _select(**kw):
    main(["index", "--repo", FIXTURE, "--repo-id", REPO_ID])
    return json.loads(asyncio.run(select_context_tool(REPO_ID, **kw)))


def test_mcp_select_delivers_evidence_package():
    out = _select(task="Fix the incorrect discount calculation", budget=2000)
    assert out["summary"].startswith("ane-harness:")
    assert out["content_warning"] == CONTENT_WARNING
    assert isinstance(out["evidence"], list) and len(out["evidence"]) >= 1
    first = out["evidence"][0]
    for key in ("path", "start_line", "end_line", "symbol", "score",
                "selection_reasons", "content_hash", "content"):
        assert key in first
    assert any(e["content"].strip() for e in out["evidence"])
    assert out["markdown_length"] == len(out["markdown"]) > 0
    assert "Tokens:" in out["markdown"]


def test_mcp_select_stats_only_when_opted_out():
    out = _select(task="Fix the incorrect discount calculation", budget=2000,
                  include_content=False)
    assert out["summary"].startswith("ane-harness:")
    assert "evidence" not in out
    assert "markdown" not in out
    assert "content_warning" not in out
    assert out["reduction_percent"] >= 0.0
