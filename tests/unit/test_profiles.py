"""Tests for capability-profile schema and derivation (measurement-driven)."""
from __future__ import annotations

from src.ane_context_harness.platform.profiles import CapabilityProfile, derive_profile
from src.ane_context_harness.platform.calibration import mock_calibration_deterministic_only
from src.ane_context_harness.schemas import BehavioralProfile


DISCOVERY = {
    "machine_id": "abc123",
    "hardware": {"architecture": "arm64", "is_apple_silicon": True, "unified_memory_bytes": 17179869184},
    "software": {"macos_version": "14.0", "python_version": "3.14.0"},
    "devices": {"coreml_available": False, "neural_engine_observed": False},
    "runtime": {"compute_mode": "deterministic_only"},
}


def test_profile_schema_serializes():
    prof = CapabilityProfile(
        profile_version=1, machine_id="x", hardware={}, software={},
        devices={}, behavioral_profile="DETERMINISTIC_ONLY",
        features={}, calibration_fingerprint="f",
    )
    d = prof.to_dict()
    assert d["profile_version"] == 1
    assert d["behavioral_profile"] == "DETERMINISTIC_ONLY"


def test_default_profile_is_deterministic_only():
    prof = derive_profile(DISCOVERY)
    assert prof.behavioral_profile == BehavioralProfile.DETERMINISTIC_ONLY.value
    # reranker backend must be cpu_deterministic (no ML qualified)
    assert prof.features["reranker"]["backend"] == "cpu_deterministic"


def test_no_ane_claim_from_apple_silicon():
    prof = derive_profile(DISCOVERY)
    # Even on arm64 macOS, no ANE feature is enabled without measurements.
    assert prof.devices.get("neural_engine_observed") is False
    assert prof.features["secret_classifier"]["backend"] == "cpu_deterministic"


def test_ml_backend_requires_measurements():
    """An ml backend is only enabled when measured gates pass."""
    meas = {
        "reranker": {"backend": "coreml_all", "enabled": True,
                     "measured_speedup_percent": 22.0, "warm_p95_ms": 390,
                     "peak_memory_mb": 512, "failure_rate_percent": 0.0,
                     "numerical_validation": "passed"},
    }
    prof = derive_profile(DISCOVERY, measurements=meas)
    assert prof.features["reranker"]["backend"] == "coreml_all"
    assert prof.behavioral_profile == BehavioralProfile.BALANCED.value


def test_ml_backend_gated_by_speedup():
    meas = {
        "reranker": {"backend": "coreml_all", "enabled": True,
                     "measured_speedup_percent": 5.0, "warm_p95_ms": 200,
                     "peak_memory_mb": 200, "failure_rate_percent": 0.0,
                     "numerical_validation": "passed"},
    }
    prof = derive_profile(DISCOVERY, measurements=meas)
    assert prof.features["reranker"]["backend"] == "cpu_deterministic"
    assert prof.behavioral_profile == BehavioralProfile.DETERMINISTIC_ONLY.value


def test_mock_calibration_is_deterministic_only():
    bundle = mock_calibration_deterministic_only("t")
    prof = derive_profile(DISCOVERY, measurements=bundle.to_measurements())
    assert prof.behavioral_profile == BehavioralProfile.DETERMINISTIC_ONLY.value
    assert prof.features["reranker"]["backend"] == "cpu_deterministic"


def test_constrained_profile_when_ml_qualified_but_slow():
    """ML backend qualifies (>=15% speedup, p95<=1500) but p95 > 500ms -> CONSTRAINED."""
    meas = {
        "reranker": {"backend": "coreml_all", "enabled": True,
                     "measured_speedup_percent": 20.0, "warm_p95_ms": 800,
                     "peak_memory_mb": 600, "failure_rate_percent": 0.0,
                     "numerical_validation": "passed"},
    }
    prof = derive_profile(DISCOVERY, measurements=meas)
    assert prof.behavioral_profile == BehavioralProfile.CONSTRAINED.value
    assert prof.features["reranker"]["backend"] == "coreml_all"
