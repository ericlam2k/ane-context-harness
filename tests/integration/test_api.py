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
                        "privacy": {"never_read": ["**/.env*", "**/.aws/**"]}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        health = _wait_health(base)
        assert health["status"] == "ok"
        assert health["compute_mode"] == "deterministic_only"
        assert health["behavioral_profile"] == "DETERMINISTIC_ONLY"
        assert health["coreml_model_loaded"] is False
        assert health["coreml_compute_units_requested"] is None  # no ANE claim

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
