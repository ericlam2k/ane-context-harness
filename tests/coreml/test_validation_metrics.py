"""Order-preservation metrics + runtime contract confirmations (WS4)."""
from __future__ import annotations

import math

import pytest

from ane_context_harness.coreml.validation_metrics import (
    FUTURE_ORDER_GATES, GATE_A_THRESHOLDS, cosine_similarity,
    evaluate_gates, order_preservation_metrics, pairwise_inversion_rate,
    sign_flips, spearman_correlation, topk_overlap)


def test_perfect_match_passes_all_future_gates():
    ref = [0.1, -0.4, 2.0, 1.5, -0.9, 0.0, 3.1, -2.2, 0.7, 1.1, -1.3, 0.4]
    m = order_preservation_metrics(ref, list(ref), [f"probe_{i}" for i in range(12)])
    assert m["max_abs_logit_diff"] == 0.0
    assert m["spearman"] == 1.0
    assert m["top10_overlap"] == 1.0
    assert m["pairwise_inversion_rate"] == 0.0
    assert m["sign_flip_count"] == 0
    assert evaluate_gates(m, FUTURE_ORDER_GATES) and all(
        evaluate_gates(m, FUTURE_ORDER_GATES).values())


def test_metrics_detect_rank_disruption():
    ref = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    cand = list(ref)
    cand[0], cand[11] = cand[11], cand[0]  # swap extremes
    m = order_preservation_metrics(ref, cand, [f"probe_{i}" for i in range(12)])
    assert m["spearman"] < 1.0
    assert m["pairwise_inversion_rate"] > 0.0
    assert m["top10_overlap"] < 1.0
    assert m["worst_case_fixture_ids"][0] in ("probe_0", "probe_11")


def test_sign_flip_counts_crossings():
    assert sign_flips([1.0, -1.0, 0.5], [-1.0, 1.0, 0.6]) == 2
    assert sign_flips([1.0, 0.0], [2.0, 0.0]) == 0


def test_gate_evaluation_is_configurable():
    m = {"cosine_similarity": 0.9995, "spearman": 0.995,
         "top10_overlap": 1.0, "pairwise_inversion_rate": 0.0,
         "max_abs_logit_diff": 0.02}
    strict = evaluate_gates(m, {**FUTURE_ORDER_GATES, "max_abs_logit": 0.01})
    assert strict["max_abs_logit"] is False
    lenient = evaluate_gates(m, FUTURE_ORDER_GATES)
    assert all(lenient.values())


def test_gate_a_thresholds_unchanged():
    assert GATE_A_THRESHOLDS == {"min_cosine": 0.999, "max_abs_logit": 0.05}


def test_length_mismatch_and_empty_rejected_clearly():
    with pytest.raises(ValueError, match="equal length"):
        order_preservation_metrics([1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="empty"):
        order_preservation_metrics([], [])


def test_helpers():
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert topk_overlap([3, 2, 1], [3, 2, 1], 2) == 1.0
    assert pairwise_inversion_rate([1, 2], [2, 1]) == 1.0
    assert pairwise_inversion_rate([1, 2], [1, 2]) == 0.0


# --- runtime contract confirmations -------------------------------------

def _fake_runtime(logit=0.5):
    from ane_context_harness.coreml.runtime import CoreMLRuntime
    rt = CoreMLRuntime(artifact=None)
    rt._loaded = True
    rt._model = object()  # marks available
    rt._tokenizer = type("T", (), {
        "seq_len": 8,
        "encode_pair": staticmethod(
            lambda q, c: ([101] + [1] * 6 + [102], [1] * 8, [0] * 8)),
    })()
    rt._model = type("M", (), {"predict": staticmethod(
        lambda inputs: {"logits": [logit]})})()
    return rt


class _Chunk:
    def __init__(self, content):
        self.content = content


def test_sigmoid_applied_exactly_once():
    rt = _fake_runtime(logit=0.5)
    scores = rt.predict("q", [_Chunk("a")])
    assert scores[0] == pytest.approx(1.0 / (1.0 + math.exp(-0.5)))
    # double sigmoid would give a different value
    once = 1.0 / (1.0 + math.exp(-0.5))
    twice = 1.0 / (1.0 + math.exp(-once))
    assert scores[0] != pytest.approx(twice)


def test_batch_size_one_and_batch_ordering():
    rt = _fake_runtime(logit=1.0)
    one = rt.predict("q", [_Chunk("only")])
    assert len(one) == 1
    # output length always equals input length; row i maps to chunk i
    many = rt.predict("q", [_Chunk("a"), _Chunk("b"), _Chunk("c")])
    assert len(many) == 3


def test_empty_batch_returns_empty_list():
    rt = _fake_runtime()
    assert rt.predict("q", []) == []


def test_invalid_batch_rejected():
    rt = _fake_runtime()
    with pytest.raises(ValueError):
        rt.predict("q", "not-a-list")


def test_scores_monotonic_with_logits():
    from ane_context_harness.coreml.runtime import CoreMLRuntime
    logits = [-2.0, -0.5, 0.0, 0.7, 3.0]
    scores = [CoreMLRuntime._sigmoid(x) for x in logits]
    assert scores == sorted(scores)
    ranks_ref = sorted(range(len(logits)), key=lambda i: -logits[i])
    ranks_score = sorted(range(len(scores)), key=lambda i: -scores[i])
    assert ranks_ref == ranks_score


def test_runtime_close_is_clean_and_terminal():
    from ane_context_harness.coreml.runtime import CoreMLRuntime
    rt = _fake_runtime()
    assert rt.available is True
    rt.close()
    assert rt.available is False
