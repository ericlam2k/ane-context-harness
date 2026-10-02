"""Latency and memory instrumentation. Pure stdlib, no source content retained."""
from __future__ import annotations

import time
import tracemalloc

try:
    import resource  # type: ignore

    def peak_rss_mb() -> float | None:
        try:
            # macOS ru_maxrss is in bytes
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        except Exception:
            return None
except Exception:  # pragma: no cover
    def peak_rss_mb() -> float | None:
        return None


class Timer:
    def __init__(self, label: str):
        self.label = label
        self.start = 0.0
        self.elapsed_ms = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000.0


class MetricsRecorder:
    """Collects timing + counters for a single request, no source text."""
    def __init__(self):
        self.stage_ms = {}
        self.counters = {}
        self._t0 = 0.0

    def time(self, stage: str) -> Timer:
        t = Timer(stage)
        self._t0_holder = t
        return t

    def record(self, stage: str, ms: float):
        self.stage_ms[stage] = round(ms, 3)

    def set(self, key: str, value):
        self.counters[key] = value

    def as_dict(self) -> dict:
        return {
            "stage_ms": dict(self.stage_ms),
            "counters": dict(self.counters),
        }
