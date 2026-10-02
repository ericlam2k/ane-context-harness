"""Tests for Phase 3 calibration + qualification (no coremltools/torch)."""
from __future__ import annotations

from src.ane_context_harness.coreml.calibration import (
    mock_calibration_phase3_classified,
    qualify_backend,
    to_feature_measurements,
    benchmark_backends,
    BackendMeasurement,
)
from src.ane_context_harness.platform.profiles import derive_profile
from src.ane_context_harness.schemas import BehavioralProfile


DISC = {
    "machine_id": "abc123",
    "hardware": {"architecture": "arm64", "is_apple_silicon": True, "unified_memory_bytes": 17179869184},
    "software": {"macos_version": "14.0", "python_version": "3.14.0"},
    "devices": {"coreml_available": True, "neural_engine_observed": True},
    "runtime": {"compute_mode": "deterministic_only"},
}


def test_phase3_mock_qualifies_coreml_cpu_gpu():
    prof = derive_profile(DISC, measurements=mock_calibration_phase3_classified("t"))
    assert prof.features["reranker"]["backend"] == "coreml_cpu_gpu"
    assert prof.behavioral_profile == BehavioralProfile.BALANCED.value


def test_phase3_profile_still_does_not_claim_ane():
    prof = derive_profile(DISC, measurements=mock_calibration_phase3_classified("t"))
    # Backend is coreml_cpu_gpu (GPU+CPU), not coreml_all (which could use ANE).
    assert prof.features["reranker"]["backend"] != "coreml_all"
    assert prof.devices.get("neural_engine_observed") is True  # observed, not claimed


def test_qualify_prefers_all_then_cpu_gpu_then_cpu_only():
    def mk(name, p95, speedup=40.0, passed=True):
        return BackendMeasurement(backend=name, seq_len=256, batch_size=1, available=True,
                                  warm_p50_ms=p95 - 10, warm_p95_ms=p95, peak_memory_mb=300.0,
                                  failure_rate_percent=0.0, measured_speedup_percent=speedup,
                                  numerical_validation="passed" if passed else "failed")
    outs = qualify_backend([
        mk("coreml_all", 480), mk("coreml_cpu_gpu", 470), mk("coreml_cpu_only", 600),
        BackendMeasurement(backend="cpu_deterministic", seq_len=256, batch_size=1, available=True,
                            warm_p50_ms=1.0, warm_p95_ms=2.0, peak_memory_mb=0.0,
                            failure_rate_percent=0.0, measured_speedup_percent=0.0,
                            numerical_validation="passed"),
    ], quality={"recall_at_1": 0.9, "ndcg_at_10": 0.8, "mrr": 0.7})
    assert outs.backend == "coreml_all"
    assert outs.enabled is True


def test_qualify_falls_back_when_numerical_fails():
    m = BackendMeasurement(backend="coreml_all", seq_len=256, batch_size=1, available=True,
                           warm_p50_ms=480, warm_p95_ms=490, peak_memory_mb=300.0,
                           failure_rate_percent=0.0, measured_speedup_percent=40.0,
                           numerical_validation="failed")
    out = qualify_backend([m], quality={"recall_at_1": 0.9, "ndcg_at_10": 0.8, "mrr": 0.7})
    assert out.backend == "cpu_deterministic"
    assert out.enabled is False


def test_qualify_uses_cpu_when_no_coreml():
    cpu = BackendMeasurement(backend="cpu_deterministic", seq_len=256, batch_size=1,
                             available=True, warm_p50_ms=1.0, warm_p95_ms=2.0,
                             peak_memory_mb=0.0, failure_rate_percent=0.0,
                             measured_speedup_percent=0.0, numerical_validation="passed")
    out = qualify_backend([cpu])
    assert out.backend == "cpu_deterministic"
    assert out.enabled is True


def test_benchmark_backends_degrades_without_tooling():
    res = benchmark_backends(None, [("q", "content")], 256, n=3)
    names = [r.backend for r in res]
    assert names == ["cpu_deterministic", "coreml_cpu_only", "coreml_cpu_gpu", "coreml_all"]
    # coreml backends all unavailable (no coremltools / no artifact)
    for r in res[1:]:
        assert r.available is False
        assert r.failure_rate_percent == 100.0


def test_to_feature_measurements_deterministic():
    cpu = BackendMeasurement(backend="cpu_deterministic", seq_len=256, batch_size=1,
                             available=True, warm_p50_ms=1.0, warm_p95_ms=2.0,
                             peak_memory_mb=0.0, failure_rate_percent=0.0,
                             measured_speedup_percent=0.0, numerical_validation="passed")
    out = qualify_backend([cpu])
    feat = to_feature_measurements(out)
    assert feat["backend"] == "cpu_deterministic"
    assert feat["enabled"] is True
    assert feat["numerical_validation"] == "passed"


def test_quality_gate_filters_poor_model():
    m = BackendMeasurement(backend="coreml_all", seq_len=256, batch_size=1, available=True,
                           warm_p50_ms=480, warm_p95_ms=490, peak_memory_mb=300.0,
                           failure_rate_percent=0.0, measured_speedup_percent=40.0,
                           numerical_validation="passed")
    # quality too poor
    out = qualify_backend([m], quality={"recall_at_1": 0.1, "ndcg_at_10": 0.1, "mrr": 0.0})
    assert out.backend == "cpu_deterministic"


def test_quality_gate_uses_recall_at_10_when_supplied():
    """Multi-relevant tasks cap recall_at_1 at 1/num_relevant; the real quality
    dict supplies recall_at_10, which the gate prefers."""
    m = BackendMeasurement(backend="coreml_all", seq_len=128, batch_size=1, available=True,
                           warm_p50_ms=40, warm_p95_ms=60, peak_memory_mb=300.0,
                           failure_rate_percent=0.0, measured_speedup_percent=40.0,
                           numerical_validation="passed")
    quality = {"recall_at_1": 0.30, "recall_at_10": 1.0,
               "ndcg_at_10": 0.85, "mrr": 0.9}
    out = qualify_backend([m], quality=quality)
    assert out.backend == "coreml_all"
    assert out.enabled is True
    # ...but a weak recall_at_10 still fails
    out2 = qualify_backend([m], quality={"recall_at_1": 0.30, "recall_at_10": 0.2,
                                         "ndcg_at_10": 0.85, "mrr": 0.9})
    assert out2.backend == "cpu_deterministic"
