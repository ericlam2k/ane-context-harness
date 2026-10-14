"""Unit: human-readable run summary footers (user lens, not engineer lens).

Rules: plain words only (cut %, totals, time). No `#` prefix (renders as
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
    assert fmt_tokens(800) == "0.8k"
    assert fmt_tokens(18794) == "18.8k"
    assert fmt_tokens(211240) == "211.2k"


def test_tokens_line_single_source_of_truth():
    # markdown output and footers share this line; byte-stable contract
    m = {"selected_tokens": 800, "candidate_tokens": 5000,
         "reduction_percent": 84.0, "total_latency_ms": 5.0}
    assert tokens_line(m) == ("**Tokens:** est. 800 sent instead of est. 5000 "
                               "(84.0% cut) | **Latency:** 5.0 ms")


def test_select_footer_plain_words_only():
    m = {"candidate_tokens": 211240, "selected_tokens": 18794,
         "reduction_percent": 91.1, "total_latency_ms": 141.29,
         "required_tokens": 16794, "discretionary_tokens": 2000,
         "diagnostics": {"budget_exceeded": True}}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 61, 20000)
    assert foot == ("ane-harness: LOCAL est. pack 18.8k from est. 211.2k eligible · est. cut 91.1% · 61 chunks · 141 ms · cpu_deterministic")
    assert not foot.startswith("#")
    for jargon in ("required", "discretionary", "budget", "recall"):
        assert jargon not in foot


def test_select_footer_flags_oversize_plainly():
    # over-budget states the overage and the must-keep split, never blame
    m = {"candidate_tokens": 5000, "selected_tokens": 4800,
         "reduction_percent": 4.0, "total_latency_ms": 5.0,
         "required_tokens": 800, "discretionary_tokens": 4000,
         "diagnostics": {"context_pressure": {
             "required_tokens": 800,
             "selected_files": 3,
             "paired_test_files": 1,
             "top_files": [{"path": "src/cart.py", "tokens": 1900,
                            "required_tokens": 800,
                            "reasons": ["named_symbol"]}],
         }}}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 9, 2000)
    assert "narrow the task" not in foot
    assert "by 2.8k" in foot
    assert "0.8k must-keep + 4.0k supporting context across 3 files" in foot
    assert "including 1 paired test file" in foot
    assert "src/cart.py" not in foot
    assert "est." in foot  # footer uses estimates


def test_select_footer_flags_mandatory_overflow():
    m = {"candidate_tokens": 443247, "selected_tokens": 9803,
         "reduction_percent": 97.79, "total_latency_ms": 437.0,
         "required_tokens": 7957, "discretionary_tokens": 1846}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 33, 2000)
    assert "narrow the task" not in foot
    assert "by 7.8k" in foot
    assert foot.endswith(
        "Agent will focus next pass while preserving required evidence")
    assert "est." in foot  # footer uses estimates


def test_update_footer_batch_totals():
    foot = update_footer(45000, 8200, 81.8, 2, 12000, 4200)
    assert foot == "ane-harness: 2 tasks · LOCAL est. pack 8.2k from est. 45.0k eligible · est. cut 81.8% median"
    assert not foot.startswith("#")
