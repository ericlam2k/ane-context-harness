"""Integration: HTTP API on 127.0.0.1 (health, index, select)."""
from __future__ import annotations

import json
import time
import threading
import urllib.error
import urllib.request

from src.ane_context_harness.api import create_server
from src.ane_context_harness.config import build_config


def _wait_health(base):
    for _ in range(60):
        try:
            with urllib.request.urlopen(base + "/v1/health", timeout=2) as r:
                if r.status == 200:
                    return json.loads(r.read())
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


def _post(base, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read())


def test_api_health_and_select(tmp_path, py_repo):
    cfg = build_config({"index": {"storage_path": str(tmp_path / "store")},
                        # Budget-honest packing now fits small config files, so
                        # the fixture's credential file is denied at indexing
                        # time (same policy class as the .env deny above).
                        "privacy": {"never_read": ["**/.env*", "**/.aws/**",
                                                   "**/runtime.secrets.json"]}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        health = _wait_health(base)
        assert health["status"] == "ok"
        assert health["compute_mode"] == "deterministic_only"
        assert health["behavioral_profile"] == "DETERMINISTIC_ONLY"

        status, idx = _post(base, "/v1/repositories/index",
                            {"repository_path": py_repo, "repository_id": "synthetic_py_project"})
        assert status == 200
        assert idx["files_indexed"] >= 1
        assert idx["chunks_indexed"] >= 1

        status, sel = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation and update its tests",
            "token_budget": 1200,
            "explicit_paths": ["src/discount.py"],
        })
        assert status == 200
        assert sel["metrics"]["reduction_percent"] >= 25.0
        sel_paths = {e["path"] for e in sel["evidence"]}
        assert "src/discount.py" in sel_paths
        assert ".env" not in sel_paths
        assert sel["execution"]["reranker"] == "cpu_deterministic"
        assert sel["execution"]["fallback_used"] is False
        assert "AKIAIOSFODNN7EXAMPLE" not in sel["markdown"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_select_recovery_block_additive_only(tmp_path, py_repo):
    """Failure caught: the recovery block (what the pack could not admit
    and why) either goes missing from the wire contract when required
    evidence misses, or leaks new keys into a fully covered select."""
    cfg = build_config({"index": {"storage_path": str(tmp_path / "store")},
                        "privacy": {"never_read": ["**/.env*", "**/.aws/**",
                                                   "**/runtime.secrets.json"]}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, idx = _post(base, "/v1/repositories/index",
                            {"repository_path": py_repo,
                             "repository_id": "synthetic_py_project"})
        assert status == 200

        # Starved budget: named evidence misses and the block must appear
        # as additive top-level + metrics.diagnostics keys.
        status, starved = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation",
            "token_budget": 30,
        })
        assert status == 200
        diag = starved["metrics"]["diagnostics"]
        assert "recovery" in diag
        assert starved["recovery"] == diag["recovery"]
        rec = starved["recovery"]
        assert rec["required_evidence_recall"] < 1.0
        assert isinstance(rec["missed_claims"], list) and rec["missed_claims"]
        entry = rec["missed_claims"][0]
        assert set(entry) == {"chunk_id", "path", "symbol", "why",
                              "reasons", "command"}
        assert entry["why"] in {"budget", "capped", "dropped"}

        # Comfortable budget: everything covered; no new keys anywhere.
        status, covered = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation",
            "token_budget": 2000,
        })
        assert status == 200
        assert "recovery" not in covered
        assert "recovery" not in covered["metrics"]["diagnostics"]
        assert "recovery_tool" not in covered["metrics"]["diagnostics"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_rejects_oversized_body(tmp_path):
    cfg = build_config({"limits": {"request_body_bytes": 100},
                        "index": {"storage_path": str(tmp_path / "store")}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}/v1/repositories/index"
        data = json.dumps({"x": "a" * 5000}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "expected 413"
        except urllib.error.HTTPError as e:
            assert e.code == 413
    finally:
        server.shutdown()
        server.server_close()


def test_api_select_has_no_stated_keys_by_default(tmp_path, py_repo):
    """Failure caught: the stated-need diagnostics block leaking into
    responses for callers that never stated a need. The wire carries no
    stated keys; an unstated select must show no top-level and no
    diagnostics stated_* keys, exactly as before the feature landed."""
    cfg = build_config({"index": {"storage_path": str(tmp_path / "store")},
                        "privacy": {"never_read": ["**/.env*", "**/.aws/**",
                                                   "**/runtime.secrets.json"]}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, idx = _post(base, "/v1/repositories/index",
                            {"repository_path": py_repo,
                             "repository_id": "synthetic_py_project"})
        assert status == 200
        status, sel = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation",
            "token_budget": 1200,
        })
        assert status == 200
        assert "stated_need_resolution" not in sel
        assert "stated_claim_summary" not in sel
        diag = sel["metrics"]["diagnostics"]
        assert not any(k.startswith("stated_") for k in diag)
    finally:
        server.shutdown()
        server.server_close()


def test_api_select_recovery_prompt_additive_only(tmp_path, py_repo):
    """Failure caught: the ask affordance either goes missing from the
    wire contract when required evidence misses, or leaks a key into a
    fully covered select. The affordance is additive and present only
    when it fired, mirroring the recovery block's top-level + diagnostics
    pattern."""
    cfg = build_config({"index": {"storage_path": str(tmp_path / "store")},
                        "privacy": {"never_read": ["**/.env*", "**/.aws/**",
                                                   "**/runtime.secrets.json"]}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, idx = _post(base, "/v1/repositories/index",
                            {"repository_path": py_repo,
                             "repository_id": "synthetic_py_project"})
        assert status == 200

        # Starved budget: the recovery block fires and the affordance
        # rides it — top-level + diagnostics, one-to-one.
        status, starved = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation",
            "token_budget": 30,
        })
        assert status == 200
        diag = starved["metrics"]["diagnostics"]
        assert "recovery_prompt" in diag
        prompt = starved["recovery_prompt"]
        assert prompt == diag["recovery_prompt"]
        assert "src/discount.py" in prompt
        assert "--stated-symbol" in prompt and "--stated-need" in prompt

        # Comfortable budget: everything covered; no new keys anywhere.
        status, covered = _post(base, "/v1/context/select", {
            "repository_id": "synthetic_py_project",
            "task": "Fix the incorrect discount calculation",
            "token_budget": 2000,
        })
        assert status == 200
        assert "recovery_prompt" not in covered
        assert "recovery_prompt" not in covered["metrics"]["diagnostics"]
    finally:
        server.shutdown()
        server.server_close()
