"""Unit: provider-metered with/without proof (metering.py + meter command).

Hermetic: an in-process stub proxy (localhost HTTP server) returns canned
usage objects, so no test ever touches the network or spends anything.
Portable (public-syncable): stdlib only, fixture repos only.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ane_context_harness.config import build_config, merge
from ane_context_harness.metering import (
    build_bodies,
    extract_metered,
    meter_footer,
    refuse_unless_free,
    run_metered,
    summarize,
    window_gate,
)
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.summary import fmt_tokens

FIXTURE = "tests/fixtures/synthetic_py_project"


class _StubProxy(BaseHTTPRequestHandler):
    """Canned chat/completions: prompt tokens scale with content length."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        content_len = sum(len(m.get("content", ""))
                             for m in body.get("messages", []))
        prompt_tokens = max(1, content_len // 4)
        payload = {
            "model": "stub-free",
            "choices": [{"message": {"content": "stub answer"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": 10,
                      "total_tokens": prompt_tokens + 10},
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def proxy_url():
    server = HTTPServer(("127.0.0.1", 0), _StubProxy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _pipe(tmp_path):
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5},
            "retention": {"ttl_seconds": 300}}
    pipe = Pipeline(build_config(merge(base, {})))
    pipe.register_repository(FIXTURE, "meter-fx")
    return pipe


def test_refuse_unless_free(tmp_path):
    refuse_unless_free("OR-Laguna")
    with pytest.raises(ValueError, match="refusing non-free model"):
        refuse_unless_free("gpt-5.6")


def test_window_gate(tmp_path):
    assert window_gate("OR-Laguna", 1000)["fits"] is True
    gate = window_gate("OR-Laguna", 10 ** 9)
    assert gate["fits"] is False
    assert gate["window"] == 128000


def test_build_bodies_same_envelope_arm_a_biggest(tmp_path):
    pipe = _pipe(tmp_path)
    arms = build_bodies("Fix the discount calculation", "meter-fx", pipe,
                        "OR-Laguna", 2000, ["standard", "toon"])
    assert set(arms) == {"A_full", "B_harness", "T_toon"}
    for spec in arms.values():
        roles = [m["role"] for m in spec["messages"]]
        assert roles == ["system", "user"]
        assert spec["gate"]["fits"] is True
    assert arms["A_full"]["estimator_tokens"] > arms["B_harness"]["estimator_tokens"]
    assert arms["T_toon"]["renderer"] == "compact-ours"
    with pytest.raises(ValueError, match="unknown format"):
        build_bodies("t", "meter-fx", pipe, "OR-Laguna", 2000, ["nope"])


def test_build_bodies_headroom_missing_package_refuses(tmp_path):
    try:
        import headroom  # noqa: F401
        pytest.skip("headroom installed here; refusal path untestable")
    except ImportError:
        pass
    pipe = _pipe(tmp_path)
    with pytest.raises(ValueError, match="needs the headroom package"):
        build_bodies("t", "meter-fx", pipe, "OR-Laguna", 2000, ["headroom"])


def test_extract_metered_tolerates_missing_usage():
    assert extract_metered({})["prompt_tokens"] is None
    met = extract_metered({"usage": {"prompt_tokens": 5,
                                     "completion_tokens": 1,
                                     "total_tokens": 6},
                           "choices": [{"message": {"content": "hi"},
                                        "finish_reason": "stop"}],
                           "model": "m"})
    assert (met["prompt_tokens"], met["completion_tokens"],
            met["output_text"]) == (5, 1, "hi")


def test_run_metered_reports_provider_counted_delta(tmp_path, proxy_url):
    pipe = _pipe(tmp_path)
    records = run_metered("Fix the discount calculation", "meter-fx", pipe,
                          "OR-Laguna", "test-key", proxy_url, 2000,
                          ["standard", "toon"], pace_s=0.0)
    assert [r["arm"] for r in records] == ["A_full", "B_harness", "T_toon"]
    assert all(r["ok"] for r in records)
    summary = summarize(records)
    a = summary["arms"]["A_full"]["metered_input"]
    b = summary["arms"]["B_harness"]["metered_input"]
    assert a > b > 0
    row = summary["arms"]["B_harness"]
    assert row["delta_vs_A_qty"] == a - b
    assert row["delta_vs_A_pct"] == round((a - b) / a * 100, 2)
    foot = meter_footer(summary, "OR-Laguna")
    assert "provider-counted total input" in foot
    assert f"(-{fmt_tokens(a - b)}, -{row['delta_vs_A_pct']}%)" in foot


def test_run_metered_refuses_paid_model(tmp_path, proxy_url):
    pipe = _pipe(tmp_path)
    with pytest.raises(ValueError, match="refusing non-free model"):
        run_metered("t", "meter-fx", pipe, "gpt-5.6", "k", proxy_url,
                    2000, ["standard"], pace_s=0.0)


def test_summarize_all_failed_arms(tmp_path):
    records = [{"arm": "A_full", "model": "m", "ok": False,
                "error": "boom", "estimator_input_tokens": 5,
                "window_gate": {"fits": True}}]
    summary = summarize(records)
    assert summary["reference_metered_input"] is None
    assert "no provider-counted usage" in meter_footer(summary, "m")
