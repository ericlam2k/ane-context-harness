"""Phase 3 gate B: retrieval-quality metrics for reranker evaluation.

Pure functions so the metric math is unit-testable without a model or torch.
Relevance labels are derived from a labelled BenchmarkTask:
``required_chunks`` and ``helpful_chunks`` => relevant (1); ``irrelevant_chunks``
and all others => 0. Scoring is the reranker's output; we do NOT compare against
the deterministic scorer's scores.
"""
from __future__ import annotations

import math

# Canonical metric definitions. Emitted in JSON reports, Markdown output and
# benchmark docs so a number is never ambiguous. Implementations below must
# stay consistent with these strings (tests enforce presence + semantics).
METRIC_DEFINITIONS = {
    "recall_at_k": (
        "Proportion of ALL labelled relevant entries (required + helpful) "
        "found within the first k ranked results: hits_in_top_k / total_relevant."
    ),
    "ndcg_at_k": (
        "Ranking quality of the labelled relevant entries in the first k "
        "positions: DCG@k divided by the ideal DCG@k for the same labels "
        "(binary gains, log2 discount)."
    ),
    "mrr": (
        "Reciprocal rank of the FIRST labelled relevant result in the ranking: "
        "1 / rank_of_first_relevant, 0.0 when none is ranked."
    ),
    "required_evidence_recall": (
        "Proportion of mandatory (required) evidence entries retained in the "
        "final token-budgeted package: a required entry counts only when a "
        "selected chunk matches its path and, when the selected chunk is "
        "symbol-scoped, its symbol/line scope as well."
    ),
    "gate_b_quality": (
        "Gate-B ranking quality of one scorer over ALL indexed chunks of a "
        "task, computed from raw sigmoid relevance scores against "
        "relevance_labels (required + helpful = relevant)."
    ),
}


def _id_for_chunk(c) -> str:
    return f"{c.path}:{c.start_line}-{c.end_line}" if c.end_line else f"{c.path}:{c.start_line}"


def _matches(c, req: dict) -> bool:
    if c.path != req.get("path"):
        return False
    lines = req.get("lines")
    if lines and not (c.start_line <= lines[0] and c.end_line >= lines[1]):
        return False
    # Compare symbols only when the chunk itself is symbol-scoped: a file-level
    # chunk (symbol None) covers any symbol inside it, decided by path/lines.
    sym = req.get("symbol")
    if sym and c.symbol and c.symbol != sym:
        return False
    return True


def relevance_labels(chunks: list, task) -> list:
    """Binary relevance per chunk: required/helpful => 1 else 0."""
    labels = [0] * len(chunks)
    # index chunks by path for fast lookup of required/helpful/irrelevant
    by_path = {}
    for i, c in enumerate(chunks):
        by_path.setdefault(c.path, []).append((i, c))
    def mark(reqs, value):
        for req in reqs:
            path = req.get("path")
            if not path:
                continue
            if path not in by_path:
                continue
            has_qualifier = bool(req.get("symbol")) or bool(req.get("lines"))
            for idx, c in by_path[path]:
                if not has_qualifier or _matches(c, req):
                    labels[idx] = value
    mark(task.required_chunks, 1)
    mark(getattr(task, "helpful_chunks", []), 1)
    mark(getattr(task, "irrelevant_chunks", []), 0)
    return labels


def _dcg(labels: list, k: int) -> float:
    return sum((2 ** l - 1) / math.log2(i + 2) for i, l in enumerate(labels[:k]))


def ndcg_at_k(labels: list, k: int) -> float:
    labels = list(labels)
    ideal = sorted(labels, reverse=True)
    denom = _dcg(ideal, k)
    if denom <= 0:
        return 0.0
    return _dcg(labels, k) / denom


def recall_at_k(labels: list, k: int) -> float:
    labels = list(labels)
    if not any(labels):
        return 0.0
    hits = sum(labels[:k])
    total = sum(labels)
    return hits / total


def mrr(labels: list) -> float:
    labels = list(labels)
    for i, l in enumerate(labels, start=1):
        if l > 0:
            return 1.0 / i
    return 0.0


def evaluate_rerank(chunks: list, scores: list, task, ks=(1, 5, 10)) -> dict:
    """Score the reranker's per-chunk scores against a labelled task.

    ``scores`` may contain None (unavailable model); Nones are treated as the
    worst score so they rank last.
    """
    labels = relevance_labels(chunks, task)
    order = sorted(range(len(chunks)),
                   key=lambda i: (scores[i] is not None, scores[i] if scores[i] is not None else -1.0),
                   reverse=True)
    ranked = [labels[i] for i in order]
    return {
        "recall_at_1": round(recall_at_k(ranked, 1), 4),
        "recall_at_5": round(recall_at_k(ranked, 5), 4),
        "recall_at_10": round(recall_at_k(ranked, 10), 4),
        "ndcg_at_10": round(ndcg_at_k(ranked, 10), 4),
        "mrr": round(mrr(ranked), 4),
        "required_chunks_covered": round(sum(ranked[:1]) / max(sum(labels), 1)
                                          if any(labels) else 1.0, 4),
    }


def aggregate_quality(per_task: list) -> dict:
    if not per_task:
        return {"n": 0}
    def mean(key):
        vals = [t[key] for t in per_task if key in t]
        return round(sum(vals) / len(vals), 4) if vals else 0.0
    return {
        "n": len(per_task),
        "mean_recall_at_1": mean("recall_at_1"),
        "mean_recall_at_10": mean("recall_at_10"),
        "mean_ndcg_at_10": mean("ndcg_at_10"),
        "mean_mrr": mean("mrr"),
    }
