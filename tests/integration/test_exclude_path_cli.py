"""Integration: `select --exclude-path` end-to-end (flag to pack).

Hermetic via tmp ANE_HARNESS_CONFIG storage (same pattern as the proxy
tests): no pollution of the real ~/.ane_context_harness.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = str(ROOT / "tests/fixtures/synthetic_py_project")


def _env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["ANE_HARNESS_NO_LOAD_SENSE"] = "1"
    src = str(ROOT / "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev}" if prev else src
    if extra:
        env.update(extra)
    return env


def _run(tmp_path, monkeypatch, *args, **kw):
    storage = tmp_path / "store"
    cfg = tmp_path / "exc_cli_config.yaml"
    cfg.write_text(f"index:\n  storage_path: {storage}\n",
                   encoding="utf-8")
    monkeypatch.setenv("ANE_HARNESS_CONFIG", str(cfg))
    return subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", *args],
        capture_output=True, text=True, timeout=180,
        env=_env(), **kw)


def test_exclude_path_flag_reaches_pack(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "index", "--repo", REPO,
             "--repo-id", "exc_cli")
    assert r.returncode == 0, r.stderr
    base = _run(tmp_path, monkeypatch, "select", "--repo-id", "exc_cli",
                "--task", "Fix the incorrect discount calculation",
                "--budget", "2000")
    assert base.returncode == 0, base.stderr
    victim = json.loads(base.stdout)["evidence"][0]["path"]
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "exc_cli",
               "--task", "Fix the incorrect discount calculation",
               "--budget", "2000", "--exclude-path", victim)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert all(e["path"] != victim for e in data["evidence"])
    assert victim in data["metrics"]["diagnostics"]["excluded"]["paths"]


def test_exclude_contradiction_exits_2(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "index", "--repo", REPO,
             "--repo-id", "exc_cli2")
    assert r.returncode == 0, r.stderr
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "exc_cli2",
               "--task", "Fix the incorrect discount calculation",
               "--budget", "2000",
               "--explicit-path", "src/discount.py",
               "--exclude-path", "src/discount.py")
    assert out.returncode == 2
    assert "contradictory pin" in out.stderr
