"""Unit: session savings ledger (counts only, local, never breaks runs)."""
from __future__ import annotations

import json

from src.ane_context_harness import usage


def test_record_and_summarize_day(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    usage.record("select", 10000, 2000, 50.0, path=ledger)
    usage.record("update", 20000, 4000, tasks=2, path=ledger)
    stats = usage.summarize(path=ledger)
    assert stats["runs"] == 2
    assert stats["tasks"] == 3
    assert stats["candidate_tokens"] == 30000
    assert stats["selected_tokens"] == 6000
    assert stats["saved_percent"] == 80.0


def test_summarize_empty_ledger(tmp_path):
    stats = usage.summarize(path=tmp_path / "missing.jsonl")
    assert stats["runs"] == 0
    assert stats["saved_percent"] == 0.0


def test_summarize_all_spans_days(tmp_path, monkeypatch):
    import time as _time
    ledger = tmp_path / "usage.jsonl"
    usage.record("select", 1000, 500, path=ledger)
    stats = usage.summarize_all(path=ledger)
    assert stats["days"] == 1
    assert stats["runs"] == 1


def test_format_session_leads_with_savings(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    usage.record("select", 10000, 1000, path=ledger)
    line = usage.format_session(usage.summarize(path=ledger))
    assert line.startswith("ane-harness daily")
    assert "saved 90.0% · uses 1.0k of 10.0k (10.0%)" in line
    assert "#" not in line


def test_record_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ANE_HARNESS_NO_USAGE_LOG", "1")
    assert usage.log_enabled() is False
    # unwritable path must not raise
    usage.record("select", 1, 1, path=tmp_path / "nope" / "x.jsonl")


def test_log_disabled_under_pytest():
    # the suite itself must never pollute the user's real ledger
    assert usage.log_enabled() is False


def test_shell_init_snippet_guarded():
    assert "command -v ane-harness" in usage.SHELL_INIT_SNIPPET
    assert "daily --brief" in usage.SHELL_INIT_SNIPPET
    assert "zshexit" in usage.SHELL_INIT_SNIPPET
    assert "trap" in usage.SHELL_INIT_SNIPPET


def test_cli_daily_and_session_alias_work(tmp_path, monkeypatch, capsys):
    # regression: "daily" was a dead subcommand (dispatch matched "session" only)
    monkeypatch.setenv("HOME", str(tmp_path))
    from src.ane_context_harness.cli import main
    assert main(["daily"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ane-harness daily (today)")
    assert main(["session", "--brief"]) == 0
    assert capsys.readouterr().out == ""  # silent with no runs yet
