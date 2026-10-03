"""Metric-definition semantics: the 8 required properties + definitions map.

Each test pins one contract from the metric-definitions workstream:
1. MRR 1.0 can coexist with Recall@10 < 1.0
2. required-evidence recall 1.0 while optional relevant chunks are omitted
3. file-scoped labels match file-level chunks (symbol null)
4. symbol-scoped labels require the correct symbol
5. wrong symbol in the correct file does not satisfy a symbol-scoped label
6. duplicate chunks do not inflate recall
7. missing optional evidence never fails mandatory evidence
8. missing mandatory evidence always drives required-evidence recall below 1.0
"""
from __future__ import annotations

from types import SimpleNamespace

from ane_context_harness.benchmark import (BenchmarkTask,
                                           required_chunks_covered)
from ane_context_harness.metrics import (METRIC_DEFINITIONS,
                                             _label_rate,
                                             evaluate_rerank,
                                             mrr, ndcg_at_k,
                                             recall_at_k,
                                             relevance_labels)


def _chunk(path, start, end, symbol=None):
    return SimpleNamespace(path=path, start_line=start, end_line=end,
                           symbol=symbol, estimated_tokens=10)


def _task(required, helpful=(), irrelevant=()):
    return BenchmarkTask(
        task_id="t", task="q", repository_id="r", task_language="python",
        token_budget=1000, required_chunks=list(required),
        helpful_chunks=list(helpful), irrelevant_chunks=list(irrelevant))


def _chunks_task(chunks, required, helpful=()):
    task = _task(required, helpful)
    return chunks, task


def test_definitions_cover_the_four_reported_metrics():
    for key in ("recall_at_k", "ndcg_at_k", "mrr", "required_evidence_recall"):
        assert key in METRIC_DEFINITIONS
        assert len(METRIC_DEFINITIONS[key]) > 40


def test_1_mrr_one_with_recall10_below_one():
    """MRR looks only at the FIRST relevant; Recall@10 counts ALL relevant."""
    chunks = [f"file{i}.py" for i in range(12)]
    chunk_objs = [_chunk(p, 1, 10) for p in chunks]
    task = _task([{"path": "file0.py"}, {"path": "file11.py"}])
    scores = [0.9 - 0.01 * i for i in range(12)]  # file0 ranks first
    res = evaluate_rerank(chunk_objs, scores, task)
    assert res["mrr"] == 1.0
    assert res["recall_at_10"] < 1.0  # only 1 of 2 relevant inside top-10
    # direct formula checks
    ranked = [1] + [0] * 10 + [1]
    assert mrr(ranked) == 1.0
    assert recall_at_k(ranked, 10) == 0.5


def test_2_required_recall_one_while_optional_omitted():
    required = [{"path": "src/core.py"}]
    helpful = [{"path": "docs/guide.md"}]
    chunks = [_chunk("src/core.py", 1, 40), _chunk("docs/guide.md", 1, 20)]
    evidence = [{"path": "src/core.py", "start_line": 1}]  # optional omitted
    assert required_chunks_covered(evidence, required, chunks) == 1.0
    assert _label_rate(evidence, helpful) == 0.0  # optional not included


def test_3_file_scoped_label_matches_file_level_chunk_symbol_null():
    chunks = [_chunk("src/core.py", 1, 40, symbol=None)]
    task = _task([{"path": "src/core.py"}])  # no symbol/lines qualifier
    assert relevance_labels(chunks, task) == [1]


def test_4_symbol_scoped_label_requires_correct_symbol():
    chunks = [_chunk("src/core.py", 1, 40, symbol="settle_invoice")]
    task = _task([{"path": "src/core.py", "symbol": "settle_invoice"}])
    assert relevance_labels(chunks, task) == [1]


def test_5_wrong_symbol_in_correct_file_rejected():
    chunks = [_chunk("src/core.py", 1, 40, symbol="other_helper")]
    task = _task([{"path": "src/core.py", "symbol": "settle_invoice"}])
    assert relevance_labels(chunks, task) == [0]


def test_6_duplicate_chunks_do_not_inflate_recall():
    dup_a = _chunk("src/core.py", 1, 30, symbol=None)
    dup_b = _chunk("src/core.py", 1, 30, symbol=None)  # duplicate copy
    chunks = [dup_a, dup_b]
    required = [{"path": "src/core.py"}]
    evidence = [{"path": "src/core.py", "start_line": 1},
                {"path": "src/core.py", "start_line": 1}]  # same chunk twice
    recall = required_chunks_covered(evidence, required, chunks)
    assert recall == 1.0
    assert recall <= 1.0  # duplicates can never push recall above 1
    # labelled ranking recall also stays bounded
    task = _task(required)
    res = evaluate_rerank(chunks, [0.9, 0.9], task)
    assert 0.0 <= res["recall_at_10"] <= 1.0


def test_7_missing_optional_never_fails_mandatory():
    required = [{"path": "src/core.py"}]
    helpful = [{"path": "docs/guide.md"}]
    chunks = [_chunk("src/core.py", 1, 40), _chunk("docs/guide.md", 1, 20)]
    evidence = [{"path": "src/core.py", "start_line": 1}]
    assert required_chunks_covered(evidence, required, chunks) == 1.0


def test_8_missing_mandatory_always_below_one():
    required = [{"path": "src/core.py"}, {"path": "src/other.py"}]
    chunks = [_chunk("src/core.py", 1, 40), _chunk("src/other.py", 1, 40)]
    evidence = [{"path": "src/core.py", "start_line": 1}]  # second required missing
    recall = required_chunks_covered(evidence, required, chunks)
    assert recall < 1.0
    # and when everything is missing it is exactly 0
    assert required_chunks_covered([], required, chunks) == 0.0


def test_ndcg_bounds_and_ideal_ordering():
    labels = [1, 0, 1, 0, 0]
    assert ndcg_at_k(labels, 10) <= 1.0
    assert ndcg_at_k([1, 1, 0, 0, 0], 10) == 1.0
    # relevant-at-bottom scores strictly worse
    assert ndcg_at_k([0, 0, 0, 1, 1], 10) < ndcg_at_k(labels, 10)
