"""Local HTTP API (stdlib http.server, bound to 127.0.0.1).

Endpoints: GET /v1/health, POST /v1/repositories/index, POST /v1/context/select,
POST /v1/feedback, POST /v1/context/compress-output.

No arbitrary shell execution. No repository content is forwarded externally.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import schemas
from .compression import compress_tool_output
from .config import build_config
from .pipeline import Pipeline
from .providers.markdown import render_markdown


class _Handler(BaseHTTPRequestHandler):
    pipeline: Pipeline = None  # type: ignore
    config: dict = None  # type: ignore

    def log_message(self, fmt, *args):
        # Default request logging is method+path+status only; never logs body/source.
        super().log_message(fmt, *args)

    def _send(self, code: int, obj: dict | str):
        data = json.dumps(obj, default=str).encode("utf-8") if not isinstance(obj, str) else obj.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/health":
            self._send(200, _health_dict(self.pipeline.health()))
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        max_body = self.config["limits"]["request_body_bytes"]
        if length > max_body:
            self._send(413, {"error": "request_body_too_large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid_json"})
            return
        if path == "/v1/repositories/index":
            req = schemas.IndexRequest(**body)
            resp = self.pipeline.register_repository(req.repository_path, req.repository_id, req.force_rebuild)
            self._send(200, resp.__dict__ if hasattr(resp, "__dict__") else resp)
            return
        if path == "/v1/context/select":
            req = _parse_select(body)
            pkg = self.pipeline.select_context(req)
            if not pkg.markdown:
                pkg.markdown = render_markdown(pkg)
            out = pkg.__dict__ if hasattr(pkg, "__dict__") else pkg
            self._send(200, out)
            return
        if path == "/v1/context/compress-output":
            if "content" not in body:
                self._send(400, {"error": "missing_content"})
                return
            try:
                result = compress_tool_output(
                    kind=str(body.get("kind", "terminal")),
                    command=str(body.get("command", "")),
                    exit_code=int(body.get("exit_code", 0)),
                    content=str(body["content"]),
                    token_budget=int(body.get("token_budget", 2000)),
                    context_lines=int(body.get("context_lines", 3)),
                    reference=body.get("reference"),
                )
            except (ValueError, TypeError) as e:
                self._send(400, {"error": "invalid_compress_request",
                                 "detail": str(e)})
                return
            self._send(200, result)
            return
        if path == "/v1/feedback":
            self._send(202, {"status": "accepted_local"})
            return
        self._send(404, {"error": "not_found"})

    def do_PUT(self):
        self._send(405, {"error": "method_not_allowed"})


def _parse_select(body: dict) -> schemas.SelectRequest:
    opts = body.get("options", {}) or {}
    return schemas.SelectRequest(
        repository_id=body["repository_id"],
        task=body["task"],
        token_budget=int(body.get("token_budget", 12000)),
        explicit_paths=body.get("explicit_paths", []),
        exclude_paths=body.get("exclude_paths", []),
        tool_outputs=body.get("tool_outputs", []),
        conversation_summary=body.get("conversation_summary"),
        options=opts,
    )


def _health_dict(h: schemas.HealthResponse) -> dict:
    return {
        "status": h.status,
        "platform": h.platform,
        "compute_mode": h.compute_mode,
        "index_version": h.index_version,
        "service_version": h.service_version,
        "behavioral_profile": h.behavioral_profile,
        "fallback_used": h.fallback_used,
        "capabilities": h.capabilities,
    }


def create_server(host: str, port: int, config: dict | None = None) -> ThreadingHTTPServer:
    cfg = config or build_config()
    _Handler.config = cfg
    _Handler.pipeline = Pipeline(cfg)
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    return server


def serve(host: str = "127.0.0.1", port: int = 8765):
    server = create_server(host, port)
    print(f"ane-context-harness listening on {host}:{port} (compute_mode=deterministic_only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
