"""Integration: the `ane-harness update` CLI command batch token savings logging.

Isolated per test via ANE_HARNESS_CONFIG pointing at a tmp config with a
throwaway storage path (no pollution of the real `~/.ane_context_harness`).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Repo root derived from this file: CLI subprocesses must run against the
# checkout under test, never a hardcoded developer path.
ROOT = Path(__file__).resolve().parents[2]
REPO = str(ROOT / "tests/fixtures/synthetic_py_project")


def _repo_env(extra: dict | None = None) -> dict:
    """Subprocess env forcing import of this checkout's src.

    The harness may be pip-installed editable from a different checkout;
    prepending this repo's src to PYTHONPATH keeps CLI subprocesses hermetic.
    """
    env = dict(os.environ)
    src = str(ROOT / "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev}" if prev else src
    if extra:
        env.update(extra)
    return env


def _cfg_env(tmp_path, monkeypatch):
    storage = tmp_path / "store"
    cfg = tmp_path / "opencode_test_config.yaml"
    cfg.write_text(
        f"index:\n  storage_path: {storage}\n"
        "privacy:\n  never_read:\n    - '**/.env*'\n    - '**/.aws/**'\n"
        "    - '**/.ssh/**'\n    - '**/*.pem'\n    - '**/.EnvLocal'\n",
        encoding="utf-8")
    monkeypatch.setenv("ANE_HARNESS_CONFIG", str(cfg))


def test_update_logs_before_after_tokens(tmp_path, monkeypatch):
    _cfg_env(tmp_path, monkeypatch)
    subprocess.run(["ane-harness", "index", "--repo", REPO,
                    "--repo-id", "py_update_test"], check=True, timeout=180,
                   capture_output=True, text=True, env=_repo_env())
    log = tmp_path / "update.log.jsonl"
    tasks = "Fix the discount calculation\ndebug the inventory loader\n"
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "update",
         "--repo-id", "py_update_test",
         "--budget", "2000", "--log", str(log)],
        input=tasks, capture_output=True, text=True, timeout=180,
        cwd=str(ROOT), env=_repo_env())
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["tasks"] == 2
    assert data["before_tokens_total"] > data["after_tokens_total"] > 0
    assert data["tokens_removed_total"] > 0
    assert 0.0 < data["reduction_percent_median"] <= 100.0
    row = data["per_task"][0]
    for key in ("candidate_tokens", "selected_tokens", "tokens_removed",
                "reduction_percent", "task"):
        assert key in row
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["selected_tokens"] <= first["candidate_tokens"]
    assert "redaction does not guarantee" in proc.stderr


def test_update_accepts_jsonl_tasks(tmp_path, monkeypatch):
    _cfg_env(tmp_path, monkeypatch)
    subprocess.run(["ane-harness", "index", "--repo", REPO,
                    "--repo-id", "py_update_test"], check=True, timeout=180,
                   capture_output=True, text=True, env=_repo_env())
    payload = '{"task": "review reporting stats output"}\n'
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "update",
         "--repo-id", "py_update_test", "--budget", "1500"],
        input=payload, capture_output=True, text=True, timeout=180,
        cwd=str(ROOT), env=_repo_env())
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["tasks"] == 1
    assert data["per_task"][0]["task"] == "review reporting stats output"
