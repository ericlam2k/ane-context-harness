"""Detection + dry-run for `ane-harness install`.

Hermetic: detection takes the base home and environment explicitly, and the
CLI-path tests monkeypatch Path.home/PATH/XDG_CONFIG_HOME at tmp_path — the
real home is never read or written.
"""
from pathlib import Path

import pytest

from ane_context_harness import install as install_mod
from ane_context_harness.cli import main


def _home_env(tmp_path, xdg=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": ""}
    if xdg is not None:
        env["XDG_CONFIG_HOME"] = str(xdg)
    return home, env


def test_all_agents_absent(tmp_path):
    home, env = _home_env(tmp_path)
    reports = install_mod.detect_agents(home=home, env=env)
    assert [r["status"] for r in reports] == ["not-found", "not-found", "not-found"]
    assert [r["agent"] for r in reports] == ["opencode", "claude", "agents"]


def test_opencode_present_unwired(tmp_path):
    home, env = _home_env(tmp_path)
    (home / ".config" / "opencode").mkdir(parents=True)
    reports = {r["agent"]: r for r in install_mod.detect_agents(home=home, env=env)}
    assert reports["opencode"]["status"] == "detected"
    assert set(reports["opencode"]["missing"]) == {"skill", "usage plugin"}
    assert reports["claude"]["status"] == "not-found"


def test_opencode_already_wired(tmp_path):
    home, env = _home_env(tmp_path)
    skill = home / ".config" / "opencode" / "skills" / "ane-harness" / "SKILL.md"
    plugin = home / ".config" / "opencode" / "plugins" / "ane-harness-usage.ts"
    skill.parent.mkdir(parents=True)
    plugin.parent.mkdir(parents=True)
    skill.write_text("skill", encoding="utf-8")
    plugin.write_text("plugin", encoding="utf-8")
    reports = {r["agent"]: r for r in install_mod.detect_agents(home=home, env=env)}
    assert reports["opencode"]["status"] == "already-wired"


def test_xdg_config_home_is_honored_for_opencode(tmp_path):
    home, env = _home_env(tmp_path, xdg=tmp_path / "xdg")
    xdg_opencode = tmp_path / "xdg" / "opencode"
    xdg_opencode.mkdir(parents=True)
    reports = {r["agent"]: r for r in install_mod.detect_agents(home=home, env=env)}
    assert reports["opencode"]["status"] == "detected"
    skill_path = next(m["path"] for m in reports["opencode"]["markers"]
                      if m["kind"] == "skill")
    assert skill_path.startswith(str(tmp_path / "xdg"))


def test_unknown_agent_exits_2():
    with pytest.raises(SystemExit) as excinfo:
        main(["install", "bogus-agent"])
    assert excinfo.value.code == 2


def test_all_flag_conflicts_with_specific_agent(capsys):
    assert main(["install", "opencode", "--all"]) == 2
    _, err = capsys.readouterr()
    assert "--all" in err


def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    home, _ = _home_env(tmp_path)
    (home / ".config" / "opencode").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert main(["install", "--dry-run"]) == 0
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert before == after
    out = capsys.readouterr().out
    assert "dry-run plan" in out
    assert str(home / ".config" / "opencode" / "skills" / "ane-harness" / "SKILL.md") in out


def test_dry_run_plan_reflects_dest_state(tmp_path):
    home, env = _home_env(tmp_path)
    plan = {b["agent"]: b for b in install_mod.dry_run_plan(home=home, env=env)}
    skill_entry = next(e for e in plan["agents"]["entries"] if e["kind"] == "skill")
    assert skill_entry["action"] == "create"

    src = install_mod.find_skill_src()  # shared with setup.py
    dest = Path(skill_entry["path"])
    dest.parent.mkdir(parents=True)
    dest.write_bytes(src.read_bytes())
    plan = {b["agent"]: b for b in install_mod.dry_run_plan(home=home, env=env)}
    skill_entry = next(e for e in plan["agents"]["entries"] if e["kind"] == "skill")
    assert skill_entry["action"] == "unchanged"

    dest.write_text("foreign file", encoding="utf-8")
    plan = {b["agent"]: b for b in install_mod.dry_run_plan(home=home, env=env)}
    skill_entry = next(e for e in plan["agents"]["entries"] if e["kind"] == "skill")
    assert skill_entry["action"] == "overwrite"
    assert "backed up" in skill_entry["detail"]
