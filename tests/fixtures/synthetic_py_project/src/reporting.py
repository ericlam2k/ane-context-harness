"""Reporting helpers for the synthetic project.

Distractor content: unrelated to discount calculation. Verbose to exceed a
tight context budget so the harness can demonstrate filtering.
"""


def build_report(rows, title="Report"):
    lines = ["", f"=== {title} ==="]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index:04d}: {row}")
    lines.append(f"=== end {title} ===")
    return "\n".join(lines)


def summary_stats(values):
    if not values:
        return {"count": 0, "mean": 0.0, "min": 0, "max": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def group_by(rows, key):
    grouped = {}
    for row in rows:
        k = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
        grouped.setdefault(k, []).append(row)
    return grouped


def frequency_table(rows, key):
    counts = {}
    for k, items in group_by(rows, key).items():
        counts[k] = len(items)
    return counts


def render_table(headers, rows):
    out = [", ".join(headers)]
    for row in rows:
        out.append(", ".join(str(row.get(h, "")) for h in headers))
    return "\n".join(out)


def diff_reports(a, b):
    keys = set(a) | set(b)
    return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    import bisect
    idx = bisect.bisect_right(sorted_values, pct)
    return sorted_values[min(idx, len(sorted_values) - 1)]


def rolling_average(values, window):
    if window < 1:
        return []
    result = []
    acc = 0
    for i, v in enumerate(values):
        acc += v
        if i >= window:
            acc -= values[i - window]
        result.append(acc / min(i + 1, window))
    return result
