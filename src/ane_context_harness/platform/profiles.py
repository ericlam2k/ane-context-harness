"""Capability-profile schema and derivation from measurements.

Profiles are derived from measurements, never from chip names. Phase 1 has no
qualified Core ML backend, so the default profile is DETERMINISTIC_ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import BehavioralProfile


@dataclass
class CapabilityProfile:
    profile_version: int
    machine_id: str
    hardware: dict
    software: dict
    devices: dict
    behavioral_profile: str
    features: dict
    calibration_fingerprint: str

    def to_dict(self) -> dict:
        return {
            "profile_version": self.profile_version,
            "machine_id": self.machine_id,
            "hardware": self.hardware,
            "software": self.software,
            "devices": self.devices,
            "behavioral_profile": self.behavioral_profile,
            "features": self.features,
            "calibration_fingerprint": self.calibration_fingerprint,
        }


def _gate_ml(backend: str, meas: dict) -> bool:
    """An ML backend is enabled only when it clears all measured gates.

    The deterministic backend never needs the speedup gate.
    """
    if backend == "cpu_deterministic":
        return meas.get("failure_rate_percent", 0) <= 0.1
    speedup = meas.get("measured_speedup_percent", 0) or 0
    min_speedup = meas.get("required_speedup_percent", 15) or 15
    fail = meas.get("failure_rate_percent", 0) or 0
    p95 = meas.get("warm_p95_ms")
    mem = meas.get("peak_memory_mb")
    max_mem = meas.get("profile_memory_limit_mb", 1200) or 1200
    within_latency = (p95 is None) or (p95 <= 1500)
    within_mem = (mem is None) or (mem <= max_mem)
    numerical_ok = meas.get("numerical_validation", "not_run") == "passed"
    return (
        speedup >= min_speedup
        and fail <= 0.1
        and within_latency
        and within_mem
        and numerical_ok
    )


def derive_profile(discovery: dict, measurements: dict | None = None) -> CapabilityProfile:
    """Derive a behavioral profile from discovery + optional calibration measurements.

    measurements shape:
      {"reranker": {"backend": "coreml_all", "enabled": True,
                    "measured_speedup_percent": 22.0, "warm_p95_ms": 390,
                    "peak_memory_mb": 410, "failure_rate_percent": 0.0,
                    "numerical_validation": "passed"}, ...}
    """
    measurements = measurements or {}
    machine_id = discovery.get("machine_id", "")
    devices = discovery.get("devices", {})
    hw = discovery.get("hardware", {})
    sw = discovery.get("software", {})

    features = {
        "reranker": _feature_state(measurements.get("reranker", {})),
        "embedding": _feature_state(measurements.get("embedding", {})),
        "secret_classifier": _feature_state(measurements.get("secret_classifier", {})),
    }

    reranker = features["reranker"]
    rb = reranker.get("backend", "cpu_deterministic")
    p95 = reranker.get("warm_p95_ms")
    # ML backends (coreml/local_gpu) are measurement-qualified; the deterministic
    # CPU backend is always available but yields DETERMINISTIC_ONLY.
    if rb in ("coreml_all", "coreml_cpu_gpu", "local_gpu"):
        if p95 is not None and p95 <= 500:
            behavioral = BehavioralProfile.BALANCED
        elif p95 is not None and p95 <= 1500:
            behavioral = BehavioralProfile.CONSTRAINED
        else:
            behavioral = BehavioralProfile.BALANCED  # qualified, limits unknown
    else:
        behavioral = BehavioralProfile.DETERMINISTIC_ONLY

    fp = (
        f"{machine_id}-{sw.get('macos_version', 'na')}-"
        f"{sw.get('python_version', 'na')}-phase01"
    )

    return CapabilityProfile(
        profile_version=1,
        machine_id=machine_id,
        hardware=hw,
        software=sw,
        devices=devices,
        behavioral_profile=behavioral.value,
        features=features,
        calibration_fingerprint=fp,
    )


def _feature_state(meas: dict) -> dict:
    """Compute a feature's final state from its measurement dict.

    Phase 1 default (no measurements supplied): deterministic-only.
    """
    backend = meas.get("backend", "cpu_deterministic")
    allowed = _gate_ml(backend, meas)
    if allowed and backend != "cpu_deterministic":
        return {
            "enabled": True,
            "backend": backend,
            "warm_p95_ms": meas.get("warm_p95_ms"),
            "peak_memory_mb": meas.get("peak_memory_mb"),
            "failure_rate_percent": meas.get("failure_rate_percent", 0),
            "numerical_validation": meas.get("numerical_validation", "passed"),
            "reason": meas.get("reason", "benchmark_qualified"),
        }
    # Deterministic fallback (always available).
    return {
        "enabled": True,
        "backend": "cpu_deterministic",
        "reason": meas.get("reason", "no_qualified_ml_backend") if meas else "default_no_measurements",
    }
