"""Integration: `ane-harness mcp` subcommand guards the optional mcp extra.

The `mcp` package is an optional dependency (declared under the `mcp` extra in
pyproject.toml). When it is absent, `ane-harness mcp` must fail gracefully with
a JSON hint + exit code 1, never a traceback. If `mcp` *is* installed, the
subcommand should import and start the server (covered lightly here when the
package is present in the environment).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _have_mcp() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def test_mcp_subcommand_graceful_when_missing():
    if _have_mcp():
        pytest.skip("mcp package is installed; graceful-failure path not exercised")
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "mcp"],
        capture_output=True, text=True, timeout=30,
        cwd="/Users/quanglam/Documents/ANEharness",
    )
    assert proc.returncode == 1
    assert not proc.stdout  # error goes to stderr only
    data = json.loads(proc.stderr)
    assert data["ok"] is False
    assert "mcp extra not installed" in data["error"]


def test_mcp_subcommand_help_works():
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "mcp", "--help"],
        capture_output=True, text=True, timeout=30,
        cwd="/Users/quanglam/Documents/ANEharness",
    )
    assert proc.returncode == 0
    assert "--transport" in proc.stdout


def test_mcp_extra_declared_in_pyproject():
    import configparser
    cfg_text = (Path(__file__).parents[2] / "pyproject.toml").read_text()
    assert 'mcp = ["mcp[cli]>=1.0,<2"]' in cfg_text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
