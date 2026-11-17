"""Wiring + undo for `ane-harness install`.

Hermetic: every entry point takes the base home and environment
explicitly; CLI-path tests monkeypatch Path.home/PATH/XDG_CONFIG_HOME at
tmp_path — the real home is never read or written. Byte-identity and
sha256 assertions, not mock-call assertions.
"""
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from ane_context_harness import install as install_mod
from ane_context_harness.cli import main


def _home_env(tmp_path, xdg=None, state_dir=None):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"PATH": ""}
    if xdg is not None:
        env["XDG_CONFIG_HOME"] = str(xdg)
    if state_dir is not None:
        env["ANE_HARNESS_STATE_DIR"] = str(state_dir)
    return home, env


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_dest(home: Path, env, agent: str) -> Path:
    return Path(install_mod.agent_specs(home, env)[agent]["markers"][0][1])


def _plugin_dest(home: Path, env) -> Path:
    return Path(install_mod.agent_specs(home, env)["opencode"]["markers"][1][1])


def _read_manifest(home: Path, env):
    path = install_mod.manifest_path(home, env)
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_install_creates_files_and_manifest(tmp_path):
    home, env = _home_env(tmp_path)
    changes = install_mod.perform_install(home=home, env=env)
    actions = {c["path"]: c["action"] for c in changes}
    assert actions[str(_skill_dest(home, env, "opencode"))] == "created"
    assert actions[str(_skill_dest(home, env, "claude"))] == "created"
    assert actions[str(_skill_dest(home, env, "agents"))] == "created"
    assert actions[str(_plugin_dest(home, env))] == "created"

    skill_src = install_mod.find_skill_src()
    for dest in (_skill_dest(home, env, "opencode"),
                 _skill_dest(home, env, "claude"),
                 _skill_dest(home, env, "agents")):
        assert dest.read_bytes() == skill_src.read_bytes()

    mpath, manifest = _read_manifest(home, env)
    assert stat.S_IMODE(mpath.stat().st_mode) == 0o600
    entries = manifest["entries"]
    assert len(entries) == 4
    for entry in entries:
        assert entry["action"] == "created"
        assert entry["backup_path"] is None
        assert entry["sha256"] == _sha(Path(entry["dest"]))
        assert entry["source"]
        assert entry["timestamp"]


def test_second_install_is_unchanged_and_manifest_stable(tmp_path):
    home, env = _home_env(tmp_path)
    install_mod.perform_install(home=home, env=env)
    mpath = install_mod.manifest_path(home, env)
    before = mpath.read_bytes()
    changes = install_mod.perform_install(home=home, env=env)
    assert {c["action"] for c in changes} == {"unchanged"}
    assert mpath.read_bytes() == before


