"""Stage 0/1 provider evaluation: mock/dry-run, spend cap, no-network proof.

Covers docs/provider-evaluation-stages.md: dry-run performs zero network
calls (proven with socket removed), cost is DERIVED, live calls stay disabled
at the default cap of 0.0, and the adapters import no network libraries.
"""
from __future__ import annotations

import ast
import json
import pathlib
from types import SimpleNamespace

import pytest

from src.ane_context_harness.config import DEFAULT_CONFIG, build_config
from src.ane_context_harness.providers import SERIALIZERS, serialize
from src.ane_context_harness.providers.dryrun import (derived_request_cost_usd,
                                                     dry_run)

_NETWORK_MODULES = {"requests", "httpx", "aiohttp", "urllib.request",
                    "http.client", "socket", "ftplib", "telnetlib"}


def _package():
    return SimpleNamespace(
        evidence=[{
            "path": "src/a.py", "start_line": 1, "end_line": 10,
            "content_hash": "h" * 8, "symbol": "f", "score": 0.9,
            "selection_reasons": ["lexical_rerank"], "category": "implementation",
            "redacted": False, "content": "def f():\n    return 1\n",
        }],
        task="do the thing", markdown="", metrics={}, redaction_summary={},
        request_id="req", repository_id="r", policy_version="p",
        index_version="i", model_version="m",
        execution={"reranker": "cpu_deterministic"},
    )


def test_dry_run_reports_zero_network_and_derived_cost():
    out = dry_run("anthropic", _package())
    assert out["network_calls"] == 0
    assert out["stage"] == "1-dry-run"
    assert out["cost_status"].startswith("DERIVED")
    assert out["request_tokens"] > 0
    assert out["estimated_cost_usd_derived"] == round(
        out["request_tokens"] * out["usd_per_million_input"] / 1_000_000, 6)


def test_dry_run_live_disabled_by_default_cap():
    out = dry_run("openai", _package())  # default cap 0.0
    assert out["max_provider_spend_usd"] == 0.0
    assert out["live_run_allowed"] is False


def test_dry_run_cap_must_cover_estimate():
    body, tokens, cost = derived_request_cost_usd("anthropic", _package())
    assert cost > 0
    allowed = dry_run("anthropic", _package(),
                      max_provider_spend_usd=cost - 0.000001)
    assert allowed["live_run_allowed"] is False
    allowed = dry_run("anthropic", _package(),
                      max_provider_spend_usd=cost + 0.001)
    assert allowed["live_run_allowed"] is True


def test_default_config_disables_live_provider_calls():
    assert DEFAULT_CONFIG["limits"]["max_provider_spend_usd"] == 0.0
    cfg = build_config({})
    assert cfg["limits"]["max_provider_spend_usd"] == 0.0


def test_default_config_cap_wired_into_dry_run():
    """Config `limits.max_provider_spend_usd` (default 0.0) disables live calls
    when passed into dry_run — the wiring between default config and the
    stage-1 gate."""
    cfg = build_config({})
    out = dry_run("openai_compat", _package(),
                  max_provider_spend_usd=cfg["limits"]["max_provider_spend_usd"])
    assert out["max_provider_spend_usd"] == 0.0
    assert out["live_run_allowed"] is False


def test_dry_run_survives_socket_removed(monkeypatch):
    import socket
    def _blocked(*a, **k):
        raise AssertionError("network attempted during dry_run")
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    out = dry_run("openai_compat", _package(), max_provider_spend_usd=5.0)
    assert out["network_calls"] == 0
    assert out["live_run_allowed"] is True


def test_providers_package_has_no_network_imports():
    root = pathlib.Path("src/ane_context_harness/providers")
    offenders = []
    for py in sorted(root.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name in _NETWORK_MODULES or name.startswith("urllib.request"):
                    offenders.append(f"{py.name}:{node.lineno} {name}")
    assert not offenders, offenders


def test_dry_run_body_matches_serializer_output():
    pkg = _package()
    for provider in sorted(SERIALIZERS):
        out = dry_run(provider, pkg)
        assert out["request"] == serialize(provider, pkg)
        json.dumps(out["request"], default=str)  # serializable report
