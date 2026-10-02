"""Integration: POST /v1/context/compress-output over HTTP (FR-7, thesis 7.4)."""
from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request

from src.ane_context_harness.api import create_server
from src.ane_context_harness.config import build_config

RAW = "\n".join(
    [f"Requirement already satisfied: pkg{i}==1.0" for i in range(30)] + [
        "collected 2 items",
        "tests/test_x.py F                                               [ 50%]",
        "=================================== FAILURES ===================================",
        "================================== ERRORS ======================================",
        "E       AssertionError: 1 != 2",
        "tests/test_x.py:4: AssertionError",
        "FAILED tests/test_x.py::test_it - AssertionError: 1 != 2",
        "========================= 1 failed, 1 passed in 0.05s ========================",
    ])


def _post(base, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_compress_output_endpoint_roundtrip(tmp_path):
    cfg = build_config({"index": {"storage_path": str(tmp_path / "store")}})
    server = create_server("127.0.0.1", 0, config=cfg)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, out = _post(base, "/v1/context/compress-output", {
            "kind": "test", "command": "pytest -q", "exit_code": 1,
            "content": RAW, "token_budget": 500,
        })
        assert status == 200
        assert out["kind"] == "test"
        assert out["command"] == "pytest -q"
        assert out["exit_code"] == 1
        assert out["within_budget"] is True
        assert out["compressed_tokens"] <= 500
        assert out["content_sha256"] == "sha256:" + hashlib.sha256(
            RAW.encode("utf-8")).hexdigest()
        assert out["reference"] is None
        assert out["original_tokens"] > out["compressed_tokens"]
        assert out["reduction_percent"] > 0
        assert "FAILED tests/test_x.py::test_it" in out["compressed"]
        assert "exit_code: 1" in out["compressed"]
        assert "Requirement already satisfied" not in out["compressed"]
        # full original must not come back downstream
        assert out["compressed"] != RAW

        status, out2 = _post(base, "/v1/context/compress-output", {
            "kind": "test", "command": "pytest -q", "exit_code": 1,
            "content": RAW, "token_budget": 500,
        })
        assert status == 200 and out2 == out  # deterministic through HTTP

        status, err = _post(base, "/v1/context/compress-output",
                            {"kind": "database", "command": "x", "content": "y"})
        assert status == 400 and err["error"] == "invalid_compress_request"

        status, err = _post(base, "/v1/context/compress-output",
                            {"kind": "test", "command": "x"})
        assert status == 400 and err["error"] == "missing_content"
    finally:
        server.shutdown()
        server.server_close()
