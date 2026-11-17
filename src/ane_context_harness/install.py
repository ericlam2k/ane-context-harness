"""Agent wiring for `ane-harness install`.

Detection and dry-run: detection checks exactly the agents `ane-harness
setup` wires today — OpenCode, Claude Code, and agents-compatible hosts
(~/.agents/skills) — via PATH lookup plus config-dir existence. Wiring is
additive: nothing is overwritten silently. A file that exists and differs is
backed up next to the original first, and every step is recorded in a 0600
JSON manifest at ~/.ane_context_harness/install-manifest.json, so `--undo`
restores byte-identically what the manifest records. The base home
directory, environment, and PATH lookup are injectable so tests never touch
the real home.

The manifest records every step before the file it describes is written, so
a crash never strands an installed file without a record; install/undo/
mcp-install take a short-lived lock next to the manifest to keep concurrent
runs from interleaving. `ane-harness install mcp` merges the ane-harness MCP
entry into Claude Code's strict-JSON ~/.claude.json (additive, backed up and
recorded in the manifest) and only prints the snippet for OpenCode, whose
config is JSONC-tolerant and never modified by the installer.

Wiring is stdlib-only and never makes a network call. Windows writes are
refused until the Windows paths are verified; detection and --dry-run work
everywhere.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .setup import find_skill_src

AGENT_NAMES = ("opencode", "claude", "agents")
MANIFEST_NAME = "install-manifest.json"
LOCK_NAME = "install.lock"


def _config_home(home: Path, env) -> Path:
    xdg = env.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else home / ".config"


def agent_specs(home: Path, env) -> dict:
    # Resolved absolute paths honoring XDG_CONFIG_HOME uniformly.
    config_home = _config_home(home, env)
    return {
        "opencode": {
            "label": "OpenCode",
            "presence_paths": [config_home / "opencode"],
            "which": ["opencode"],
            "markers": [
                ("skill", config_home / "opencode" / "skills" / "ane-harness" / "SKILL.md"),
                ("usage plugin", config_home / "opencode" / "plugins" / "ane-harness-usage.ts"),
            ],
        },
        "claude": {
            "label": "Claude Code",
            "presence_paths": [home / ".claude"],
            "which": ["claude"],
            "markers": [
                ("skill", home / ".claude" / "skills" / "ane-harness" / "SKILL.md"),
            ],
        },
        "agents": {
            "label": "agents-compatible hosts (~/.agents/skills)",
            "presence_paths": [home / ".agents"],
            "which": [],
            "markers": [
                ("skill", home / ".agents" / "skills" / "ane-harness" / "SKILL.md"),
            ],
        },
    }


def _default_which(env):
    path = env.get("PATH", "")
    return lambda cmd: shutil.which(cmd, path=path)


def detect_agents(home=None, env=None, which=None) -> list:
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    which = _default_which(env) if which is None else which
    specs = agent_specs(home, env)
    reports = []
    for name in AGENT_NAMES:
        spec = specs[name]
        present = (any(p.is_dir() for p in spec["presence_paths"])
                   or any(which(cmd) for cmd in spec["which"]))
        markers = [{"kind": kind, "path": str(p), "present": p.is_file()}
                   for kind, p in spec["markers"]]
        if all(m["present"] for m in markers):
            status = "already-wired"
        elif present:
            status = "detected"
        else:
            status = "not-found"
        reports.append({
            "agent": name,
            "label": spec["label"],
            "status": status,
            "presence_paths": [str(p) for p in spec["presence_paths"]],
            "markers": markers,
            "missing": [m["kind"] for m in markers if not m["present"]],
        })
    return reports


def _find_plugin_src():
    checkout = Path(__file__).resolve().parents[2]
    plugin_src = checkout / "integrations" / "opencode" / "ane-harness-usage.ts"
    if not plugin_src.exists():
        plugin_src = Path(__file__).resolve().parent / "ane-harness-usage.ts"
    return plugin_src


def _targets(home: Path, env) -> list:
    specs = agent_specs(home, env)
    skill_src = find_skill_src()
    plugin_src = _find_plugin_src()
    out = []
    for name in AGENT_NAMES:
        spec = specs[name]
        targets = [("skill", spec["markers"][0][1], skill_src)]
        if name == "opencode":
            targets.append(("usage plugin", spec["markers"][1][1], plugin_src))
        out.append((name, targets))
    return out


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _atomic_write(dest: Path, data: bytes, mode=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp-{os.getpid()}-{_utc_stamp()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666 if mode is None else mode)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if mode is not None:
        os.chmod(dest, mode)


def _backup_path(dest: Path) -> Path:
    stamp = _utc_stamp()
    backup = dest.parent / f"{dest.name}.bak-{stamp}"
    counter = 1
    while backup.exists():
        backup = dest.parent / f"{dest.name}.bak-{stamp}-{counter}"
        counter += 1
    return backup


def manifest_path(home=None, env=None) -> Path:
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    root = env.get("ANE_HARNESS_STATE_DIR")
    if root:
        return Path(root).expanduser() / MANIFEST_NAME
    return home / ".ane_context_harness" / MANIFEST_NAME


class _ManifestError(Exception):
    pass


class _LockError(Exception):
    pass


def _load_manifest_entries(path: Path) -> list:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _ManifestError(f"cannot read manifest at {path}: {exc}")
    try:
        data = json.loads(raw)
    except ValueError:
        raise _ManifestError(f"manifest at {path} is corrupt; refusing to touch anything")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise _ManifestError(f"manifest at {path} has an unexpected shape; "
                             "refusing to touch anything")
    entries = []
    for entry in data["entries"]:
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("dest"), str)
                or not isinstance(entry.get("sha256"), str)):
            raise _ManifestError(f"manifest at {path} holds a malformed entry; "
                                 "refusing to touch anything")
        entries.append(entry)
    return entries


def _write_manifest(path: Path, entries: list) -> None:
    payload = (json.dumps({"version": 1, "entries": entries}, indent=2) + "\n").encode("utf-8")
    _atomic_write(path, payload, mode=0o600)


def dry_run_plan(home=None, env=None) -> list:
    """Per-file plan of what a real install would write. No writes, ever."""
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    specs = agent_specs(home, env)
    plan = []
    for name, targets in _targets(home, env):
        spec = specs[name]
        entries = []
        for kind, dest, src in targets:
            if src is None or not Path(src).is_file():
                entries.append({"kind": kind, "path": str(dest),
                                "action": "skip",
                                "detail": "source file not found in this installation"})
                continue
            src_bytes = Path(src).read_bytes()
            if not dest.exists():
                entries.append({"kind": kind, "path": str(dest),
                                "action": "create",
                                "detail": f"source: {src}"})
            elif dest.read_bytes() == src_bytes:
                entries.append({"kind": kind, "path": str(dest),
                                "action": "unchanged",
                                "detail": "already present and identical"})
            else:
                entries.append({"kind": kind, "path": str(dest),
                                "action": "overwrite",
                                "detail": f"overwrite (backed up to {dest}.bak-<UTC timestamp>)"})
        plan.append({"agent": name, "label": spec["label"], "entries": entries})
    return plan


def _render_agent_line(report: dict) -> str:
    status = report["status"]
    if status == "not-found":
        return f"{report['agent']}: not found"
    if status == "already-wired":
        wired = ", ".join(f"{m['kind']}: {m['path']}" for m in report["markers"])
        return f"{report['agent']}: already wired ({wired})"
    config_dir = report["presence_paths"][0]
    missing = ", ".join(report["missing"]) or "none"
    return f"{report['agent']}: detected (config dir: {config_dir}; missing: {missing})"


def render_report(reports: list) -> list:
    lines = ["ane-harness install — detection report"]
    for report in reports:
        lines.append(_render_agent_line(report))
    lines.append("windows: detection and --dry-run only; writes are refused until verified")
    counts = {}
    for report in reports:
        counts[report["status"]] = counts.get(report["status"], 0) + 1
    parts = ", ".join(f"{counts.get(s, 0)} {s}" for s in ("detected", "not-found", "already-wired"))
    checked = ", ".join(report["agent"] for report in reports)
    lines.append(f"summary: checked {len(reports)} agent(s) ({checked}): {parts}")
    return lines


def render_dry_run(plan: list) -> list:
    lines = ["dry-run plan (what a real install would write; nothing was written):"]
    for block in plan:
        lines.append(f"{block['agent']}:")
        for entry in block["entries"]:
            lines.append(f"  {entry['action']}: {entry['path']} "
                         f"({entry['kind']}; {entry['detail']})")
    lines.append("dry-run only: no files were created, merged, or overwritten")
    return lines


def _windows_refused(os_name=None, sys_platform=None) -> bool:
    os_name = os.name if os_name is None else os_name
    sys_platform = sys.platform if sys_platform is None else sys_platform
    return os_name == "nt" or sys_platform == "win32"


def _manifest_entry(change: dict, timestamp: str) -> dict:
    return {
        "agent": change["agent"],
        "kind": change["kind"],
        "source": change["source"],
        "dest": change["path"],
        "action": change["action"],
        "sha256": change["sha256"],
        "backup_path": change.get("backup_path"),
        "timestamp": timestamp,
    }


def _record_change_in_manifest(mpath: Path, change: dict) -> None:
    entries = _load_manifest_entries(mpath) if mpath.exists() else []
    entries = [e for e in entries if e.get("dest") != change["path"]]
    entries.append(_manifest_entry(change, _iso_now()))
    _write_manifest(mpath, entries)


def _lock_recorded_timestamp(lock: Path) -> str:
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    ts = data.get("timestamp") if isinstance(data, dict) else None
    return ts if isinstance(ts, str) else "unknown"


@contextlib.contextmanager
def _install_lock(mpath: Path, command: str):
    lock = mpath.parent / LOCK_NAME
    mpath.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pid": os.getpid(),
                          "timestamp": _iso_now(),
                          "command": command}).encode("utf-8")

    def _acquire() -> int:
        return os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    try:
        fd = _acquire()
    except FileExistsError:
        try:
            age = datetime.now(timezone.utc).timestamp() - lock.stat().st_mtime
        except OSError:
            age = 0.0
        if age < 1800:
            recorded = _lock_recorded_timestamp(lock)
            raise _LockError(
                f"install lock at {lock} (recorded at {recorded}); "
                f"if no other ane-harness install/undo is running, "
                f"remove {lock} and retry")
        try:
            lock.unlink()
        except OSError:
            pass
        try:
            fd = _acquire()
        except FileExistsError:
            recorded = _lock_recorded_timestamp(lock)
            raise _LockError(
                f"install lock at {lock} (recorded at {recorded}); "
                f"if no other ane-harness install/undo is running, "
                f"remove {lock} and retry")
    fh = None
    try:
        fh = os.fdopen(fd, "wb")
        fh.write(payload)
        fh.close()
    except BaseException:
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
        else:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            lock.unlink()
        except OSError:
            pass
        raise
    try:
        yield lock
    finally:
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and data.get("pid") == os.getpid():
            try:
                lock.unlink()
            except OSError:
                pass


def perform_install(home=None, env=None, selected=None) -> list:
    """Wire skill/plugin files per the dry-run contract. Returns per-file
    change records (created|unchanged|backed_up|skipped). The manifest
    records every step before the file it describes is written, so a crash
    never strands an installed file without a record."""
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    mpath = manifest_path(home, env)
    with _install_lock(mpath, "install"):
        if mpath.exists():
            _load_manifest_entries(mpath)  # corrupt manifest: refuse before any write
        changes = []
        for agent, targets in _targets(home, env):
            if selected and agent not in selected:
                continue
            for kind, dest, src in targets:
                try:
                    if src is None or not Path(src).is_file():
                        changes.append({"agent": agent, "kind": kind, "path": str(dest),
                                        "action": "skipped",
                                        "source": str(src) if src else None,
                                        "detail": "source file not found in this installation"})
                        continue
                    src_bytes = Path(src).read_bytes()
                    change = {"agent": agent, "kind": kind, "path": str(dest),
                              "source": str(src), "backup_path": None}
                    if not dest.exists():
                        change.update(action="created",
                                      sha256=_sha256_bytes(src_bytes),
                                      detail=f"source: {src}")
                        _record_change_in_manifest(mpath, change)
                        _atomic_write(dest, src_bytes)
                    else:
                        dest_bytes = dest.read_bytes()
                        if dest_bytes == src_bytes:
                            change.update(action="unchanged",
                                          sha256=_sha256_bytes(dest_bytes),
                                          detail="already present and identical")
                        else:
                            backup = _backup_path(dest)
                            shutil.copy2(dest, backup)
                            change.update(action="backed_up",
                                          sha256=_sha256_bytes(src_bytes),
                                          backup_path=str(backup),
                                          detail=f"backed up to {backup}; wrote new content")
                            _record_change_in_manifest(mpath, change)
                            _atomic_write(dest, src_bytes)
                    changes.append(change)
                except OSError as exc:
                    raise OSError(f"{dest}: {exc}") from exc
        return changes


def render_changes(changes: list) -> list:
    lines = []
    counts = {}
    for change in changes:
        counts[change["action"]] = counts.get(change["action"], 0) + 1
        action = change["action"]
        if action == "backed_up":
            lines.append(f"backed-up: {change['path']} ({change['kind']}; "
                         f"backed up to {change['backup_path']}; wrote new content)")
        else:
            label = {"created": "created", "unchanged": "unchanged",
                     "skipped": "skipped"}[action]
            lines.append(f"{label}: {change['path']} ({change['kind']}; {change['detail']})")
    parts = ", ".join(f"{counts.get(a, 0)} {a.replace('_', ' ')}"
                      for a in ("created", "backed_up", "unchanged", "skipped"))
    lines.append(f"summary: {parts}")
    return lines


MCP_SERVER_NAME = "ane-harness"


def _mcp_command(env) -> str:
    found = shutil.which("ane-harness", path=(env or {}).get("PATH", ""))
    return found if found else "ane-harness"


def _claude_mcp_entry(cmd: str) -> dict:
    return {"type": "stdio", "command": cmd,
            "args": ["mcp", "--transport", "stdio"]}


def _opencode_mcp_entry(cmd: str) -> dict:
    return {"type": "local",
            "command": [cmd, "mcp", "--transport", "stdio"],
            "enabled": True}


def _claude_mcp_path(home: Path, env) -> Path:
    cfg = env.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return Path(cfg).expanduser() / ".claude.json"
    return home / ".claude.json"


def mcp_targets(home: Path, env) -> list:
    return [("claude", _claude_mcp_path(home, env)),
            ("opencode", _config_home(home, env) / "opencode" / "opencode.json")]


def _mcp_snippet(host: str, cmd: str) -> str:
    if host == "claude":
        block = {"mcpServers": {MCP_SERVER_NAME: _claude_mcp_entry(cmd)}}
    else:
        block = {"mcp": {MCP_SERVER_NAME: _opencode_mcp_entry(cmd)}}
    return json.dumps(block, indent=2)


def _claude_merge_bytes(data: dict, cmd: str) -> bytes:
    entry = _claude_mcp_entry(cmd)
    new_data = dict(data)
    servers = data.get("mcpServers")
    new_servers = dict(servers) if isinstance(servers, dict) else {}
    new_servers[MCP_SERVER_NAME] = entry
    new_data["mcpServers"] = new_servers
    return (json.dumps(new_data, indent=2) + "\n").encode("utf-8")


def perform_mcp_install(home=None, env=None, mcp_command=None, dry_run=False) -> list:
    """Wire the ane-harness MCP server. Claude Code gets a strict-JSON additive
    merge into ~/.claude.json (backed up and recorded in the manifest); OpenCode
    is never written — its config is JSONC-tolerant, so the snippet is printed
    instead. Returns per-host change records."""
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    mpath = manifest_path(home, env)
    lock_ctx = contextlib.nullcontext() if dry_run else _install_lock(mpath, "install mcp")
    with lock_ctx:
        if not dry_run and mpath.exists():
            _load_manifest_entries(mpath)
        cmd = mcp_command if mcp_command is not None else _mcp_command(env)
        claude_entry = _claude_mcp_entry(cmd)
        changes = []
        for host, path in mcp_targets(home, env):
            try:
                if host == "opencode":
                    changes.append({"agent": "mcp", "kind": "opencode mcp config",
                                    "path": str(path), "action": "print",
                                    "detail": "opencode config is JSONC-tolerant; "
                                              "never modified by the installer",
                                    "snippet": _mcp_snippet("opencode", cmd)})
                    continue
                base = {"agent": "mcp", "kind": "claude mcp config",
                        "path": str(path), "source": None, "backup_path": None}
                if not path.exists():
                    new_bytes = (json.dumps({"mcpServers": {MCP_SERVER_NAME: claude_entry}},
                                            indent=2) + "\n").encode("utf-8")
                    if dry_run:
                        changes.append({**base, "action": "would-create",
                                        "detail": "would create the file with only the "
                                                  "ane-harness MCP entry"})
                        continue
                    change = {**base, "action": "created",
                              "sha256": _sha256_bytes(new_bytes),
                              "detail": "created ~/.claude.json with only the "
                                        "ane-harness MCP entry"}
                    _record_change_in_manifest(mpath, change)
                    _atomic_write(path, new_bytes)
                    changes.append(change)
                    continue
                raw = path.read_bytes()
                snippet = _mcp_snippet("claude", cmd)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    changes.append({**base,
                                    "action": "would-skip-print" if dry_run else "skipped",
                                    "detail": "file is not strict JSON (corrupt or JSONC); "
                                              "never modified",
                                    "snippet": snippet})
                    continue
                if not isinstance(data, dict):
                    changes.append({**base,
                                    "action": "would-skip-print" if dry_run else "skipped",
                                    "detail": "top-level JSON value is not an object; "
                                              "never modified",
                                    "snippet": snippet})
                    continue
                servers = data.get("mcpServers")
                if "mcpServers" in data and not isinstance(servers, dict):
                    changes.append({**base,
                                    "action": "would-skip-print" if dry_run else "skipped",
                                    "detail": "'mcpServers' is present but not an object; "
                                              "never modified",
                                    "snippet": snippet})
                    continue
                if isinstance(servers, dict) and MCP_SERVER_NAME in servers:
                    if servers[MCP_SERVER_NAME] == claude_entry:
                        changes.append({**base, "action": "unchanged",
                                        "detail": "already present and identical"})
                        continue
                    changes.append({**base,
                                    "action": "would-skip-print" if dry_run else "skipped",
                                    "detail": "an ane-harness MCP entry already exists "
                                              "with different content; not modified",
                                    "snippet": snippet})
                    continue
                if dry_run:
                    changes.append({**base, "action": "would-merge",
                                    "detail": "would add ane-harness to mcpServers "
                                              "(backed up first)"})
                    continue
                backup = _backup_path(path)
                shutil.copy2(path, backup)
                new_bytes = _claude_merge_bytes(data, cmd)
                change = {**base, "action": "merged",
                          "sha256": _sha256_bytes(new_bytes),
                          "backup_path": str(backup),
                          "detail": f"backed up to {backup}; added ane-harness "
                                    "to mcpServers"}
                _record_change_in_manifest(mpath, change)
                _atomic_write(path, new_bytes)
                changes.append(change)
            except OSError as exc:
                raise OSError(f"{path}: {exc}") from exc
        return changes


def render_mcp_changes(changes: list) -> list:
    lines = []
    counts = {}
    for change in changes:
        action = change["action"]
        counts[action] = counts.get(action, 0) + 1
        lines.append(f"{action}: {change['path']} ({change['kind']}; "
                     f"{change['detail']})")
    for change in changes:
        snippet = change.get("snippet")
        if snippet:
            lines.extend(snippet.splitlines())
    order = ("created", "merged", "unchanged", "skipped", "print",
             "would-create", "would-merge", "would-skip-print")
    parts = ", ".join(f"{counts.get(a, 0)} {a}" for a in order if counts.get(a))
    lines.append(f"summary: {parts}")
    return lines


def run_install_mcp(args) -> int:
    if getattr(args, "undo", False):
        if _windows_refused():
            print("ane-harness install --undo: Windows wiring unverified; "
                  "nothing removed.", file=sys.stderr)
            return 2
        try:
            lines, code = perform_undo(selected=["mcp"])
        except _LockError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        for line in lines:
            print(line)
        return code
    if not getattr(args, "dry_run", False) and _windows_refused():
        print("ane-harness install: Windows wiring unverified; nothing written. "
              "Use --dry-run to preview the plan.", file=sys.stderr)
        return 2
    dry_run = bool(getattr(args, "dry_run", False))
    try:
        changes = perform_mcp_install(dry_run=dry_run)
    except _LockError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except _ManifestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except OSError as exc:
        print(json.dumps({"ok": False,
                          "error": f"write failed: {exc}; the install manifest records "
                                   "every step, including the one that failed; revert "
                                   "with 'ane-harness install --undo'"}),
              file=sys.stderr)
        return 1
    for line in render_mcp_changes(changes):
        print(line)
    return 0


def perform_undo(home=None, env=None, selected=None):
    """Revert exactly what the manifest records. Returns (lines, exit_code)."""
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    mpath = manifest_path(home, env)
    with _install_lock(mpath, "undo"):
        if not mpath.exists():
            return ([f"ane-harness install --undo: no install manifest at {mpath}; "
                     "nothing to undo"], 2)
        try:
            entries = _load_manifest_entries(mpath)
        except _ManifestError as exc:
            return ([f"ane-harness install --undo: {exc}"], 2)
        if selected:
            chosen = [e for e in entries if e.get("agent") in selected]
            if not chosen:
                return ([f"ane-harness install --undo: no manifest entries for "
                         f"{', '.join(selected)}"], 0)
        else:
            chosen = list(entries)
        lines = []
        kept = [e for e in entries if e not in chosen]
        removed = restored = skipped = 0
        for entry in reversed(chosen):
            dest = Path(entry["dest"])
            backup = entry.get("backup_path")
            current_sha = _sha256_file(dest) if dest.exists() else None
            ours = current_sha is not None and current_sha == entry["sha256"]
            if backup:
                backup_path = Path(backup)
                if backup_path.is_file():
                    if dest.exists() and not ours:
                        backup_bytes = backup_path.read_bytes()
                        if current_sha is not None and _sha256_bytes(backup_bytes) == current_sha:
                            _atomic_write(dest, backup_bytes)
                            lines.append(f"restored: {dest} (from {backup_path})")
                            restored += 1
                            continue
                        lines.append(f"skipped: {dest} (changed since install; left untouched)")
                        kept.append(entry)
                        skipped += 1
                        continue
                    _atomic_write(dest, backup_path.read_bytes())
                    lines.append(f"restored: {dest} (from {backup_path})")
                    restored += 1
                    continue
                if dest.exists():
                    lines.append(f"skipped: {dest} (backup {backup_path} is missing; "
                                 "leaving the file in place)")
                    kept.append(entry)
                    skipped += 1
                    continue
                lines.append(f"skipped: {dest} (backup {backup_path} is missing; "
                             "nothing to restore)")
                kept.append(entry)
                skipped += 1
                continue
            if not dest.exists():
                lines.append(f"absent: {dest} (already removed)")
                continue
            if not ours:
                lines.append(f"skipped: {dest} (changed since install; left untouched)")
                kept.append(entry)
                skipped += 1
                continue
            dest.unlink()
            lines.append(f"removed: {dest}")
            removed += 1
        if kept:
            _write_manifest(mpath, kept)
            lines.append(f"manifest kept at {mpath} ({len(kept)} entr{'y' if len(kept) == 1 else 'ies'} "
                         "could not be undone)")
        else:
            mpath.unlink()
            lines.append(f"manifest removed: {mpath}")
        referenced = {e.get("backup_path") for e in entries}
        seen_backups = set()
        for entry in chosen:
            dest = Path(entry["dest"])
            seen_backups.add((str(dest.parent), dest.name))
        for parent, name in sorted(seen_backups):
            parent_path = Path(parent)
            if not parent_path.is_dir():
                continue
            for bak in sorted(parent_path.glob(name + ".bak-*")):
                if str(bak) not in referenced:
                    lines.append(f"note: unreferenced backup file remains: {bak} "
                                 "(no manifest entry; left untouched)")
        if restored:
            lines.append("note: backup files (.bak-*) were kept next to the restored files")
        lines.append(f"summary: {removed} removed, {restored} restored, {skipped} skipped")
        return (lines, 0)


def run_install(args) -> int:
    if getattr(args, "all", False) and args.agent not in (None, "all"):
        print(json.dumps({"ok": False, "error":
                          "--all cannot be combined with a specific agent name"}),
              file=sys.stderr)
        return 2
    if getattr(args, "undo", False) and getattr(args, "dry_run", False):
        print(json.dumps({"ok": False, "error":
                          "--undo cannot be combined with --dry-run"}),
              file=sys.stderr)
        return 2
    if args.agent == "mcp":
        return run_install_mcp(args)
    selected = None
    if args.agent and args.agent != "all" and not getattr(args, "all", False):
        selected = [args.agent]
    if getattr(args, "undo", False):
        if _windows_refused():
            print("ane-harness install --undo: Windows wiring unverified; "
                  "nothing removed.", file=sys.stderr)
            return 2
        try:
            lines, code = perform_undo(selected=selected)
        except _LockError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        for line in lines:
            print(line)
        return code
    if not getattr(args, "dry_run", False) and _windows_refused():
        print("ane-harness install: Windows wiring unverified; nothing written. "
              "Use --dry-run to preview the plan.", file=sys.stderr)
        return 2
    reports = detect_agents()
    if selected is not None:
        reports = [r for r in reports if r["agent"] in selected]
    for line in render_report(reports):
        print(line)
    if args.dry_run:
        plan = dry_run_plan()
        if selected is not None:
            plan = [b for b in plan if b["agent"] in selected]
        for line in render_dry_run(plan):
            print(line)
        return 0
    try:
        changes = perform_install(selected=selected)
    except _LockError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except _ManifestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except OSError as exc:
        print(json.dumps({"ok": False,
                          "error": f"write failed: {exc}; the install manifest records "
                                   "every step, including the one that failed; revert "
                                   "with 'ane-harness install --undo'"}),
              file=sys.stderr)
        return 1
    for line in render_changes(changes):
        print(line)
    return 0
