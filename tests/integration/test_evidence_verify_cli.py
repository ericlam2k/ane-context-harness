"""Integration: the `ane-harness evidence verify` CLI command.

Runs the CLI entrypoint against the real fixture bundle (read-only) and locks
down the JSON shape + exit-code contract. Does not mutate the bundle.
"""
from __future__ import annotations

import json
import subprocess
import sys

BUNDLE = "ane-context-harness-evidence-v0.1"


def test_evidence_verify_ok(tmp_path, monkeypatch):
    monkeypatch.chdir("/Users/quanglam/Documents/ANEharness")
    proc = subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", "evidence", "verify",
         BUNDLE],
        capture_output=True, text=True, timeout=60)
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
