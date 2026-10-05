"""Adoption gates: setup + prove subcommands (portable, deterministic-only)."""
import json
import os

import pytest

from ane_context_harness.cli import main
from ane_context_harness.setup import default_repo_id, install_skills
from ane_context_harness.prove import (
    CANNED_TASKS, DOC_TASKS, PY_TASKS, TS_TASKS, canned_tasks_for,
    detect_repo_kind, load_tasks,
)

FIXTURE = "tests/fixtures/synthetic_py_project"


def _run(argv):
    # main() prints JSON to stdout; capture via capsys in tests below.
    return main(argv)


def test_default_repo_id_sanitizes(tmp_path):
    assert default_repo_id(".") != ""
    assert "/" not in default_repo_id("/a/b/c")


def test_install_skills_copies(tmp_path):
    src = tmp_path / "SKILL.md"
    src.write_text("skill", encoding="utf-8")
    dest = tmp_path / "skills" / "SKILL.md"
    out = install_skills(src, [dest])
    assert out == [str(dest)]
    assert dest.read_text(encoding="utf-8") == "skill"


def test_install_skills_missing_src_returns_empty(tmp_path):
    assert install_skills(tmp_path / "nope.md", [tmp_path / "x.md"]) == []


def test_load_tasks_canned_and_file(tmp_path):
    assert load_tasks(None) == list(CANNED_TASKS)
    f = tmp_path / "t.jsonl"
    f.write_text('{"task": "a"}\nbare b\n\n', encoding="utf-8")
    assert load_tasks(str(f)) == ["a", "bare b"]
    empty = tmp_path / "e.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert load_tasks(str(empty)) == list(CANNED_TASKS)


def test_setup_subcommand_json_stdout(capsys, tmp_path):
    rc = _run(["setup", "--repo", FIXTURE, "--repo-id", "ut-setup",
               "--no-skill", "--no-shell-init"])
    assert rc == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["ok"] is True
    assert data["repository_id"] == "ut-setup"
    assert data["chunks_indexed"] >= 1  # total, stable across incremental runs
    assert "smoke_summary" in data
    assert data["smoke_summary"].startswith("ane-harness: sent")
    assert "shell_hint" not in data  # --no-shell-init hides it
    assert "ane-harness: sent" in err  # footer to stderr


def test_canned_tasks_per_repo_kind():
    assert detect_repo_kind("tests/fixtures/synthetic_py_project") == "python"
    assert canned_tasks_for("tests/fixtures/synthetic_py_project") == list(PY_TASKS)
    assert detect_repo_kind("tests/fixtures/synthetic_ts_project") == "typescript"
    assert canned_tasks_for("tests/fixtures/synthetic_ts_project") == list(TS_TASKS)
    assert detect_repo_kind("tests/fixtures/synthetic_hard_project") == "docs-mixed"
    assert canned_tasks_for("tests/fixtures/synthetic_hard_project") == list(DOC_TASKS)
    # --tasks-file still wins tested below; empty repo falls back to generic
    assert load_tasks(None, "tests/fixtures/synthetic_py_project") == list(PY_TASKS)


def test_prove_subcommand_unlabelled(capsys, tmp_path):
    rc = _run(["prove", "--repo", FIXTURE, "--repo-id", "ut-prove"])
    assert rc == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["tasks"] == 5
    assert data["task_kind"] == "python"
    assert data["per_task"][0]["task"] == PY_TASKS[0]
    assert data["recall"] == "not_applicable"
    assert data["labelled"] is False
    assert data["reduction_percent_median"] >= 0.0
    assert len(data["per_task"]) == data["tasks"]
    assert data["summary"].startswith("ane-harness:")
    assert "ane-harness:" in err


def test_prove_tasks_file_and_out(capsys, tmp_path):
    tf = tmp_path / "tasks.jsonl"
    tf.write_text('{"task": "find discount logic"}\nsku lookup\n',
                  encoding="utf-8")
    outdir = tmp_path / "rep"
    rc = _run(["prove", "--repo", FIXTURE, "--repo-id", "ut-prove2",
               "--tasks-file", str(tf), "--out", str(outdir), "--quiet"])
    assert rc == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["tasks"] == 2
    assert (outdir / "prove.json").exists()
    assert (outdir / "prove.md").exists()
    assert "not_applicable" in (outdir / "prove.md").read_text(
        encoding="utf-8")
