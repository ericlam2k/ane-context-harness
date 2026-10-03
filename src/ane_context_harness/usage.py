"""Session savings ledger for vibe-coders.

Nobody remembers flags. So every `select`/`update` run silently appends one
counts-only line (no task text, no paths, no content) to a local ledger:

    ~/.ane_context_harness/usage.jsonl

`ane-harness session` totals it (today + all time), and
`eval "$(ane-harness shell-init)"` prints the session line when the shell
exits. Users only ever see savings; everything else is handled.

Disabled with ANE_HARNESS_NO_USAGE_LOG=1. Never written under pytest.
"""
from __future__ import annotations

import json
import os
import time as _time
from pathlib import Path
from typing import Any

LEDGER_NAME = "usage.jsonl"


def ledger_path() -> Path:
    return Path.home() / ".ane_context_harness" / LEDGER_NAME


def log_enabled() -> bool:
    if os.environ.get("ANE_HARNESS_NO_USAGE_LOG"):
        return False
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    return True


def record(kind: str, candidate_tokens: int, selected_tokens: int,
           latency_ms: float | None = None, tasks: int = 1,
           path: Path | None = None) -> None:
    """Append one counts-only entry. Never raises (ledger must not break runs)."""
    try:
        target = path or ledger_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": int(_time.time()), "kind": kind, "tasks": tasks,
                 "candidate_tokens": int(candidate_tokens),
                 "selected_tokens": int(selected_tokens),
                 "latency_ms": latency_ms}
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _day(ts: int) -> str:
    return _time.strftime("%Y-%m-%d", _time.localtime(ts))


def summarize(path: Path | None = None,
              day: str | None = None) -> dict[str, Any]:
    """Aggregate entries (optionally for one YYYY-MM-DD day; default today)."""
    target = path or ledger_path()
    runs = tasks = cand = sel = 0
    lat = 0.0
    want = day or _time.strftime("%Y-%m-%d", _time.localtime())
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if _day(int(e.get("ts", 0))) != want:
            continue
        runs += 1
        tasks += int(e.get("tasks", 1))
        cand += int(e.get("candidate_tokens", 0))
        sel += int(e.get("selected_tokens", 0))
        if e.get("latency_ms") is not None:
            lat += float(e["latency_ms"])
    saved = ((cand - sel) / cand * 100.0) if cand else 0.0
    return {"day": want, "runs": runs, "tasks": tasks,
            "candidate_tokens": cand, "selected_tokens": sel,
            "saved_percent": round(saved, 1),
            "latency_ms_total": round(lat, 1)}


def summarize_all(path: Path | None = None) -> dict[str, Any]:
    """Aggregate across all days."""
    target = path or ledger_path()
    days: set[str] = set()
    runs = tasks = cand = sel = 0
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        days.add(_day(int(e.get("ts", 0))))
        runs += 1
        tasks += int(e.get("tasks", 1))
        cand += int(e.get("candidate_tokens", 0))
        sel += int(e.get("selected_tokens", 0))
    saved = ((cand - sel) / cand * 100.0) if cand else 0.0
    return {"days": len(days), "runs": runs, "tasks": tasks,
            "candidate_tokens": cand, "selected_tokens": sel,
            "saved_percent": round(saved, 1)}


def format_session(stats: dict[str, Any], label: str = "today") -> str:
    from .summary import fmt_tokens
    return (f"# ane-harness session ({label}): {stats['saved_percent']}% saved "
            f"({fmt_tokens(stats['selected_tokens'])} of "
            f"{fmt_tokens(stats['candidate_tokens'])}) · "
            f"{stats['tasks']} tasks in {stats['runs']} runs")


SHELL_INIT_SNIPPET = """\
# ane-harness: print session savings on shell exit.
# Opt-in: eval "$(ane-harness shell-init)"
_ane_session_summary() {
  command -v ane-harness >/dev/null 2>&1 || return 0
  ane-harness session --brief 2>/dev/null || true
}
if [ -n "${ZSH_VERSION:-}" ]; then
  autoload -Uz add-zsh-hook 2>/dev/null && add-zsh-hook zshexit _ane_session_summary 2>/dev/null || true
else
  _ane_prev_exit=$(trap -p EXIT 2>/dev/null | sed -n "s/^trap -- '\\(.*\\)' EXIT$/\\1/p")
  if [ -n "$_ane_prev_exit" ]; then
    trap "_ane_session_summary; $_ane_prev_exit" EXIT
  else
    trap _ane_session_summary EXIT
  fi
fi
"""
