"""Unit: human-readable run summary footers (user lens, not engineer lens).

Rules: plain words only (saved %, totals, time). No `#` prefix (renders as
a giant heading in chat UIs), no jargon (required/discretionary, chunks,
backend names) — those stay in the JSON for machines.
"""
from __future__ import annotations

from src.ane_context_harness.summary import (
    fmt_tokens,
    select_footer,
    tokens_line,
    update_footer,
)


def test_fmt_tokens_compact():
    assert fmt_tokens(800) == "800"
    assert fmt_tokens(18794) == "18.8k"
    assert fmt_tokens(211240) == "211.2k"


def test_tokens_line_single_source_of_truth():
    # markdown output and footers share this line; byte-stable contract
    m = {"selected_tokens": 800, "candidate_tokens": 5000,
         "reduction_percent": 84.0, "total_latency_ms": 5.0}
    assert tokens_line(m) == ("**Tokens:** 800 selected of 5000 candidate "
                              "(84.0% reduction) | **Latency:** 5.0 ms")


def test_select_footer_plain_words_only():
    m = {"candidate_tokens": 211240, "selected_tokens": 18794,
         "reduction_percent": 91.1, "total_latency_ms": 141.29,
         "required_tokens": 16794, "discretionary_tokens": 2000,
         "diagnostics": {"budget_exceeded": True}}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 61, 2000)
    assert foot == ("ane-harness: saved 91.1% context (18.8k of 211.2k) in 141 ms")
    assert not foot.startswith("#")
    for jargon in ("required", "discretionary", "chunk", "cpu_deterministic",
                   "budget", "recall"):
        assert jargon not in foot


def test_select_footer_flags_oversize_plainly():
    # the one case the user is ever involved: too big means narrow the task
    m = {"candidate_tokens": 5000, "selected_tokens": 4800,
         "reduction_percent": 4.0, "total_latency_ms": 5.0,
         "required_tokens": 800, "discretionary_tokens": 4000}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 9, 2000)
    assert foot.endswith("too big, narrow the task")


def test_update_footer_batch_totals():
    foot = update_footer(45000, 8200, 81.8, 2, 12000, 4200)
    assert foot == "ane-harness: 2 tasks, saved 81.8% context median (8.2k of 45.0k)"
    assert not foot.startswith("#")
