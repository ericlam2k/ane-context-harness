"""Integration: the `ane-harness evidence verify` CLI command.

Runs the CLI entrypoint against the real fixture bundle (read-only) and locks
down the JSON shape + exit-code contract. Does not mutate the bundle.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BUNDLE = "ane-context-harness-evidence-v0.1"

# Repo root derived from this file: CLI subprocesses must run against the
# checkout under test, never a hardcoded developer path.
ROOT = Path(__file__).resolve().parents[2]


def _repo_env() -> dict:
    """Subprocess env forcing import of this checkout's src.

    The harness may be pip-installed editable from a different checkout;
    prepending this repo's src to PYTHONPATH keeps CLI subprocesses hermetic.
    """
    env = dict(os.environ)
    src = str(ROOT / "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev}" if prev else src
    return env


def test_evidence_verify_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "evidence", "verify",
         BUNDLE],
        capture_output=True, text=True, timeout=60, env=_repo_env())
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["bundle_dir"] == BUNDLE
    assert data["checked"] == 10
    assert data["missing"] == []
    assert data["changed"] == []
    assert data["unexpected"] == []
    assert data["errors"] == []


def test_evidence_verify_bad_path_exit1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "evidence", "verify",
         "/no/such/bundle"],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    data = json.loads(proc.stdout)
    assert data["ok"] is False
    assert any("manifest.json not found" in e for e in data["errors"]) or \
        "manifest.json not found" in str(data.get("errors", []))
