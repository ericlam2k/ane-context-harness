"""Unit tests for FR-7 tool-output compression (no heavy deps)."""
from __future__ import annotations

import hashlib

import pytest

from src.ane_context_harness.compression import ALLOWED_KINDS, compress_tool_output

PYTEST_FAILURE = """============================= test session starts ==============================
collected 6 items

tests/test_discount.py ..FF..                                          [ 50%]

=================================== FAILURES ===================================
_________________________________ test_bulk ____________________________________

    def test_bulk():
>       assert calc(10) == 90
E       assert 95 == 90

tests/test_discount.py:12: AssertionError
=========================== short test summary info ============================
FAILED tests/test_discount.py::test_bulk - AssertionError: 95 != 90
FAILED tests/test_discount.py::test_stack - KeyError: 'price'
========================= 2 failed, 4 passed in 0.42s ==========================
"""

PIP_NOISE = "\n".join(
    f"Requirement already satisfied: pkg{i}==1.0 in /site (1.0)" for i in range(40))

PROGRESS = "\n".join(
    f"{i}%|####      | {i}/100 [00:01<00:02, 40.00it/s]" for i in range(0, 100, 10))

TRACEBACK = """Traceback (most recent call last):
  File "app/main.py", line 10, in <module>
    run()
  File "app/worker.py", line 22, in run
    task()
ValueError: boom
Traceback (most recent call last):
  File "app/main.py", line 10, in <module>
    run()
ValueError: boom"""

LOG_OUTPUT = "\n".join([
    "2026-10-02 10:00:00 INFO starting server on 127.0.0.1",
    "2026-10-02 10:00:01 WARN port 8765 busy",
    "2026-10-02 10:00:01 WARN port 8765 busy",
    "2026-10-02 10:00:02 WARN port 8765 busy",
    "2026-10-02 10:00:03 ERROR bind failed: address in use",
    "2026-10-02 10:00:04 INFO retrying with fallback port",
])


def test_allowed_kinds_and_validation():
    assert ALLOWED_KINDS == ("terminal", "build", "lint", "test")
    with pytest.raises(ValueError):
        compress_tool_output("database", "pg_dump", 0, "x")
    with pytest.raises(ValueError):
        compress_tool_output("test", "pytest", 0, "x", token_budget=0)
    with pytest.raises(ValueError):
        compress_tool_output("test", "pytest", 0, "x", context_lines=-1)


def test_preserves_failure_facts():
    r = compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE, token_budget=800)
    out = r["compressed"]
    assert "command: pytest -q" in out
    assert "exit_code: 1" in out
    assert "FAILED tests/test_discount.py::test_bulk" in out
    assert "AssertionError" in out
    assert "tests/test_discount.py:12" in out
    assert "E       assert 95 == 90" in out
    assert "2 failed, 4 passed in 0.42s" in out


def test_collapses_progress_and_install_noise():
    content = PIP_NOISE + "\n" + PROGRESS + "\n" + PYTEST_FAILURE
    r = compress_tool_output("test", "pytest -q", 1, content, token_budget=800)
    assert r["removed"]["install"] == 40
    assert r["removed"]["progress"] == 10
    assert "Requirement already satisfied" not in r["compressed"]
    assert "pkg37" not in r["compressed"]
    assert "40%|####" not in r["compressed"]
    assert "[install] 40 dependency-install lines collapsed" not in r["compressed"]
    assert r["reduction_percent"] > 0


def test_removes_duplicate_stack_frames():
    r = compress_tool_output("terminal", "python app.py", 1, TRACEBACK,
                             token_budget=800, context_lines=5)
    assert r["removed"]["duplicate_frames"] >= 1
    assert r["compressed"].count('File "app/main.py", line 10') == 1
    assert r["compressed"].count('File "app/worker.py", line 22') == 1
    assert r["kept"]["stack_frames"] == 2
    assert "ValueError: boom" in r["compressed"]


def test_dedupes_repeated_warnings():
    r = compress_tool_output("terminal", "app run", 1, LOG_OUTPUT, token_budget=800)
    assert r["compressed"].count("WARN port 8765 busy") == 1
    assert r["removed"]["repeated_warnings"] == 2
    assert "ERROR bind failed: address in use" in r["compressed"]


