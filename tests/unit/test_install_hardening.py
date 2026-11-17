"""Hardening for `ane-harness install`.

Crash-window ordering (manifest record before file write), the concurrent-run
lock, unreferenced-backup notes in --undo, and crash containment. Hermetic
like test_install_wiring.py: everything runs under tmp_path with an isolated
home and ANE_HARNESS_STATE_DIR — the real home is never touched. Fault
injection is path-based (raise only on the _atomic_write call targeting the
victim dest; the manifest record goes through the same function and always
passes through), which is the only way to simulate "crash after the manifest
record, before/while the file write lands".
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ane_context_harness import install as install_mod
from ane_context_harness.cli import main

CMD = "/opt/bin/ane-harness"


def _home_env(tmp_path, state_dir=None):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"PATH": ""}
    if state_dir is not None:
        env["ANE_HARNESS_STATE_DIR"] = str(state_dir)
    return home, env


def _skill_dest(home, env, agent):
    return Path(install_mod.agent_specs(home, env)[agent]["markers"][0][1])


def _plugin_dest(home, env):
    return Path(install_mod.agent_specs(home, env)["opencode"]["markers"][1][1])


def _claude_path(home, env):
    return install_mod._claude_mcp_path(home, env)


def _lock_path(home, env):
    return install_mod.manifest_path(home, env).parent / install_mod.LOCK_NAME


def _write_lock(home, env, pid=99999, command="install"):
    mpath = install_mod.manifest_path(home, env)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    lock = mpath.parent / install_mod.LOCK_NAME
    lock.write_text(json.dumps({"pid": pid,
                                "timestamp": install_mod._iso_now(),
                                "command": command}),
                    encoding="utf-8")
    return lock


def _stale_mtime(lock, hours=2):
    old = datetime.now(timezone.utc).timestamp() - hours * 3600
    os.utime(lock, (old, old))


def _read_entries(home, env):
    mpath = install_mod.manifest_path(home, env)
    return json.loads(mpath.read_text(encoding="utf-8"))["entries"]


def test_created_crash_window_records_before_write(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    mpath = install_mod.manifest_path(home, env)
    first_dest = _skill_dest(home, env, "opencode")

    real_atomic = install_mod._atomic_write

    def fake_atomic(dest, data, mode=None):
        if Path(dest) == first_dest:
            raise OSError("injected dest write failure")
        return real_atomic(dest, data, mode)

    monkeypatch.setattr(install_mod, "_atomic_write", fake_atomic)

    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env, selected=["opencode", "claude"])

    assert mpath.exists()
    entries = _read_entries(home, env)
    assert len(entries) >= 1
    dests = [e["dest"] for e in entries]
    assert str(first_dest) in dests
    assert not first_dest.exists()
    for agent, targets in install_mod._targets(home, env):
        for kind, dest, src in targets:
            if Path(dest).exists():
                assert str(dest) in dests
    assert not _lock_path(home, env).exists()

    monkeypatch.setattr(install_mod, "_atomic_write", real_atomic)
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert not _skill_dest(home, env, "opencode").exists()
    assert not _skill_dest(home, env, "claude").exists()
    assert not _plugin_dest(home, env).exists()
    assert not _skill_dest(home, env, "agents").exists()
    assert not mpath.exists()
    assert any("absent" in line for line in lines)


def test_merge_crash_window_skill_restore(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    dest = _skill_dest(home, env, "opencode")
    dest.parent.mkdir(parents=True)
    original = b"foreign skill bytes"
    dest.write_bytes(original)

    real_atomic = install_mod._atomic_write

    def fake_atomic(d, data, mode=None):
        if Path(d) == dest:
            raise OSError("injected dest write failure")
        return real_atomic(d, data, mode)

    monkeypatch.setattr(install_mod, "_atomic_write", fake_atomic)

    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env, selected=["opencode"])

    assert dest.read_bytes() == original
    backups = list(dest.parent.glob("SKILL.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    entries = _read_entries(home, env)
    entry = next(e for e in entries if e["dest"] == str(dest))
    assert entry["backup_path"] == str(backups[0])

    monkeypatch.setattr(install_mod, "_atomic_write", real_atomic)
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert dest.read_bytes() == original
    assert any(line.startswith("restored:") for line in lines)


def test_mcp_merge_crash_window_restore(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = {"projects": {"foo": {"path": "/tmp/x"}}, "numStartups": 7}
    original_bytes = (json.dumps(original, indent=2) + "\n").encode("utf-8")
    path.write_bytes(original_bytes)

    real_atomic = install_mod._atomic_write

    def fake_atomic(d, data, mode=None):
        if Path(d) == path:
            raise OSError("injected claude.json write failure")
        return real_atomic(d, data, mode)

    monkeypatch.setattr(install_mod, "_atomic_write", fake_atomic)

    with pytest.raises(OSError):
        install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    assert path.read_bytes() == original_bytes
    backups = list(path.parent.glob(".claude.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_bytes
    entries = _read_entries(home, env)
    entry = next(e for e in entries if e["dest"] == str(path))
    assert entry["backup_path"] == str(backups[0])

    monkeypatch.setattr(install_mod, "_atomic_write", real_atomic)
    lines, code = install_mod.perform_undo(home=home, env=env, selected=["mcp"])
    assert code == 0
    assert path.read_bytes() == original_bytes
    assert any(line.startswith("restored:") for line in lines)


def test_fresh_lock_refuses_install(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _write_lock(home, env, command="install")
    before = lock.read_bytes()
    with pytest.raises(install_mod._LockError) as excinfo:
        install_mod.perform_install(home=home, env=env)
    assert str(lock) in str(excinfo.value)
    assert lock.read_bytes() == before
    assert not install_mod.manifest_path(home, env).exists()
    assert not _skill_dest(home, env, "claude").exists()


def test_fresh_lock_run_install_exits_2(tmp_path, monkeypatch, capsys):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _write_lock(home, env, command="install")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("ANE_HARNESS_STATE_DIR", str(tmp_path / "state"))
    args = SimpleNamespace(all=False, undo=False, dry_run=False, agent=None)
    assert install_mod.run_install(args) == 2
    err = capsys.readouterr().err.strip()
    payload = json.loads(err.splitlines()[-1])
    assert payload["ok"] is False
    assert str(lock) in payload["error"]
    assert lock.exists()


def test_stale_lock_is_taken_over(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _write_lock(home, env, pid=99999, command="install")
    _stale_mtime(lock, hours=2)
    changes = install_mod.perform_install(home=home, env=env)
    assert any(c["action"] == "created" for c in changes)
    if lock.exists():
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_lock_released_when_install_fails(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _lock_path(home, env)

    def fake_atomic(dest, data, mode=None):
        raise OSError("injected failure")

    monkeypatch.setattr(install_mod, "_atomic_write", fake_atomic)
    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env)
    assert not lock.exists()


def test_dry_run_creates_no_lock(tmp_path, monkeypatch, capsys):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD, dry_run=True)
    assert not _lock_path(home, env).exists()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("ANE_HARNESS_STATE_DIR", str(tmp_path / "state"))
    assert main(["install", "--dry-run"]) == 0
    capsys.readouterr()
    assert not list(tmp_path.rglob(install_mod.LOCK_NAME))


def test_undo_fresh_lock_refuses_stale_proceeds(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _write_lock(home, env, command="undo")
    with pytest.raises(install_mod._LockError):
        install_mod.perform_undo(home=home, env=env)
    assert lock.exists()

    _stale_mtime(lock, hours=2)
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 2
    assert any("no install manifest" in line for line in lines)
    assert not lock.exists()


def test_undo_reports_unreferenced_backup_note(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    install_mod.perform_install(home=home, env=env)
    dest = _skill_dest(home, env, "agents")
    stray = dest.parent / (dest.name + ".bak-20260101T000000Z")
    stray.write_text("stray backup", encoding="utf-8")
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert any(line == f"note: unreferenced backup file remains: {stray} "
                       "(no manifest entry; left untouched)" for line in lines)
    assert stray.read_text(encoding="utf-8") == "stray backup"


def test_undo_does_not_flag_referenced_backup(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    dest = _skill_dest(home, env, "agents")
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"foreign")
    install_mod.perform_install(home=home, env=env)
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert not any("unreferenced backup" in line for line in lines)


def test_crash_containment_walk(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    dest = _skill_dest(home, env, "opencode")
    dest.parent.mkdir(parents=True)
    original = b"foreign skill bytes"
    dest.write_bytes(original)

    real_atomic = install_mod._atomic_write

    def fake_atomic(d, data, mode=None):
        if Path(d) == dest:
            raise OSError("injected dest write failure")
        return real_atomic(d, data, mode)

    monkeypatch.setattr(install_mod, "_atomic_write", fake_atomic)
    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env, selected=["opencode"])

    roots = (home.resolve(), (tmp_path / "state").resolve())
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files
    for f in files:
        assert ".tmp-" not in f.name
        resolved = f.resolve()
        assert any(resolved == root or root in resolved.parents for root in roots)
    names = [f.name for f in files]
    assert install_mod.MANIFEST_NAME in names
    assert any(name.startswith("SKILL.md.bak-") for name in names)
    assert not _lock_path(home, env).exists()


def test_undo_still_skips_real_user_edit(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    dest = _skill_dest(home, env, "opencode")
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"original")
    install_mod.perform_install(home=home, env=env)
    dest.write_bytes(b"user edit after install")
    lines, code = install_mod.perform_undo(home=home, env=env)
    assert code == 0
    assert dest.read_bytes() == b"user edit after install"
    assert any("changed since install" in line for line in lines)
    entries = _read_entries(home, env)
    assert any(e["dest"] == str(dest) for e in entries)


def test_lock_write_failure_leaves_no_lock_and_next_install_works(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _lock_path(home, env)

    real_fdopen = os.fdopen
    state = {"calls": 0}

    def fake_fdopen(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError("disk full")
        return real_fdopen(*args, **kwargs)

    monkeypatch.setattr(os, "fdopen", fake_fdopen)
    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env)
    assert not lock.exists()

    monkeypatch.undo()
    changes = install_mod.perform_install(home=home, env=env)
    assert any(c["action"] == "created" for c in changes)
    assert _skill_dest(home, env, "opencode").exists()


def test_lock_write_midway_failure_leaves_no_lock(tmp_path, monkeypatch):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    lock = _lock_path(home, env)

    real_fdopen = os.fdopen
    state = {"calls": 0}

    class _BoomWriter:
        def __init__(self, real):
            self._real = real

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._real.close()
            return False

        def write(self, data):
            raise OSError("disk full")

    def fake_fdopen(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            return _BoomWriter(real_fdopen(*args, **kwargs))
        return real_fdopen(*args, **kwargs)

    monkeypatch.setattr(os, "fdopen", fake_fdopen)
    with pytest.raises(OSError):
        install_mod.perform_install(home=home, env=env)
    assert not lock.exists()
