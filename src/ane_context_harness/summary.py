"""Human-readable one-line run summaries for vibe-coders.

Every `select`/`update` run (CLI or MCP) returns machine JSON, but nobody
remembers flags to ask "how much did that save?". These helpers render the
same numbers as a one-line footer:

    # ane-harness: 18.8k of 211.2k tokens (91.1% saved) · 61 chunks ·
    #   141 ms · budget 2000 EXCEEDED (+16.8k) · cpu_deterministic

Rules: stdout stays pure JSON (footers go to stderr on the CLI, or a
`summary` key over MCP) so parsers never break. No recall claim is ever
made here — recall needs labelled ground truth, unavailable at runtime.
"""
from __future__ import annotations

from typing import Any


def fmt_tokens(n: float | int) -> str:
    """Compact token count: 18794 -> '18.8k', 800 -> '800'."""
    n = int(n)
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def select_footer(metrics: dict[str, Any], execution: dict[str, Any] | None,
                  n_chunks: int, budget: int) -> str:
    """One-line footer for a single select run."""
    cand = metrics.get("candidate_tokens", 0)
    sel = metrics.get("selected_tokens", 0)
    red = metrics.get("reduction_percent", 0.0)
    lat = metrics.get("total_latency_ms", 0.0)
    diag = metrics.get("diagnostics", {}) or {}
    exceeded = bool(diag.get("budget_exceeded", sel > budget))
    if exceeded:
        budget_bit = f"budget {budget} EXCEEDED (+{fmt_tokens(sel - budget)})"
    else:
        budget_bit = f"budget {budget} ok"
    backend = (execution or {}).get("reranker", "unknown")
    return (f"# ane-harness: {fmt_tokens(sel)} of {fmt_tokens(cand)} tokens "
            f"({red}% saved) · {n_chunks} chunks · {lat} ms · "
            f"{budget_bit} · {backend}")


def update_footer(before_total: int, after_total: int,
                  reduction_median: float, n_tasks: int,
                  budget: int) -> str:
    """One-line footer for a batch update run."""
    return (f"# ane-harness: {n_tasks} tasks · {fmt_tokens(after_total)} of "
            f"{fmt_tokens(before_total)} tokens "
            f"({reduction_median}% saved median) · budget {budget}")
