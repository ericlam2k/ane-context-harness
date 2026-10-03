"""CLI entry point. No shell execution of source; only local file/HTTP operations."""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from pathlib import Path

from . import schemas
from .config import build_config
from .pipeline import Pipeline, SERVICE_VERSION
from .providers.markdown import render_markdown
from .summary import fmt_tokens, select_footer, update_footer
from . import usage as usage_log


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
    p_select.add_argument("--full", action="store_true",
                          help="Baseline mode: pack the whole repo, no trimming; "
                               "for with/without comparison of results")
    p_select.add_argument("--quiet", action="store_true",
                          help="Suppress the human-readable stderr summary footer")
    p_serve = sub.add_parser("serve", help="Run local HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_update = sub.add_parser(
        "update", help="Select context for a batch of tasks and log "
                       "before/after token budgets (local; no network).")
    p_update.add_argument("--repo-id", required=True)
    p_update.add_argument("--budget", type=int, default=12000)
    p_update.add_argument("--tasks-file", default=None,
                          help="JSONL file (one {\"task\": \"...\"} or task string per line); "
                               "defaults to stdin")
    p_update.add_argument("--log", default=None,
                          help="Optional path to append per-task JSONL log to")
    p_update.add_argument("--quiet", action="store_true",
                          help="Suppress the human-readable stderr summary footer")
    p_evidence = sub.add_parser("evidence", help="Verify a release evidence bundle")
    evi_sub = p_evidence.add_subparsers(dest="evidence_command")
    p_evi_verify = evi_sub.add_parser("verify", help="Verify bundle checksums")
    p_evi_verify.add_argument("bundle", help="Bundle directory")
    p_mcp = sub.add_parser(
        "mcp", help="Serve ane-harness over MCP (optional; requires "
                    "the 'mcp' extra: pip install 'ane-context-harness[mcp]')")
    p_mcp.add_argument("--transport", default="stdio",
                       choices=["stdio", "sse"], help="MCP transport")
    p_session = sub.add_parser(
        "daily", aliases=["session"],
        help="Show saved-tokens daily totals from the local usage ledger")
    p_session.add_argument("--brief", action="store_true",
                           help="One line, or nothing when no runs yet (for shell-exit hooks)")
    sub.add_parser("shell-init", help="Print shell snippet: daily savings on shell exit; "
                                      "opt in with eval \"$(ane-harness shell-init)\"")

    args = parser.parse_args(argv)
    if args.command == "shell-init":
        print(usage_log.SHELL_INIT_SNIPPET, end="")
        return 0
    if args.command in ("daily", "session"):
        today = usage_log.summarize()
        if args.brief:
            if today["runs"] == 0:
                return 0
            print(usage_log.format_session(today))
            return 0
        print(usage_log.format_session(today))
        print(usage_log.format_session(usage_log.summarize_all(), "all time"))
        return 0
    if args.command == "mcp":
        try:
            import mcp  # noqa: F401
            from .mcp_server import build_server
        except ImportError:
            print(json.dumps({"ok": False, "error": (
                "mcp extra not installed; run: pip install 'ane-context-harness[mcp]'")}),
                file=sys.stderr)
            return 1
        server = build_server()
        server.run(args.transport)
        return 0

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
            options={"full_context": True} if args.full else {},
        )
        pkg = pipe.select_context(req)
        pkg.markdown = render_markdown(pkg)
        if args.full:
            foot = (f"ane-harness: full context "
                    f"({fmt_tokens(pkg.metrics['selected_tokens'])}) "
                    f"in {round(pkg.metrics.get('total_latency_ms', 0.0))} ms")
            print("# WARNING: full baseline bypasses selection AND redaction; "
                  "untrimmed content (including any indexed secrets) is included.",
                  file=sys.stderr)
        else:
            foot = select_footer(pkg.metrics, pkg.execution, len(pkg.evidence),
                                 args.budget)
        out = {
            "request_id": pkg.request_id,
            "metrics": pkg.metrics,
            "execution": pkg.execution,
            "redactions": pkg.redaction_summary,
            "summary": foot,
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
            print(json.dumps({"markdown_written": args.out, "metrics": pkg.metrics,
                              "summary": foot}, indent=2))
        else:
            print(text)
        if not args.quiet:
            print(foot, file=sys.stderr)
        if usage_log.log_enabled():
            usage_log.record("select", pkg.metrics["candidate_tokens"],
                             pkg.metrics["selected_tokens"],
                             pkg.metrics.get("total_latency_ms"))
        return 0
    if args.command == "serve":
        from .api import serve
        serve(args.host, args.port)
        return 0
    if args.command == "update":
        if args.tasks_file:
            raw_tasks = Path(args.tasks_file).read_text(encoding="utf-8").splitlines()
        else:
            raw_tasks = sys.stdin.read().splitlines()
        tasks = []
        for line in raw_tasks:
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    tasks.append(json.loads(line)["task"])
                except (json.JSONDecodeError, KeyError):
                    tasks.append(line)
            else:
                tasks.append(line)
        per_task = []
        for task in tasks:
            req = schemas.SelectRequest(
                repository_id=args.repo_id,
                task=task,
                token_budget=args.budget,
            )
            pkg = pipe.select_context(req)
            m = pkg.metrics
            per_task.append({
                "task": task,
                "candidate_tokens": m["candidate_tokens"],
                "selected_tokens": m["selected_tokens"],
                "tokens_removed": m["tokens_removed"],
                "reduction_percent": m["reduction_percent"],
                "required_tokens": m.get("required_tokens", 0),
                "discretionary_tokens": m.get("discretionary_tokens", 0),
            })
        if args.log:
            stamp = _time.strftime("%Y%m%d-%H%M%S")
            log_path = Path(args.log)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                for row in per_task:
                    f.write(json.dumps(row) + "\n")
        reductions = [r["reduction_percent"] for r in per_task]
        summary = {
            "repo_id": args.repo_id,
            "budget": args.budget,
            "tasks": len(per_task),
            "before_tokens_total": sum(r["candidate_tokens"] for r in per_task),
            "after_tokens_total": sum(r["selected_tokens"] for r in per_task),
            "tokens_removed_total": sum(r["tokens_removed"] for r in per_task),
            "required_tokens_total": sum(r["required_tokens"] for r in per_task),
            "discretionary_tokens_total": sum(r["discretionary_tokens"] for r in per_task),
            "reduction_percent_median": round(sorted(reductions)[len(reductions) // 2], 2) if reductions else 0.0,
            "per_task": per_task,
        }
        summary["summary"] = update_footer(
            summary["before_tokens_total"], summary["after_tokens_total"],
            summary["reduction_percent_median"], summary["tasks"],
            args.budget, summary["required_tokens_total"])
        print(json.dumps(summary, indent=2))
        print("# Note: local measurements over the given repo; redaction does not "
              "guarantee all secrets are caught.", file=sys.stderr)
        if not args.quiet:
            print(summary["summary"], file=sys.stderr)
        if usage_log.log_enabled():
            usage_log.record("update", summary["before_tokens_total"],
                             summary["after_tokens_total"],
                             tasks=summary["tasks"])
        return 0
    if args.command == "evidence":
        from .evidence import verify_bundle
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
