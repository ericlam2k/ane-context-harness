"""Calibration interface + mock benchmark results for tests.

Real calibration runs the discover->validate->benchmark sequence against
candidate model/backends (Phase 3). Phase 1 ships a mock only so the profile
derivation and degradation pipeline is testable without any Core ML model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalibrationResult:
    feature: str
    backend: str
    enabled: bool
    measured_speedup_percent: float = 0.0
    warm_p50_ms: float | None = None
    warm_p95_ms: float | None = None
    peak_memory_mb: float | None = None
    failure_rate_percent: float = 0.0
    numerical_validation: str = "not_run"
    reason: str = ""


@dataclass
class CalibrationBundle:
    """Results for all features for a given hardware/software fingerprint."""
    fingerprint: str
    results: list = field(default_factory=list)

    def result(self, feature: str) -> CalibrationResult | None:
        for r in self.results:
            if r.feature == feature:
                return r
        return None

    def to_measurements(self) -> dict:
        out = {}
        for r in self.results:
            out[r.feature] = {
                "backend": r.backend,
                "enabled": r.enabled,
                "measured_speedup_percent": r.measured_speedup_percent,
                "warm_p50_ms": r.warm_p50_ms,
                "warm_p95_ms": r.warm_p95_ms,
                "peak_memory_mb": r.peak_memory_mb,
                "failure_rate_percent": r.failure_rate_percent,
                "numerical_validation": r.numerical_validation,
                "reason": r.reason,
            }
        return out


def mock_calibration_deterministic_only(fingerprint: str = "test") -> CalibrationBundle:
    """Mock result for Phase 1: only deterministic ranking, no ML."""
    return CalibrationBundle(
        fingerprint=fingerprint,
        results=[
            CalibrationResult(
                feature="reranker",
                backend="cpu_deterministic",
                enabled=True,
                measured_speedup_percent=0.0,
                warm_p50_ms=1.0,
                warm_p95_ms=2.0,
                peak_memory_mb=0.0,
                failure_rate_percent=0.0,
                numerical_validation="passed",
                reason="deterministic_only_portable_line",
            ),
            CalibrationResult(
                feature="embedding",
                backend="disabled",
                enabled=False,
                reason="embeddings_deferred_phase1",
            ),
            CalibrationResult(
                feature="secret_classifier",
                backend="disabled",
                enabled=False,
                reason="secret_detection_deferred_phase2",
            ),
        ],
    )
