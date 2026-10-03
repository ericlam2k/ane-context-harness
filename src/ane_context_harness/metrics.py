"""Portable ranking-methodology helpers (no models, no ANE).

Canonical metric definitions plus pure label/score math over labelled
BenchmarkTasks: relevance labels (required + helpful => relevant),
Recall@K, nDCG, MRR, and package-emission-order ranking metrics.
Moved here from the Arm-C evaluation apparatus so the portable line keeps
one methodology home; the A/B/C run harness itself is private.
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
    """Score per-chunk scores against a labelled task.

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


def _label_rate(haystack: list, labels: list) -> float:
    if not labels:
        return 1.0
    hits = sum(1 for lab in labels
               if any(lab.get("path") == e.get("path") for e in haystack))
    return hits / len(labels)


def _percentile(samples: list, pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def _dcg_binary(rel: list, k: int) -> float:
    """Binary-gain DCG: sum of 1/log2(rank+1) over relevant items in top k."""
    return sum(1.0 / math.log2(i + 2) for i, r in enumerate(rel[:k]) if r)


def package_ranking_metrics(evidence: list, chunks: list, task) -> dict:
    """Ranking quality of the PACKAGE emission order against corpus labels.

    The ranking is the order evidence is presented in (category-stable, then
    score descending). Recall@k uses the corpus-wide relevant total as the
    denominator, so unselected relevant chunks stay misses; nDCG@10 compares
    against the ideal order of ALL corpus labels (unselected relevant rank
    after everything selected). Relevant = required + helpful (METRIC_DEFINITIONS).
    """
    labels = relevance_labels(chunks, task)
    idx_by = {(c.path, c.start_line): i for i, c in enumerate(chunks)}
    ranked_idx, ids = [], []
    for e in evidence:
        i = idx_by.get((e["path"], e["start_line"]))
        if i is None:
            continue
        ranked_idx.append(i)
        ids.append(f"{e['path']}:{e['start_line']}-{e['end_line']}"
                   if e.get("end_line") else f"{e['path']}:{e['start_line']}")
    rel = [labels[i] for i in ranked_idx]
    total_rel = sum(labels)
    out = {"ranked_chunk_ids": ids}
    for k in (1, 5, 10):
        hits = sum(rel[:k])
        out[f"recall_at_{k}"] = round(hits / total_rel, 4) if total_rel else 1.0
    idcg = _dcg_binary(sorted(labels, reverse=True), 10)
    out["ndcg_at_10"] = round(_dcg_binary(rel, 10) / idcg, 4) if idcg > 0 else 0.0
    mrr_val = 0.0
    for pos, r in enumerate(rel, start=1):
        if r:
            mrr_val = 1.0 / pos
            break
    out["mrr"] = round(mrr_val, 4)
    return out
