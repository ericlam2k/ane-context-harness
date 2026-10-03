"""Integration: live MCP server end-to-end over stdio.

Spawns `ane-harness mcp --transport stdio` as a real subprocess and drives it with
the official `mcp.client` stdio transport. Skipped when the optional `mcp` extra
is absent, so the default suite (no optional deps) stays green — matching the
documented promise that `mcp` is opt-in, not a hard dependency.

Covers:
  - server initializes with name 'ane-harness'
  - tools advertised: select, update, verify, tokens
  - `tokens` tool returns the deterministic pinned-backend count (regex v2):
    "hello world foo bar" -> 4
"""
from __future__ import annotations

import os
import sys

import pytest


def _have_mcp() -> bool:
    try:
        import mcp  # noqa: F401
        from mcp.client.stdio import stdio_client
        from mcp.client.session import ClientSession
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _have_mcp(), reason="mcp extra not installed")
def test_mcp_live_server_stdio():
    import anyio
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ane_context_harness.cli", "mcp", "--transport", "stdio"],
        env=os.environ)

    async def _run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "ane-harness"
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                assert {"select", "update", "verify", "tokens"} <= set(names)

                tok = await session.call_tool("tokens", {"text": "hello world foo bar"})
                assert tok.content[0].text.strip() == "4"

    anyio.run(_run)
