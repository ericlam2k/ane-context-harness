"""Human-readable one-line run summaries for vibe-coders.

Every `select`/`update` run (CLI or MCP) returns machine JSON, but nobody
remembers flags to ask "how much context did that hand over?". These helpers
render the same numbers as a one-line footer:

    # ane-harness: est. sent 18.8k instead of est. 211.2k · est. cut 91.1% ·
    #   61 chunks · 141 ms · budget 2000 EXCEEDED (+16.8k) · cpu_deterministic

The percent is how much less we ESTIMATE we send than everything we could send —
not provider bills or cache behavior, which are the provider's layer and are
never claimed here. These are LOCAL ESTIMATES from the pinned estimator,
not provider-metered tokens. For provider-metered totals, use `ane-harness meter`.

Rules: stdout stays pure JSON (footers go to stderr on the CLI, or a
`summary` key over MCP) so parsers never break. No recall claim is ever
made here — recall needs labelled ground truth, unavailable at runtime.

Budget policy (users never touch this): the token budget governs
*discretionary* chunks only. Required-evidence (mandatory) chunks form a
floor that is always kept. When a package grows beyond the target, the
footer states the overage and the must-keep/supporting split as
consequence. It never blocks the current task or silently drops required
evidence.
"""
from __future__ import annotations

from typing import Any


def fmt_tokens(n: float | int) -> str:
    """Compact token count: 18794 -> '18.8k', 800 -> '800'."""
    n = int(n)
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def tokens_line(metrics: dict[str, Any]) -> str:
    """Canonical Tokens/Latency line.

    Single source of truth shared by the markdown output and the CLI/MCP
    footers — render here so the two can never drift apart.
    """
    return (f"**Tokens:** est. {metrics.get('selected_tokens', 0)} sent instead of "
            f"est. {metrics.get('candidate_tokens', 0)} "
            f"({metrics.get('reduction_percent', 0)}% cut) | "
            f"**Latency:** {metrics.get('total_latency_ms', 0)} ms")


def select_footer(metrics: dict[str, Any], execution: dict[str, Any] | None,
                  n_chunks: int, budget: int,
                  pinned_changed: list | None = None) -> str:
    """One-line footer for a single select run.

    User lens only: context handed over out of everything available, plus
    percent cut. Cut% is local context reduction, not bill savings —
    no jargon (required/discretionary, chunks, backend names), no `#`
    prefix (renders as a giant heading in chat UIs); those stay in the JSON
    for machines.
    """
    cand = metrics.get("candidate_tokens", 0)
    sel = metrics.get("selected_tokens", 0)
    red = metrics.get("reduction_percent", 0.0)
    lat = metrics.get("total_latency_ms", 0.0)
    line = (f"ane-harness: est. package {fmt_tokens(sel)} from est. {fmt_tokens(cand)} eligible "
            f"· est. cut {red}% in {round(lat)} ms")
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
            line += (f" — work continues; {over} over the target: {shape}. "
                     "No action needed from you; the agent will use the "
                     "context map to focus its next internal pass while "
                     "preserving required evidence")
        else:
            line += (f" — work continues; package exceeded the target by "
                     f"{over}. No action needed from you; the agent will "
                     "focus its next internal pass while preserving "
                     "required evidence")
    if pinned_changed:
        names = ", ".join(p.split("/")[-1] for p in pinned_changed[:2])
        extra = f" +{len(pinned_changed) - 2} more" if len(pinned_changed) > 2 else ""
        line += f" — pinned source updated: {names}{extra}"
    return line


def update_footer(before_total: int, after_total: int,
                  reduction_median: float, n_tasks: int,
                  budget: int, required_total: int = 0) -> str:
    """One-line footer for a batch update run (user lens: tasks + cut)."""
    return (f"ane-harness: {n_tasks} tasks · est. packaged {fmt_tokens(after_total)} "
            f"from est. {fmt_tokens(before_total)} eligible · est. cut "
            f"{reduction_median}% median")
