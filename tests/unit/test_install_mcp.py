"""MCP wiring for `ane-harness install mcp`.

Hermetic like test_install_wiring.py: every entry point takes the base home
and environment explicitly, or CLI-path tests monkeypatch Path.home and
os.environ at tmp_path — the real home is never read or written. Byte-identity
assertions, not mock-call assertions. mcp_command is passed explicitly so PATH
lookup is not exercised.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ane_context_harness import install as install_mod
from ane_context_harness.cli import main

NAME = install_mod.MCP_SERVER_NAME
CMD = "/opt/bin/ane-harness"


def _home_env(tmp_path, xdg=None, state_dir=None, claude_config_dir=None):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"PATH": ""}
    if xdg is not None:
        env["XDG_CONFIG_HOME"] = str(xdg)
    if state_dir is not None:
        env["ANE_HARNESS_STATE_DIR"] = str(state_dir)
    if claude_config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
    return home, env


def _claude_entry(cmd=CMD):
    return {"type": "stdio", "command": cmd,
            "args": ["mcp", "--transport", "stdio"]}


def _opencode_entry(cmd=CMD):
    return {"type": "local",
            "command": [cmd, "mcp", "--transport", "stdio"],
            "enabled": True}


def _claude_path(home, env):
    return install_mod._claude_mcp_path(home, env)


def _opencode_path(home, env):
    return Path(install_mod.mcp_targets(home, env)[1][1])


def _read_manifest(home, env):
    path = install_mod.manifest_path(home, env)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _merge_claude(home, env, original: dict, cmd=CMD):
    path = _claude_path(home, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(original, indent=2) + "\n").encode("utf-8"))
    return install_mod.perform_mcp_install(home=home, env=env, mcp_command=cmd)


def test_merge_preserves_foreign_keys_and_records_manifest(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    original = {"projects": {"foo": {"path": "/tmp/x", "allowed": True}},
                "numStartups": 7}
    original_bytes = (json.dumps(original, indent=2) + "\n").encode("utf-8")
    path = _claude_path(home, env)
    path.write_bytes(original_bytes)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if c["agent"] == "mcp" and "claude" in c["kind"])
    assert change["action"] == "merged"
    data = json.loads(path.read_bytes())
    assert data["projects"] == original["projects"]
    assert data["numStartups"] == 7
    assert data["mcpServers"] == {NAME: _claude_entry()}

    backups = list(path.parent.glob(".claude.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_bytes
    assert change["backup_path"] == str(backups[0])

    mpath, manifest = _read_manifest(home, env)
    entries = [e for e in manifest["entries"] if e["dest"] == str(path)]
    assert len(entries) == 1
    assert entries[0]["agent"] == "mcp"
    assert entries[0]["kind"] == "claude mcp config"
    assert entries[0]["backup_path"] == str(backups[0])
    assert entries[0]["sha256"] == install_mod._sha256_bytes(path.read_bytes())


def test_undo_round_trip_restores_original_bytes(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    original = {"projects": {"foo": {"path": "/tmp/x"}}, "numStartups": 7}
    original_bytes = (json.dumps(original, indent=2) + "\n").encode("utf-8")
    path = _claude_path(home, env)
    path.write_bytes(original_bytes)

    install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)
    assert path.read_bytes() != original_bytes

    lines, code = install_mod.perform_undo(home=home, env=env, selected=["mcp"])
    assert code == 0
    assert path.read_bytes() == original_bytes
    assert not install_mod.manifest_path(home, env).exists()
    assert any(line.startswith("restored:") for line in lines)


def test_missing_file_created_and_undo_removes_it(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    assert not path.exists()

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    expected = {"mcpServers": {NAME: _claude_entry()}}
    assert change["action"] == "created"
    assert json.loads(path.read_bytes()) == expected
    assert path.read_bytes() == (json.dumps(expected, indent=2) + "\n").encode("utf-8")

    _, manifest = _read_manifest(home, env)
    entry = next(e for e in manifest["entries"] if e["dest"] == str(path))
    assert entry["agent"] == "mcp"
    assert entry["backup_path"] is None

    lines, code = install_mod.perform_undo(home=home, env=env, selected=["mcp"])
    assert code == 0
    assert not path.exists()
    assert not install_mod.manifest_path(home, env).exists()
    assert any(line.startswith("removed:") for line in lines)


def test_identical_entry_is_unchanged_no_write_no_manifest(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    content = {"mcpServers": {NAME: _claude_entry()}}
    path.write_bytes((json.dumps(content, indent=2) + "\n").encode("utf-8"))
    before = path.read_bytes()

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "unchanged"
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".claude.json.bak-*"))
    assert not install_mod.manifest_path(home, env).exists()


def test_different_entry_is_skipped_snippet_printed(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    content = {"mcpServers": {NAME: {"type": "stdio", "command": "other",
                                     "args": ["mcp"]}}}
    path.write_bytes((json.dumps(content, indent=2) + "\n").encode("utf-8"))
    before = path.read_bytes()

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "skipped"
    assert "different content" in change["detail"]
    assert '"ane-harness"' in change["snippet"]
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".claude.json.bak-*"))
    assert not install_mod.manifest_path(home, env).exists()


def test_jsonc_file_is_never_modified(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    jsonc = b'// user comment\n{\n  "numStartups": 7,\n}\n'
    path.write_bytes(jsonc)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "skipped"
    assert '"ane-harness"' in change["snippet"]
    assert path.read_bytes() == jsonc
    assert not install_mod.manifest_path(home, env).exists()


def test_corrupt_file_is_never_modified(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    corrupt = b"{not json"
    path.write_bytes(corrupt)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "skipped"
    assert '"ane-harness"' in change["snippet"]
    assert path.read_bytes() == corrupt
    assert not install_mod.manifest_path(home, env).exists()


def test_mcp_servers_present_but_not_a_dict_is_never_modified(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    path = _claude_path(home, env)
    content = (json.dumps({"mcpServers": []}, indent=2) + "\n").encode("utf-8")
    path.write_bytes(content)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "skipped"
    assert '"ane-harness"' in change["snippet"]
    assert path.read_bytes() == content
    assert not install_mod.manifest_path(home, env).exists()


def test_opencode_always_prints_and_never_writes(tmp_path):
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state")
    oc_path = _opencode_path(home, env)
    oc_path.parent.mkdir(parents=True)
    oc_bytes = b'{"mcp": {"other": {"type": "local"}}}\n'
    oc_path.write_bytes(oc_bytes)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "opencode" in c["kind"])
    assert change["action"] == "print"
    assert '"ane-harness"' in change["snippet"]
    assert '"type": "local"' in change["snippet"]
    assert '"enabled": true' in change["snippet"]
    assert oc_path.read_bytes() == oc_bytes
    mpath = install_mod.manifest_path(home, env)
    if mpath.exists():
        entries = json.loads(mpath.read_text(encoding="utf-8"))["entries"]
        assert not any("opencode" in e["kind"] for e in entries)

    oc_path.unlink()
    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)
    change = next(c for c in changes if "opencode" in c["kind"])
    assert change["action"] == "print"
    assert not oc_path.exists()


def test_dry_run_never_writes_backs_up_or_records(tmp_path):
    fixtures = {
        "missing": None,
        "strict": {"projects": {"foo": {}}, "numStartups": 7},
        "identical": {"mcpServers": {NAME: _claude_entry()}},
        "different": {"mcpServers": {NAME: {"type": "stdio", "command": "other",
                                            "args": ["mcp"]}}},
        "servers-not-dict": {"mcpServers": []},
    }
    for label, content in fixtures.items():
        home, env = _home_env(tmp_path / label, state_dir=tmp_path / label / "state")
        path = _claude_path(home, env)
        if content is not None:
            path.write_bytes((json.dumps(content, indent=2) + "\n").encode("utf-8"))
        before = path.read_bytes() if path.exists() else None

        changes = install_mod.perform_mcp_install(home=home, env=env,
                                                  mcp_command=CMD, dry_run=True)

        after = path.read_bytes() if path.exists() else None
        assert after == before, label
        assert not list(path.parent.glob(".claude.json.bak-*")) if path.parent.exists() else True
        assert not install_mod.manifest_path(home, env).exists()
        actions = {c["action"] for c in changes if "claude" in c["kind"]}
        assert actions <= {"would-create", "would-merge", "unchanged", "would-skip-print"}

    home, env = _home_env(tmp_path / "jsonc", state_dir=tmp_path / "jsonc-state")
    path = _claude_path(home, env)
    path.write_bytes(b'// c\n{\n}\n')
    before = path.read_bytes()
    changes = install_mod.perform_mcp_install(home=home, env=env,
                                              mcp_command=CMD, dry_run=True)
    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "would-skip-print"
    assert path.read_bytes() == before


def test_claude_config_dir_env_is_honored(tmp_path):
    cfg_dir = tmp_path / "claude-cfg"
    cfg_dir.mkdir()
    home, env = _home_env(tmp_path, state_dir=tmp_path / "state",
                          claude_config_dir=cfg_dir)

    changes = install_mod.perform_mcp_install(home=home, env=env, mcp_command=CMD)

    change = next(c for c in changes if "claude" in c["kind"])
    assert change["action"] == "created"
    assert (cfg_dir / ".claude.json").exists()
    assert not (home / ".claude.json").exists()

    cfg_dir_unset = dict(env)
    cfg_dir_unset.pop("CLAUDE_CONFIG_DIR")
    path = install_mod._claude_mcp_path(home, cfg_dir_unset)
    assert path == home / ".claude.json"


def test_run_install_routes_mcp_before_skill_wiring(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    env_copy = dict(os.environ)
    env_copy.pop("CLAUDE_CONFIG_DIR", None)
    env_copy.pop("XDG_CONFIG_HOME", None)
    env_copy["ANE_HARNESS_STATE_DIR"] = str(tmp_path / "state")
    env_copy["PATH"] = ""
    monkeypatch.setattr(os, "environ", env_copy)
    monkeypatch.setattr(install_mod, "_windows_refused", lambda *a, **k: False)

    dry_args = SimpleNamespace(all=False, undo=False, dry_run=True, agent="mcp")
    assert install_mod.run_install(dry_args) == 0
    assert not (home / ".claude.json").exists()

    args = SimpleNamespace(all=False, undo=False, dry_run=False, agent="mcp")
    assert install_mod.run_install(args) == 0
    path = home / ".claude.json"
    assert path.exists()
    data = json.loads(path.read_bytes())
    assert data["mcpServers"][NAME]["args"] == ["mcp", "--transport", "stdio"]
    assert not (home / ".config" / "opencode" / "skills").exists()

    assert main(["install", "mcp", "--dry-run"]) == 0