def test_success_listings_removed_for_failed_tests():
    ok_block = "\n".join([
        "tests/test_a.py::test_one PASSED                               [ 33%]",
        "tests/test_a.py::test_two PASSED                               [ 66%]",
        "tests/test_a.py::test_three FAILED                             [100%]",
        "FAILED tests/test_a.py::test_three - AssertionError: no",
        "========================= 1 failed, 2 passed in 0.31s ===========",
    ])
    content = PYTEST_FAILURE + "\n" + ok_block
    r = compress_tool_output("test", "pytest -q", 1, content, token_budget=2000)
    assert "test_one PASSED" not in r["compressed"]
    assert "FAILED tests/test_a.py::test_three" in r["compressed"]


def test_successful_run_collapses_to_summary():
    ok = "\n".join([
        "collected 3 items",
        "tests/test_a.py ...                                              [100%]",
        "",
        "========================= 3 passed in 0.11s =========================",
    ])
    r = compress_tool_output("test", "pytest -q", 0, ok, token_budget=500)
    assert "3 passed in 0.11s" in r["compressed"]
    assert "tests/test_a.py ..." not in r["compressed"]
    assert r["within_budget"] is True


def test_original_content_never_returned():
    r = compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE, token_budget=800)
    expected = hashlib.sha256(PYTEST_FAILURE.encode("utf-8")).hexdigest()
    assert r["content_sha256"] == f"sha256:{expected}"
    assert "reference" not in r or r["reference"] is None
    assert all(v != PYTEST_FAILURE for v in r.values())
    # compressed is a strict subset representation, not the whole original
    assert r["compressed"] != PYTEST_FAILURE


def test_reference_passthrough():
    r = compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE,
                             reference="/tmp/last-run.log")
    assert r["reference"] == "/tmp/last-run.log"


def test_budget_is_enforced():
    content = PIP_NOISE + "\n" + PROGRESS + "\n" + PYTEST_FAILURE
    generous = compress_tool_output("test", "pytest -q", 1, content, token_budget=900)
    assert generous["within_budget"] is True
    assert "command: pytest -q" in generous["compressed"]
    assert "exit_code: 1" in generous["compressed"]
    assert "FAILED tests/test_discount.py::test_bulk" in generous["compressed"]

    tight = compress_tool_output("test", "pytest -q", 1, content, token_budget=100)
    assert tight["compressed_tokens"] <= 100
    assert tight["within_budget"] is True
    assert "command: pytest -q" in tight["compressed"]
    assert "exit_code: 1" in tight["compressed"]


def test_build_kind_keeps_compile_errors_and_paths():
    content = "\n".join(["Compiling serde v1.0.100"] * 25 + [
        "error[E0308]: mismatched types",
        "  --> src/main.rs:10:5",
        "   |",
        '10 |     let x: i32 = "hi";',
        "   |            ^^^ expected `i32`, found `&str`",
        "",
        "error: aborting due to previous error",
        "",
        "Build failed!",
    ])
    r = compress_tool_output("build", "cargo build", 101, content, token_budget=500)
    assert r["removed"]["install"] == 25
    assert "error[E0308]: mismatched types" in r["compressed"]
    assert "--> src/main.rs:10:5" in r["compressed"]
    assert "Build failed!" in r["compressed"]
    assert r["within_budget"] is True


def test_log_kind_keeps_plain_lines_in_order():
    r = compress_tool_output("terminal", "app run", 1, LOG_OUTPUT, token_budget=800)
    lines = [l for l in r["compressed"].splitlines()
             if l.startswith("2026-")]
    assert len(lines) == 4  # INFO start, one WARN (2 dupes collapsed), ERROR, INFO retry
    assert lines[0].endswith("starting server on 127.0.0.1")
    assert lines[-1].endswith("retrying with fallback port")
    assert sum(1 for l in lines if "WARN" in l) == 1


def test_output_is_deterministic():
    a = compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE, token_budget=800)
    b = compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE, token_budget=800)
    assert a == b


def test_ansi_escape_codes_are_stripped():
    content = "\x1b[31merror\x1b[0m: disk full\x1b[K"
    r = compress_tool_output("terminal", "df", 1, content, token_budget=200)
    assert "\x1b[" not in r["compressed"]
    assert "disk full" in r["compressed"]
