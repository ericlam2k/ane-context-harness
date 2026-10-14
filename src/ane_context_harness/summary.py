"""Human-readable one-line run summaries for vibe-coders.

Every `select`/`update` run (CLI or MCP) returns machine JSON, but nobody
remembers flags to ask "how much context did that hand over?". These helpers
render the same numbers as a one-line footer:

    # ane-harness: LOCAL est. package 18.8k from est. 211.2k eligible · est. cut 91.1% ·
    #   61 chunks · 141 ms · budget 2000 EXCEEDED (+16.8k) · cpu_deterministic

These are LOCAL ESTIMATES from the pinned estimator over indexed content —
NOT provider-metered tokens. The selector trims eligible chunks to a pack;
the TUI then adds system prompt, history, tools. Provider-metered savings
require the `ane-harness meter` command (A/B through the proxy).

Rules: stdout stays pure JSON (footers go to stderr on the CLI, or a
`summary` key over MCP) so parsers never break. No recall claim is ever
made here — recall needs labelled ground truth, unavailable at runtime.
"""
from __future__ import annotations

from typing import Any


def fmt_tokens(n: float | int) -> str:
    """Token count in thousands: 18794 -> '18.8k', 800 -> '0.8k'."""
    return f"{n / 1000:.1f}k"


def tokens_line(metrics: dict[str, Any], include_latency: bool = True) -> str:
    """Canonical Tokens/Latency line.

    Single source of truth shared by the markdown output and the CLI/MCP
    footers — render here so the two can never drift apart.

    include_latency=False renders the KV-safe variant (counts only): per-call
    latency digits would break provider prefix-cache hits, so serialized
    prompt bodies must never contain them.
    """
    line = (f"**Tokens:** est. {metrics.get('selected_tokens', 0)} sent instead of "
            f"est. {metrics.get('candidate_tokens', 0)} "
            f"({metrics.get('reduction_percent', 0)}% cut)")
    if include_latency:
        line += f" | **Latency:** {metrics.get('total_latency_ms', 0)} ms"
    return line


def select_footer(metrics: dict[str, Any], execution: dict[str, Any] | None,
                  n_chunks: int, budget: int,
                  pinned_changed: list | None = None) -> str:
    """One-line footer for a single select run.

    LOCAL ESTIMATES ONLY — not provider-metered. The selector trims eligible
    chunks → pack. The TUI then adds system prompt, history, tools.
    Provider prompt_tokens = aneharness pack + system + history + tools.
    Real savings = provider prompt_tokens (with harness) ÷ provider prompt_tokens
    (without harness = full eligible + system). Use `ane-harness meter` for
    provider-metered A/B.
    """
    cand = metrics.get("candidate_tokens", 0)
    sel = metrics.get("selected_tokens", 0)
    red = metrics.get("reduction_percent", 0.0)
    lat = metrics.get("total_latency_ms", 0.0)
    reranker = execution.get("reranker", "?") if execution else "?"
    line = (f"ane-harness: LOCAL est. pack {fmt_tokens(sel)} from est. {fmt_tokens(cand)} eligible "
            f"· est. cut {red}% · {n_chunks} chunks · {round(lat)} ms · {reranker}")
    if sel - budget > 0:
        over = fmt_tokens(sel - budget)
        pressure = (metrics.get("diagnostics", {}) or {}).get(
            "context_pressure", {}) or {}
        required = pressure.get("required_tokens",
                                metrics.get("required_tokens", 0))
        top = (pressure.get("top_files") or [])[:1]
        if top:
            supporting = max(0, sel - required)
            files = pressure.get("selected_files", 0)
            paired_tests = pressure.get("paired_test_files", 0)
            shape = (f"{fmt_tokens(required)} must-keep + "
                     f"{fmt_tokens(supporting)} supporting context")
            if files:
                shape += f" across {files} files"
            if paired_tests:
                label = "file" if paired_tests == 1 else "files"
                shape += f", including {paired_tests} paired test {label}"
            line += (f" — over target by {over}: {shape}. "
                     "Agent will focus next pass while preserving required evidence")
        else:
            line += (f" — over target by {over}. "
                     "Agent will focus next pass while preserving required evidence")
    if pinned_changed:
        names = ", ".join(p.split("/")[-1] for p in pinned_changed[:2])
        extra = f" +{len(pinned_changed) - 2} more" if len(pinned_changed) > 2 else ""
        line += f" — pinned source updated: {names}{extra}"
    return line


def update_footer(before_total: int, after_total: int,
                  reduction_median: float, n_tasks: int,
                  budget: int, required_total: int = 0) -> str:
    """One-line footer for a batch update run.

    LOCAL ESTIMATES ONLY. Real provider savings need `ane-harness meter`.
    """
    return (f"ane-harness: {n_tasks} tasks · LOCAL est. pack {fmt_tokens(after_total)} "
            f"from est. {fmt_tokens(before_total)} eligible · est. cut "
            f"{reduction_median}% median")
