"""Unit: human-readable run summary footers (vibe-coder UX)."""
from __future__ import annotations

from src.ane_context_harness.summary import (
    fmt_tokens,
    select_footer,
    update_footer,
)


def test_fmt_tokens_compact():
    assert fmt_tokens(800) == "800"
    assert fmt_tokens(18794) == "18.8k"
    assert fmt_tokens(211240) == "211.2k"


def test_select_footer_reports_floor_split_not_exceeded():
    # 16.8k required always kept; only discretionary is judged vs budget.
    m = {"candidate_tokens": 211240, "selected_tokens": 18794,
         "reduction_percent": 91.1, "total_latency_ms": 141.29,
         "required_tokens": 16794, "discretionary_tokens": 2000,
         "diagnostics": {"budget_exceeded": True}}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 61, 2000)
    assert foot.startswith("# ane-harness:")
    assert "91.1% saved" in foot
    assert "16.8k required kept" in foot
    assert "budget" in foot and "over budget" not in foot
    assert "cpu_deterministic" in foot
    assert "recall" not in foot  # never claim recall without ground truth


def test_select_footer_flags_discretionary_overrun_only():
    # The one case the user is ever involved: discretionary over budget.
    m = {"candidate_tokens": 5000, "selected_tokens": 4800,
         "reduction_percent": 4.0, "total_latency_ms": 5.0,
         "required_tokens": 800, "discretionary_tokens": 4000}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 9, 2000)
    assert "over budget" in foot
    assert "narrow the task" in foot


def test_select_footer_budget_ok():
    m = {"candidate_tokens": 5000, "selected_tokens": 800,
         "reduction_percent": 84.0, "total_latency_ms": 5.0,
         "required_tokens": 200, "discretionary_tokens": 600,
         "diagnostics": {"budget_exceeded": False}}
    foot = select_footer(m, {"reranker": "cpu_deterministic"}, 4, 12000)
    assert "budget ok" in foot
    assert "over budget" not in foot


def test_update_footer_batch_totals():
    foot = update_footer(45000, 8200, 81.8, 2, 12000, 4200)
    assert foot.startswith("# ane-harness:")
    assert "2 tasks" in foot
    assert "81.8% saved median" in foot
    assert "4.2k required kept" in foot
