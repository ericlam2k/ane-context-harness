"""One-command agent setup: index + skill install + smoke select.

Portable (stdlib only, no silicon/Network deps). Stdout stays pure JSON;
human footer goes to stderr like select/update.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL_SRC_CANDIDATES = ("skills/ane-harness/SKILL.md",)
SKILL_DESTS = (
    Path.home() / ".config" / "opencode" / "skills" / "ane-harness" / "SKILL.md",
    Path.home() / ".claude" / "skills" / "ane-harness" / "SKILL.md",
    Path.home() / ".agents" / "skills" / "ane-harness" / "SKILL.md",
)
SHELL_HINT = 'eval "$(ane-harness shell-init)"'


def find_skill_src() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here.parent.parent.parent, here.parent.parent]:
        for rel in SKILL_SRC_CANDIDATES:
            cand = parent / rel
            if cand.exists():
                return cand
    # editable-install fallback: cwd repo checkout
    cand = Path.cwd() / "skills" / "ane-harness" / "SKILL.md"
    return cand if cand.exists() else None


def default_repo_id(repo: str) -> str:
    name = Path(repo).resolve().name or "repo"
    safe = "".join(c.lower() if (c.isalnum() or c in ("-", "_")) else "-" for c in name)
    return safe.strip("-") or "repo"


def python_check() -> dict:
    v = sys.version_info
    return {
        "version": f"{v.major}.{v.minor}.{v.micro}",
        "ok": v >= (3, 11),
        "warn": None if v in ((3, 13), (3, 14)) and False else (
            None if (v.major, v.minor) in ((3, 11), (3, 12), (3, 13), (3, 14))
            else "unsupported: requires Python >=3.11"),
    }


def install_skills(src: Path | None, dests=None) -> list:
    installed = []
    if src is None or not src.exists():
        return installed
    for dest in (dests or SKILL_DESTS):
        try:
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            installed.append(str(dest))
        except OSError:
            continue
    return installed


def run_setup(repo: str, repo_id: str | None, budget: int = 2000,
              with_mcp: bool = False, dests=None) -> dict:
    from .config import build_config
    from .pipeline import Pipeline, SERVICE_VERSION
    from . import schemas
    from .summary import select_footer

    root = str(Path(repo).resolve())
    rid = repo_id or default_repo_id(root)
    py = python_check()
    cfg = build_config()
    pipe = Pipeline(cfg)
    health = pipe.health()
    reg = pipe.register_repository(root, rid)
    # smoke select: proves retrieval works end-to-end on this repo
    req = schemas.SelectRequest(
        repository_id=rid,
        task="smoke test: find the main entry point",
        token_budget=budget,
    )
    pkg = pipe.select_context(req)
    foot = select_footer(pkg.metrics, pkg.execution, len(pkg.evidence), budget)
    src = find_skill_src()
    installed = install_skills(src, dests)
    return {
        "ok": True,
        "python": py,
        "repository_id": rid,
        "repo": root,
        "files_indexed": reg.files_indexed,
        "chunks_indexed": reg.chunks_indexed,
        "health": {
            "status": health.status,
            "platform": health.platform,
            "compute_mode": health.compute_mode,
            "service_version": SERVICE_VERSION,
        },
        "skills_installed": installed,
        "skill_source": str(src) if src else None,
        "smoke_summary": foot,
        "smoke_metrics": {
            "candidate_tokens": pkg.metrics["candidate_tokens"],
            "selected_tokens": pkg.metrics["selected_tokens"],
            "reduction_percent": pkg.metrics["reduction_percent"],
        },
        "shell_hint": SHELL_HINT,
        "mcp_note": ("mcp extra not installed; run: pip install "
                      "'ane-context-harness[mcp]'" if with_mcp else None),
        "next": f'ane-harness prove --repo {root} --repo-id {rid}',
    }
