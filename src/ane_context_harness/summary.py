"""Human-readable one-line run summaries for vibe-coders.

Every `select`/`update` run (CLI or MCP) returns machine JSON, but nobody
remembers flags to ask "how much did that save?". These helpers render the
same numbers as a one-line footer:

    # ane-harness: 18.8k of 211.2k tokens (91.1% saved) · 61 chunks ·
    #   141 ms · budget 2000 EXCEEDED (+16.8k) · cpu_deterministic

Rules: stdout stays pure JSON (footers go to stderr on the CLI, or a
`summary` key over MCP) so parsers never break. No recall claim is ever
made here — recall needs labelled ground truth, unavailable at runtime.

Budget policy (users never touch this): the token budget governs
*discretionary* chunks only. Required-evidence (mandatory) chunks form a
floor that is always kept. The footer reports the split as consequence;
the only case a user is ever involved is discretionary overrun, which
means "narrow the task" — and the footer says exactly that.
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
    return (f"**Tokens:** {metrics.get('selected_tokens', 0)} selected of "
            f"{metrics.get('candidate_tokens', 0)} candidate "
            f"({metrics.get('reduction_percent', 0)}% reduction) | "
            f"**Latency:** {metrics.get('total_latency_ms', 0)} ms")


def select_footer(metrics: dict[str, Any], execution: dict[str, Any] | None,
                  n_chunks: int, budget: int) -> str:
    """One-line footer for a single select run."""
    cand = metrics.get("candidate_tokens", 0)
    sel = metrics.get("selected_tokens", 0)
    red = metrics.get("reduction_percent", 0.0)
    lat = metrics.get("total_latency_ms", 0.0)
    req = metrics.get("required_tokens", sel)
    disc = metrics.get("discretionary_tokens", 0)
    over = disc - budget
    if over > 0:
        budget_bit = (f"discretionary {fmt_tokens(disc)} over budget "
                      f"{budget} (+{fmt_tokens(over)}) — narrow the task")
    else:
        budget_bit = f"discretionary {fmt_tokens(disc)} of {budget} budget ok"
    backend = (execution or {}).get("reranker", "unknown")
    return (f"# ane-harness: {red}% saved ({fmt_tokens(sel)} of "
            f"{fmt_tokens(cand)}) · {fmt_tokens(req)} required kept + "
            f"{budget_bit} · {n_chunks} chunks · {lat} ms · {backend}")


def update_footer(before_total: int, after_total: int,
                  reduction_median: float, n_tasks: int,
                  budget: int, required_total: int = 0) -> str:
    """One-line footer for a batch update run."""
    disc = after_total - required_total
    return (f"# ane-harness: {n_tasks} tasks · {reduction_median}% saved "
            f"median ({fmt_tokens(after_total)} of {fmt_tokens(before_total)} "
            f"· {fmt_tokens(required_total)} required kept + "
            f"{fmt_tokens(disc)} discretionary) · budget {budget}")
