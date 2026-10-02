"""Model-lifecycle telemetry: thread-safe counters + bounded reason log.

Counts only — never source text, chunk contents or secrets. Fallback reasons
are short machine strings (error type / stage), truncated defensively.
"""
from __future__ import annotations

import threading

_COUNTER_KEYS = (
    "artifact_resolution_count",
    "runtime_construction_count",
    "model_load_count",
    "prediction_count",
    "cache_hit_count",
    "cache_miss_count",
    "cache_invalidation_count",
    "cache_eviction_count",
    "concurrent_construction_prevented_count",
    "fallback_count",
    "shutdown_count",
)


class LifecycleMetrics:
    def __init__(self, max_reasons: int = 50):
        self._lock = threading.Lock()
        self._counts = {k: 0 for k in _COUNTER_KEYS}
        self._fallback_reasons: list[str] = []
        self._max_reasons = max_reasons
        self.cold_load_ms: float | None = None
        self.last_construction_ms: float | None = None

    def incr(self, key: str, n: int = 1) -> None:
        if key not in self._counts:
            return
        with self._lock:
            self._counts[key] += n

    def record_fallback(self, reason: str) -> None:
        with self._lock:
            self._counts["fallback_count"] += 1
            self._fallback_reasons.append(str(reason)[:200])
            if len(self._fallback_reasons) > self._max_reasons:
                self._fallback_reasons = self._fallback_reasons[-self._max_reasons:]

    def record_construction_ms(self, ms: float, first_load: bool) -> None:
        with self._lock:
            self.last_construction_ms = round(ms, 2)
            if first_load and self.cold_load_ms is None:
                self.cold_load_ms = round(ms, 2)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                **self._counts,
                "cold_load_ms": self.cold_load_ms,
                "last_construction_ms": self.last_construction_ms,
                "fallback_reasons": list(self._fallback_reasons[-10:]),
            }

    def reset(self) -> None:
        with self._lock:
            self._counts = {k: 0 for k in _COUNTER_KEYS}
            self._fallback_reasons = []
            self.cold_load_ms = None
            self.last_construction_ms = None
