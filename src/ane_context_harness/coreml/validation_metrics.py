"""Order-preservation metrics for conversion validation (raw logits).

Pure, dependency-free functions over vectors of raw logits
``reference`` (PyTorch) vs ``candidate`` (Core ML), computed BEFORE any
sigmoid so conversion fidelity is measured in the model's native output
space. Suggested future-release gates are configurable and recorded in the
artifact manifest; Gate A (min cosine 0.999 per pair, max abs logit 0.05)
is unchanged and keeps gating ``passed``.
"""
from __future__ import annotations

import math

# Gate A — unchanged, still decides numeric_validation.passed.
GATE_A_THRESHOLDS = {
    "min_cosine": 0.999,      # per-sample cosine (2-value vectors)
    "max_abs_logit": 0.05,
}

# Suggested future-release gates — evaluated + recorded, configurable per run.
FUTURE_ORDER_GATES = {
    "min_cosine": 0.999,             # cosine over the full logit vectors
    "min_spearman": 0.99,
    "min_top10_overlap": 0.98,
    "max_pairwise_inversion_rate": 0.01,
    "max_abs_logit": 0.05,
}


def _percentile(sorted_vals: list, pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = pct / 100.0 * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def cosine_similarity(a: list, b: list) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if den == 0:
        return 0.0
    return num / den


def _ranks(values: list) -> list:
    """Average ranks (1-based) with tie handling."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_correlation(a: list, b: list) -> float:
    """Pearson correlation of ranks (centered — required for reversal = -1)."""
    if len(a) < 2:
        return 1.0
    ra, rb = _ranks(a), _ranks(b)
    ma = sum(ra) / len(ra)
    mb = sum(rb) / len(rb)
    ca = [x - ma for x in ra]
    cb = [y - mb for y in rb]
    return cosine_similarity(ca, cb)


def topk_overlap(a: list, b: list, k: int) -> float:
    """Fraction of the reference's top-k indices also in the candidate top-k."""
    if not a:
        return 1.0
    k = min(k, len(a))
    top_a = set(sorted(range(len(a)), key=lambda i: -a[i])[:k])
    top_b = set(sorted(range(len(b)), key=lambda i: -b[i])[:k])
    return len(top_a & top_b) / k


def pairwise_inversion_rate(a: list, b: list) -> float:
    """Fraction of pairs whose relative order flips between a and b."""
    n = len(a)
    if n < 2:
        return 0.0
    inversions = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = a[i] - a[j]
            db = b[i] - b[j]
            if da == 0 or db == 0:
                continue
            pairs += 1
            if (da > 0) != (db > 0):
                inversions += 1
    if pairs == 0:
        return 0.0
    return inversions / pairs


def sign_flips(a: list, b: list) -> int:
    """Pairs of values on opposite sides of zero (a true sign flip)."""
    count = 0
    for x, y in zip(a, b):
        if x == 0 or y == 0:
            continue
        if (x > 0) != (y > 0):
            count += 1
    return count


def order_preservation_metrics(reference: list, candidate: list,
                               fixture_ids: list | None = None) -> dict:
    """Full order-preservation report for equal-length raw-logit vectors."""
    if len(reference) != len(candidate):
        raise ValueError("reference and candidate must have equal length")
    if not reference:
        raise ValueError("empty logit vectors")
    n = len(reference)
    ids = list(fixture_ids) if fixture_ids else [f"sample_{i}" for i in range(n)]
    diffs = sorted(abs(x - y) for x, y in zip(reference, candidate))
    worst = sorted(range(n), key=lambda i: -abs(reference[i] - candidate[i]))
    return {
        "n_samples": n,
        "p50_abs_logit_diff": round(_percentile(diffs, 50), 6),
        "p95_abs_logit_diff": round(_percentile(diffs, 95), 6),
        "p99_abs_logit_diff": round(_percentile(diffs, 99), 6),
        "max_abs_logit_diff": round(diffs[-1], 6),
        "cosine_similarity": round(cosine_similarity(reference, candidate), 6),
        "spearman": round(spearman_correlation(reference, candidate), 6),
        "top5_overlap": round(topk_overlap(reference, candidate, 5), 6),
        "top10_overlap": round(topk_overlap(reference, candidate, 10), 6),
        "pairwise_inversion_rate": round(pairwise_inversion_rate(reference, candidate), 6),
        "sign_flip_count": sign_flips(reference, candidate),
        "worst_case_fixture_ids": [ids[i] for i in worst[:5]],
        "compared_raw_logits": True,
    }


def evaluate_gates(metrics: dict, gates: dict) -> dict:
    """Evaluate configured gates against an order-preservation metrics dict."""
    results = {}
    if "min_cosine" in gates:
        results["min_cosine"] = metrics.get("cosine_similarity", 0.0) >= gates["min_cosine"]
    if "min_spearman" in gates:
        results["min_spearman"] = metrics.get("spearman", 0.0) >= gates["min_spearman"]
    if "min_top10_overlap" in gates:
        results["min_top10_overlap"] = metrics.get("top10_overlap", 0.0) >= gates["min_top10_overlap"]
    if "max_pairwise_inversion_rate" in gates:
        results["max_pairwise_inversion_rate"] = (
            metrics.get("pairwise_inversion_rate", 1.0) <= gates["max_pairwise_inversion_rate"])
    if "max_abs_logit" in gates:
        results["max_abs_logit"] = metrics.get("max_abs_logit_diff", 1e9) <= gates["max_abs_logit"]
    return results
