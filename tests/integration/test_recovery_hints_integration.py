"""Integration: required-evidence recovery hints on the synthetic fixture.

The harness never runs the emitted search commands; the tests execute one
of them only to prove the emitted form is real on this host.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

import pytest

from ane_context_harness import schemas
from ane_context_harness.config import build_config, merge
from ane_context_harness.pipeline import Pipeline

FIXTURE = "tests/fixtures/synthetic_py_project"
TASK = "Fix the incorrect discount calculation"


def _starved_select(tmp_path, repo_name, budget=30, exclude_paths=None):
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5},
            "retention": {"ttl_seconds": 300},
            "privacy": {"never_read": ["**/.env**", "**/.aws/**",
                                       "**/runtime.secrets.json"]}}
    pipe = Pipeline(build_config(merge(base, {})))
    pipe.register_repository(FIXTURE, repo_name)
    req = schemas.SelectRequest(repository_id=repo_name, task=TASK,
                                token_budget=budget,
                                exclude_paths=exclude_paths or [])
    return pipe, pipe.select_context(req)


@pytest.mark.skipif(shutil.which("rg") is None,
                    reason="ripgrep not installed; rg-form recovery hints "
                           "cannot be exercised on this host")
def test_recovery_hints_for_budget_cut_fixture(tmp_path, monkeypatch):
    """Failure caught: a recovery block full of commands the host cannot
    run (or pointing at paths outside the repo) leaves the agent's next
    turn worse off than no hint at all. rg present: entries carry the rg
    command form and the environment state."""
    real = {"rg": shutil.which("rg"), "grep": shutil.which("grep")}
    assert real["rg"], "test host must have ripgrep for the rg-form case"
    monkeypatch.setattr(shutil, "which", lambda name: real.get(name))

    pipe, pkg = _starved_select(tmp_path, "recovery-rg")
    diag = pkg.metrics.get("diagnostics") or {}
    assert diag.get("recovery_tool") == {"rg": real["rg"], "grep": real["grep"]}
    rec = diag.get("recovery")
    assert rec, "a starved budget must cut named evidence worth a hint"
    assert rec["required_claims_total"] >= 1
    assert rec["required_claims_covered"] == 0
    assert rec["required_evidence_recall"] < 1.0
    assert len(rec["missed_claims"]) <= 5
    for entry in rec["missed_claims"]:
        assert set(entry) == {"chunk_id", "path", "symbol", "why",
                              "reasons", "command"}
        assert entry["why"] in {"budget", "capped", "dropped"}
        assert entry["command"].startswith("rg ")
        path = entry["path"]
        assert not path.startswith("/") and ".." not in path.split("/")
        fpath = os.path.join(FIXTURE, path)
        assert os.path.exists(fpath), f"hint path not in the fixture: {path}"
        m = re.fullmatch(r"rg -n '([^']+)' -- '([^']+)'", entry["command"])
        assert m, f"unparseable rg command: {entry['command']}"
        assert m.group(2) == path.replace("'", "'\\''")
        with open(fpath, encoding="utf-8") as fh:
            content = fh.read()
        for term in m.group(1).split("|"):
            assert term in content, f"identifier {term!r} not present in {path}"

    req_small = schemas.SelectRequest(repository_id="recovery-rg", task=TASK,
                                      token_budget=2000, explicit_paths=[])
    pkg_wide = pipe.select_context(req_small)
    wide_diag = pkg_wide.metrics.get("diagnostics") or {}
    assert "recovery" not in wide_diag
    assert "recovery_tool" not in wide_diag


def test_recovery_hints_grep_fallback_runs_against_fixture(tmp_path, monkeypatch):
    """Failure caught: shipping a grep fallback command that no host can
    actually run (wrong escaping, wrong flag) — the agent would paste a
    dead command into its recovery turn. The emitted command is executed
    for real against the fixture here."""
    real_grep = shutil.which("grep")
    assert real_grep, "test host must have grep for the fallback case"
    monkeypatch.setattr(shutil, "which",
                        lambda name: None if name == "rg" else real_grep)

    _pipe, pkg = _starved_select(tmp_path, "recovery-grep")
    diag = pkg.metrics.get("diagnostics") or {}
    assert diag.get("recovery_tool") == {"rg": None, "grep": real_grep}
    rec = diag.get("recovery")
    assert rec and rec["missed_claims"]
    for entry in rec["missed_claims"]:
        assert entry["command"].startswith("grep -nE ")
        m = re.fullmatch(r"grep -nE '([^']+)' -- '([^']+)'", entry["command"])
        assert m, f"unparseable grep fallback command: {entry['command']}"
        assert m.group(2) == entry["path"].replace("'", "'\\''")
        proc = subprocess.run(shlex.split(entry["command"]),
                              cwd=FIXTURE, capture_output=True, text=True)
        assert proc.returncode == 0, (
            f"grep fallback failed on {entry['path']}: {proc.stderr}")
        matches = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert matches, f"grep fallback found nothing in {entry['path']}"
        for term in m.group(1).split("|"):
            assert any(term in ln for ln in matches), (
                f"identifier {term!r} not reported by the emitted command")


def test_recovery_hints_no_search_tool_no_fabricated_command(tmp_path, monkeypatch):
    """Failure caught: the host has neither ripgrep nor grep, and the block
    still emits a plausible-looking command the agent cannot run — worse
    than none. Entries must carry an empty command and the diagnostics
    must show both tools missing."""
    monkeypatch.setattr(shutil, "which", lambda name: None)

    _pipe, pkg = _starved_select(tmp_path, "recovery-none")
    diag = pkg.metrics.get("diagnostics") or {}
    assert diag.get("recovery_tool") == {"rg": None, "grep": None}
    rec = diag.get("recovery")
    assert rec and rec["missed_claims"]
    for entry in rec["missed_claims"]:
        assert entry["command"] == "", (
            "no tool on PATH — command must not be fabricated")


def test_recovery_hints_excluded_path_never_pointed_at(tmp_path):
    """Failure caught: the recovery block points the agent at a file the
    caller explicitly excluded — smuggling it back through the side door."""
    _pipe, pkg = _starved_select(tmp_path, "recovery-excluded",
                                 budget=30,
                                 exclude_paths=["src/discount.py"])
    diag = pkg.metrics.get("diagnostics") or {}
    # Every named claim lives on the excluded path; once no hint can point
    # there, the block must not survive with zero entries either.
    assert "recovery" not in diag
    assert diag["excluded"]["chunks_dropped"] >= 0
