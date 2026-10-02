"""Analytics module for the synthetic project.

Distractor content: unrelated to discount calculation.
"""


class Metrics:
    def __init__(self):
        self.points = []

    def record(self, value):
        self.points.append(value)

    def average(self):
        return sum(self.points) / len(self.points) if self.points else 0.0


def moving_average(values, window):
    if window < 1 or not values:
        return []
    out = []
    acc = 0
    for i, v in enumerate(values):
        acc += v
        if i >= window:
            acc -= values[i - window]
        out.append(acc / min(i + 1, window))
    return out


def correlation(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


def histogram(values, buckets):
    counts = [0] * (len(buckets) - 1)
    for v in values:
        for i in range(len(buckets) - 1):
            if buckets[i] <= v < buckets[i + 1]:
                counts[i] += 1
                break
    return counts


def smooth(values, alpha=0.3):
    if not values:
        return []
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def detect_outliers(values, threshold=2.0):
    if not values:
        return []
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    sd = var ** 0.5
    return [v for v in values if sd and abs(v - m) / sd > threshold]
