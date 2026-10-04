"""Integration: `ane-harness proxy` agent mode (stdin tasks -> stdout markdown).

Hermetic via tmp ANE_HARNESS_CONFIG storage (same pattern as the update
command tests): no pollution of the real ~/.ane_context_harness.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = str(ROOT / "tests/fixtures/synthetic_py_project")


def _repo_env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["ANE_HARNESS_NO_LOAD_SENSE"] = "1"
    src = str(ROOT / "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev}" if prev else src
    if extra:
        env.update(extra)
    return env


def _cfg_env(tmp_path, monkeypatch):
    storage = tmp_path / "store"
    cfg = tmp_path / "proxy_test_config.yaml"
    cfg.write_text(
        f"index:\n  storage_path: {storage}\n"
        "privacy:\n  never_read:\n    - '**/.env*'\n    - '**/.aws/**'\n"
        "    - '**/.ssh/**'\n    - '**/*.pem'\n    - '**/.EnvLocal'\n",
        encoding="utf-8")
    monkeypatch.setenv("ANE_HARNESS_CONFIG", str(cfg))


def _proxy(tmp_path, stdin_text, *args):
    return subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "proxy",
         "--repo-id", "py_proxy_test", *args],
        input=stdin_text, capture_output=True, text=True, timeout=180,
        cwd=str(ROOT), env=_repo_env())


def test_proxy_emits_markdown_per_task(tmp_path, monkeypatch):
    _cfg_env(tmp_path, monkeypatch)
    subprocess.run(["ane-harness", "index", "--repo", REPO,
                    "--repo-id", "py_proxy_test"], check=True, timeout=180,
                   capture_output=True, text=True, env=_repo_env())
    tasks = ('{"task": "Fix the discount calculation"}\n'
             'debug the inventory loader\n')
    proc = _proxy(tmp_path, tasks, "--budget", "2000")
    assert proc.returncode == 0
    # stdout: two markdown docs with machine-split comment headers
    assert proc.stdout.count("<!-- ane-harness task ") == 2
    assert "1/2" in proc.stdout and "2/2" in proc.stdout
    assert "**Tokens:**" in proc.stdout
    assert "\n\n---\n" in proc.stdout  # doc separator
    # no JSON on stdout (pure markdown for the agent)
    assert not proc.stdout.lstrip().startswith("{")
    # stderr: one trim footer per task + redaction caveat
    assert proc.stderr.count("ane-harness: evidence") == 2
    assert "redaction does not guarantee" in proc.stderr


def test_proxy_indexes_repo_when_given(tmp_path, monkeypatch):
    _cfg_env(tmp_path, monkeypatch)
    tasks = 'Fix the discount calculation\n'
    proc = _proxy(tmp_path, tasks, "--repo", REPO, "--budget", "2000")
    assert proc.returncode == 0
    assert "<!-- ane-harness task 1/1" in proc.stdout
    assert "**Tokens:**" in proc.stdout


def test_proxy_rejects_empty_input(tmp_path, monkeypatch):
    _cfg_env(tmp_path, monkeypatch)
    proc = _proxy(tmp_path, "\n", "--repo", REPO)
    assert proc.returncode == 2
    assert "no tasks on stdin" in proc.stderr
