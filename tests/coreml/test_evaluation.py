"""Tests for Phase 3 retrieval-quality metrics (gate B) + task labelling."""
from __future__ import annotations

from src.ane_context_harness.coreml.evaluation import (
    ndcg_at_k, recall_at_k, mrr, evaluate_rerank, aggregate_quality,
    relevance_labels,
)
from src.ane_context_harness.benchmark import BenchmarkTask


class _C:
    def __init__(self, path, sym, s, e):
        self.path = path; self.symbol = sym; self.start_line = s; self.end_line = e
        self.symbol = sym


def test_recall_and_mrr_and_ndcg_basic():
    assert recall_at_k([1, 0, 0], 1) == 1.0
    assert recall_at_k([0, 1, 0], 1) == 0.0
    assert mrr([0, 1, 0]) == 0.5
    assert mrr([1, 0, 0]) == 1.0
    assert mrr([0, 0, 0]) == 0.0
    assert abs(ndcg_at_k([1, 1, 0], 2) - 1.0) < 1e-9


def test_perfect_ranking_scores_max():
    labels = [1, 1, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.6, 0.5]  # relevant ranked first
    res = _run(labels, scores)
    # recall@1 = 1 hit of 2 relevant; recall@10 = 1.0 (all relevant in top 10)
    assert res["recall_at_1"] == 0.5
    assert res["recall_at_10"] == 1.0
    assert res["ndcg_at_10"] == 1.0
    assert res["mrr"] == 1.0


def test_worst_ranking_scores_min():
    labels = [1, 1, 0, 0, 0]
    scores = [0.1, 0.0, 0.9, 0.8, 0.7]  # relevant at the bottom
    res = _run(labels, scores)
    assert res["recall_at_1"] == 0.0
    assert res["mrr"] < 0.5


def test_none_scores_rank_last():
    # model unavailable -> Nones rank last, perfect items still win
    labels = [0, 0, 1]
    scores = [None, None, None]  # no signal -> relevance order undefined but Nones last
    res = _run(labels, scores)
    assert res["recall_at_1"] in (0.0, 1.0)  # deterministic tie-break; just no crash


def test_relevance_labels_from_task():
    chunks = [_C("src/discount.py", "calculate_discount", 7, 12),
              _C("tests/test_discount.py", "test_calculate_discount", 1, 10),
              _C("src/inventory.py", "update_stock", 1, 5)]
    task = BenchmarkTask(
        task_id="t1", task="q", repository_id="r", task_language="python",
        token_budget=1000,
        required_chunks=[{"path": "src/discount.py", "symbol": "calculate_discount", "lines": [7, 12]}],
        helpful_chunks=[{"path": "docs/design.md"}],
        irrelevant_chunks=[{"path": "src/inventory.py"}],
    )
    labels = relevance_labels(chunks, task)
    assert labels == [1, 0, 0]


def _run(labels, scores):
    chunks = [type("C", (), {"path": f"f{i}", "symbol": None, "start_line": i + 1,
                             "end_line": i + 2})() for i in range(len(labels))]
    task = BenchmarkTask(task_id="t", task="q", repository_id="r",
                         task_language="py", token_budget=1000,
                         required_chunks=[{"path": c.path} for c in chunks if labels[c.start_line - 1]],
                         helpful_chunks=[], irrelevant_chunks=[])
    return evaluate_rerank(chunks, scores, task)


def test_aggregate_quality():
    items = [{"recall_at_1": 1.0, "ndcg_at_10": 0.9, "mrr": 0.8},
             {"recall_at_1": 0.6, "ndcg_at_10": 0.7, "mrr": 0.6}]
    agg = aggregate_quality(items)
    assert agg["n"] == 2
    assert abs(agg["mean_recall_at_1"] - 0.8) < 1e-9
    assert abs(agg["mean_mrr"] - 0.7) < 1e-9
