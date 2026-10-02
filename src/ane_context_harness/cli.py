"""CLI entry point. No shell execution of source; only local file/HTTP operations."""
from __future__ import annotations

import argparse
import json
import sys

from . import schemas
from .config import build_config
from .pipeline import Pipeline, SERVICE_VERSION
from .providers.markdown import render_markdown


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ane-harness")
    sub = parser.add_subparsers(dest="command")

    p_health = sub.add_parser("health", help="Print health/profile")
    p_index = sub.add_parser("index", help="Index a repository")
    p_index.add_argument("--repo", required=True)
    p_index.add_argument("--repo-id", default=None)
    p_index.add_argument("--force-rebuild", action="store_true")
    p_select = sub.add_parser("select", help="Select context for a task")
    p_select.add_argument("--repo-id", required=True)
    p_select.add_argument("--task", required=True)
    p_select.add_argument("--budget", type=int, default=12000)
    p_select.add_argument("--explicit-path", action="append", default=[])
    p_select.add_argument("--out", default=None)
    p_serve = sub.add_parser("serve", help="Run local HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_evidence = sub.add_parser("evidence", help="Build/verify release evidence bundle")
    evi_sub = p_evidence.add_subparsers(dest="evidence_command")
    p_evi_build = evi_sub.add_parser("build", help="Freeze an evidence bundle")
    p_evi_build.add_argument("--out", required=True, help="Bundle output directory")
    p_evi_build.add_argument("--force", action="store_true")
    p_evi_verify = evi_sub.add_parser("verify", help="Verify bundle checksums")
    p_evi_verify.add_argument("bundle", help="Bundle directory")

    args = parser.parse_args(argv)
    cfg = build_config()
    pipe = Pipeline(cfg)

    if args.command == "health":
        h = pipe.health()
        print(json.dumps({
            "status": h.status,
            "platform": h.platform,
            "compute_mode": h.compute_mode,
            "behavioral_profile": h.behavioral_profile,
            "service_version": SERVICE_VERSION,
        }, indent=2))
        return 0
    if args.command == "index":
        resp = pipe.register_repository(args.repo, args.repo_id, args.force_rebuild)
        print(json.dumps({
            "repository_id": resp.repository_id,
            "files_indexed": resp.files_indexed,
            "chunks_indexed": resp.chunks_indexed,
            "files_skipped": resp.files_skipped,
            "duration_ms": resp.duration_ms,
            "incremental": resp.incremental,
        }, indent=2))
        return 0
    if args.command == "select":
        req = schemas.SelectRequest(
            repository_id=args.repo_id,
            task=args.task,
            token_budget=args.budget,
            explicit_paths=args.explicit_path,
        )
        pkg = pipe.select_context(req)
        pkg.markdown = render_markdown(pkg)
        out = {
            "request_id": pkg.request_id,
            "metrics": pkg.metrics,
            "execution": pkg.execution,
            "redactions": pkg.redaction_summary,
            "evidence": [{"path": e["path"], "start_line": e["start_line"],
                          "end_line": e["end_line"], "symbol": e.get("symbol"),
                          "score": e.get("score"), "selection_reasons": e.get("selection_reasons"),
                          "content_hash": e.get("content_hash")} for e in pkg.evidence],
            "markdown_length": len(pkg.markdown),
        }
        text = json.dumps(out, indent=2, default=str)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(pkg.markdown)
            print(json.dumps({"markdown_written": args.out, "metrics": pkg.metrics}, indent=2))
        else:
            print(text)
        return 0
    if args.command == "serve":
        from .api import serve
        serve(args.host, args.port)
        return 0
    if args.command == "evidence":
        from .evidence import EvidenceError, build_bundle, verify_bundle
        if args.evidence_command == "build":
            try:
                info = build_bundle(args.out, force=args.force)
            except EvidenceError as exc:
                print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
                return 1
            print(json.dumps({"ok": True, **info}, indent=2))
            return 0
        if args.evidence_command == "verify":
            result = verify_bundle(args.bundle)
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] else 1
        p_evidence.print_help()
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