def test_differing_file_is_backed_up_then_written(tmp_path):
    home, env = _home_env(tmp_path)
    dest = _skill_dest(home, env, "opencode")
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"foreign skill bytes")
    changes = install_mod.perform_install(home=home, env=env)
    change = next(c for c in changes if c["path"] == str(dest))
    assert change["action"] == "backed_up"
    assert dest.read_bytes() == install_mod.find_skill_src().read_bytes()

    backups = list(dest.parent.glob("SKILL.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"foreign skill bytes"
    assert change["backup_path"] == str(backups[0])

    _, manifest = _read_manifest(home, env)
    entry = next(e for e in manifest["entries"] if e["dest"] == str(dest))
    assert entry["backup_path"] == str(backups[0])
    assert entry["sha256"] == _sha(dest)

    rendered = install_mod.render_changes(changes)
    assert any(str(backups[0]) in line for line in rendered)


def test_undo_removes_created_files(tmp_path):
    home, env = _home_env(tmp_path)
    install_mod.perform_install(home=home, env=env)
    foreign = home / ".config" / "opencode" / "untouched.txt"
    foreign.write_text("keep me", encoding="utf-8")
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert not _skill_dest(home, env, "opencode").exists()
    assert not _skill_dest(home, env, "claude").exists()
    assert not _skill_dest(home, env, "agents").exists()
    assert not _plugin_dest(home, env).exists()
    assert not install_mod.manifest_path(home, env).exists()
    assert foreign.read_text(encoding="utf-8") == "keep me"
    assert any(line.startswith("removed:") for line in lines)


def test_undo_restores_from_backup(tmp_path):
    home, env = _home_env(tmp_path)
    dest = _skill_dest(home, env, "claude")
    dest.parent.mkdir(parents=True)
    foreign_bytes = b"foreign claude skill"
    dest.write_bytes(foreign_bytes)
    install_mod.perform_install(home=home, env=env)
    assert dest.read_bytes() != foreign_bytes
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert dest.read_bytes() == foreign_bytes
    assert not install_mod.manifest_path(home, env).exists()
    assert any(line.startswith("restored:") for line in lines)


def test_undo_skips_files_changed_after_install(tmp_path):
    home, env = _home_env(tmp_path)
    install_mod.perform_install(home=home, env=env)
    dest = _skill_dest(home, env, "agents")
    dest.write_bytes(dest.read_bytes() + b"\nuser edit")
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert dest.read_bytes().endswith(b"\nuser edit")
    _, manifest = _read_manifest(home, env)
    assert any(e["dest"] == str(dest) for e in manifest["entries"])
    assert any("skipped" in line for line in lines)


def test_undo_ignores_foreign_files_and_backups(tmp_path):
    home, env = _home_env(tmp_path)
    install_mod.perform_install(home=home, env=env)
    plugin = _plugin_dest(home, env)
    foreign_bak = plugin.parent / "ane-harness-usage.ts.bak-19990101T000000Z"
    foreign_bak.write_text("not ours", encoding="utf-8")
    foreign = plugin.parent / "other-plugin.ts"
    foreign.write_text("other", encoding="utf-8")
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert foreign_bak.read_text(encoding="utf-8") == "not ours"
    assert foreign.read_text(encoding="utf-8") == "other"


def test_undo_without_manifest_exits_2(tmp_path):
    home, env = _home_env(tmp_path)
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 2
    assert any("no install manifest" in line for line in lines)


def test_corrupt_manifest_refuses_install_and_undo(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    mpath = install_mod.manifest_path(home, env)
    mpath.parent.mkdir(parents=True)
    mpath.write_text("not json", encoding="utf-8")
    with pytest.raises(install_mod._ManifestError):
        install_mod.perform_install(home=home, env=env)
    assert not _skill_dest(home, env, "claude").exists()
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 2
    assert any("corrupt" in line or "refusing" in line for line in lines)


def test_manifest_keeps_foreign_entries_and_updates_in_place(tmp_path):
    home, env = _home_env(tmp_path)
    mpath = install_mod.manifest_path(home, env)
    mpath.parent.mkdir(parents=True)
    foreign = {"agent": "other", "kind": "thing", "source": "s",
               "dest": str(home / "foreign"), "action": "created",
               "sha256": "0" * 64, "backup_path": None,
               "timestamp": "2020-01-01T00:00:00Z"}
    dest = _skill_dest(home, env, "claude")
    stale = {"agent": "claude", "kind": "skill", "source": "s",
             "dest": str(dest), "action": "created", "sha256": "1" * 64,
             "backup_path": None, "timestamp": "2020-01-01T00:00:00Z"}
    mpath.write_text(json.dumps({"version": 1, "entries": [foreign, stale]}),
                     encoding="utf-8")
    install_mod.perform_install(home=home, env=env)
    _, manifest = _read_manifest(home, env)
    dests = [e["dest"] for e in manifest["entries"]]
    assert str(home / "foreign") in dests
    assert dests.count(str(dest)) == 1
    entry = next(e for e in manifest["entries"] if e["dest"] == str(dest))
    assert entry["sha256"] == _sha(dest)


def test_state_dir_override_and_default_path(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    assert install_mod.manifest_path(home, env) == tmp_path / "state" / "install-manifest.json"
    install_mod.perform_install(home=home, env=env)
    assert (tmp_path / "state" / "install-manifest.json").is_file()

    home2, env2 = _home_env(tmp_path / "second")
    assert install_mod.manifest_path(home2, env2) == home2 / ".ane_context_harness" / "install-manifest.json"


def test_windows_branch_refused(tmp_path):
    assert install_mod._windows_refused(os_name="nt") is True
    assert install_mod._windows_refused(sys_platform="win32") is True
    assert install_mod._windows_refused(os_name="posix", sys_platform="darwin") is False


def test_windows_write_modes_exit_2_and_write_nothing(tmp_path, monkeypatch, capsys):
    home, _ = _home_env(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("ANE_HARNESS_STATE_DIR", raising=False)
    monkeypatch.setattr(install_mod, "_windows_refused", lambda *a, **k: True)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert main(["install"]) == 2
    assert main(["install", "--undo"]) == 2
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert before == after
    err = capsys.readouterr().err
    assert "Windows wiring unverified" in err


def test_cli_install_then_undo_roundtrip(tmp_path, monkeypatch, capsys):
    home, _ = _home_env(tmp_path, state_dir=tmp_path / "state")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("ANE_HARNESS_STATE_DIR", str(tmp_path / "state"))
    assert main(["install"]) == 0
    out = capsys.readouterr().out
    assert "created:" in out
    assert main(["install"]) == 0
    out = capsys.readouterr().out
    assert "unchanged:" in out
    assert "created:" not in out
    assert main(["install", "--undo"]) == 0
    out = capsys.readouterr().out
    assert "summary:" in out
    assert not install_mod.manifest_path(home=Path(home),
                                         env={"ANE_HARNESS_STATE_DIR": str(tmp_path / "state")}).exists()
    assert main(["install", "--undo"]) == 2


def test_undo_cannot_combine_with_dry_run(capsys):
    assert main(["install", "--undo", "--dry-run"]) == 2
    _, err = capsys.readouterr()
    assert "--undo" in err
