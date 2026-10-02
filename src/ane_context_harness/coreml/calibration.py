"""Phase 3 reranker calibration: benchmark backends + qualification gates.

Two independent gates:
  A. Numerical conversion fidelity — Core ML logits vs the original PyTorch
     checkpoint (cosine + max-abs). NOT vs the deterministic scorer.
  B. Code-context retrieval quality — Recall@K / nDCG@K / MRR against the
     harness labelled benchmark tasks. NOT deterministic-score equality.

Gates feed the capability profile's ``reranker`` feature, which selects the
backend. Selection is by measured performance, never by chip identity.

All heavy imports (torch / coremltools / transformers) happen lazily and the
module degrades to the deterministic-only measurement when they (or the
compiled artifact) are absent, so it is safe to import on any machine.
"""
from __future__ import annotations

import os
import time
import json
from dataclasses import dataclass, asdict, replace
from pathlib import Path

from ..platform.profiles import BehavioralProfile
from ..platform.discovery import discover as _discover
from ..benchmark import load_benchmark_tasks, BenchmarkResult
from ..retrieval.reranker import _compute_unit_for, CoreMLReranker

# Latency / memory / speed gates (mirrors platform.profiles._gate_ml).
REquired_SPEEDUP_PCT = 15
MAX_P95_MS = 1500.0
MAX_PEAK_MEMORY_MB = 1200.0
MAX_FAILURE_RATE_PCT = 0.1


@dataclass
class BackendMeasurement:
    backend: str            # cpu_deterministic | coreml_cpu_only | coreml_cpu_gpu | coreml_all
    seq_len: int
    batch_size: int
    available: bool
    warm_p50_ms: float
    warm_p95_ms: float
    peak_memory_mb: float
    failure_rate_percent: float
    measured_speedup_percent: float  # vs the cpu_deterministic baseline
    numerical_validation: str = "not_run"  # passed | failed | skipped
    quality: dict = None                    # gate B metrics
    reason: str = ""


@dataclass
class CalibrationOutcome:
    backend: str
    enabled: bool
    measurement: BackendMeasurement | None
    gates: dict
    reason: str


def _peak_rss_mb() -> float:
    from ..telemetry.metrics import peak_rss_mb
    return float(peak_rss_mb() or 0.0)


def _sample_pairs_from_tasks(tasks_dir: str = "benchmarks/tasks", repo_root: str | None = None) -> list:
    """Build (task, chunk_content) pairs from labelled benchmark tasks + a repo."""
    tasks = load_benchmark_tasks(tasks_dir)
    pairs = []
    if repo_root:
        for t in tasks:
            for rc in t.required_chunks:
                p = os.path.join(repo_root, rc.get("path", ""))
                if os.path.exists(p):
                    try:
                        pairs.append((t.task, open(p, encoding="utf-8").read()[:2048]))
                    except Exception:
                        pass
    else:
        # fallback synthetic pairs so the harness always has something to time
        pairs = [("how does the discount calculation work",
                  "def calculate_discount(price, rate): return price - (price * rate)")]
    return pairs or [("query", "content")]


def _bench_coreml(artifact, compute_unit_name: str, pairs: list, seq_len: int,
                  n_warm: int = 3, n: int = 50) -> BackendMeasurement:
    from ..coreml.runtime import CoreMLRuntime, CoreMLComputeUnit
    cu = _compute_unit_for(compute_unit_name)
    rt = CoreMLRuntime(artifact, compute_unit=cu)
    if not rt.available:
        return BackendMeasurement(backend=compute_unit_name, seq_len=seq_len, batch_size=1,
                                  available=False, warm_p50_ms=0.0, warm_p95_ms=0.0,
                                  peak_memory_mb=0.0, failure_rate_percent=100.0,
                                  measured_speedup_percent=0.0,
                                  numerical_validation="skipped",
                                  reason=rt.load_error or "unavailable")
    chunks_klass = []

    class _C:
        pass

    chunk_objs = []
    for _, content in pairs:
        c = _C(); c.content = content; chunk_objs.append(c)
    # warm
    for _ in range(min(n_warm, len(chunk_objs))):
        rt.predict(pairs[0][0], chunk_objs[:1])
    import numpy as np  # type: ignore
    timings = []
    fails = 0
    mem0 = _peak_rss_mb()
    for i in range(n):
        pair = pairs[i % len(pairs)]
        c = chunk_objs[i % len(chunk_objs)]
        t0 = time.perf_counter()
        try:
            sc = rt.predict(pair[0], [c])
            if sc is None or sc[0] is None:
                fails += 1
        except Exception:  # noqa: BLE001
            fails += 1
        timings.append((time.perf_counter() - t0) * 1000.0)
    mem1 = _peak_rss_mb()
    timings.sort()
    p50 = timings[int(len(timings) * 0.5) - 1]
    p95 = timings[min(len(timings) - 1, max(0, int(len(timings) * 0.95) - 1))]
    return BackendMeasurement(
        backend=compute_unit_name, seq_len=seq_len, batch_size=1,
        available=True, warm_p50_ms=round(p50, 3), warm_p95_ms=round(p95, 3),
        peak_memory_mb=round(mem1 - mem0, 1),
        failure_rate_percent=round(fails / max(n, 1) * 100, 2),
        measured_speedup_percent=0.0,  # set after baseline measurement
        numerical_validation=_numerical_state(rt),
        reason="ok",
    )


def _bench_cpu_baseline(pairs: list, n: int = 50, seq_len: int = 128,
                        artifact=None) -> BackendMeasurement:
    """Reference: PyTorch CPU eager scoring of the SAME checkpoint.

    The deterministic (no-ML) reranker is a no-op and cannot serve as a speed
    baseline for an ML backend; the meaningful speedup for Core ML is against
    running the identical model in PyTorch on CPU. Falls back to a degenerate
    timing when torch/the checkpoint is unavailable (tests, non-build hosts).
    """
    ref = _load_torch_reference(artifact)
    class _C: pass
    chunk_objs = []
    for _, content in pairs:
        c = _C(); c.content = content; chunk_objs.append(c)
    timings = []
    reason = "pytorch_cpu_reference"
    if ref is None:
        reason = "pytorch_reference_unavailable"
        for i in range(n):
            t0 = time.perf_counter()
            _ = len(pairs)
            timings.append((time.perf_counter() - t0) * 1000.0)
    else:
        model, tok = ref
        import torch  # type: ignore
        # warm-up (excluded from timings)
        for i in range(min(3, n)):
            q, c = pairs[i % len(pairs)]
            enc = tok(q, c, truncation=True, padding="max_length",
                      max_length=seq_len, return_tensors="pt")
            with torch.no_grad():
                model(**enc)
        for i in range(n):
            q, c = pairs[i % len(pairs)]
            t0 = time.perf_counter()
            enc = tok(q, c, truncation=True, padding="max_length",
                      max_length=seq_len, return_tensors="pt")
            with torch.no_grad():
                model(**enc)
            timings.append((time.perf_counter() - t0) * 1000.0)
    timings.sort()
    p50 = timings[int(len(timings) * 0.5) - 1]
    p95 = timings[min(len(timings) - 1, max(0, int(len(timings) * 0.95) - 1))]
    return BackendMeasurement(backend="cpu_deterministic", seq_len=seq_len, batch_size=1,
                              available=True, warm_p50_ms=round(p50, 3),
                              warm_p95_ms=round(p95, 3), peak_memory_mb=_peak_rss_mb(),
                              failure_rate_percent=0.0,
                              measured_speedup_percent=0.0,
                              numerical_validation="passed",
                              reason=reason)


def _load_torch_reference(artifact):
    """(model, tokenizer) from the pinned build-cache snapshot, or None."""
    if artifact is None:
        return None
    try:
        import torch  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForSequenceClassification, AutoTokenizer)
        from .convert import PHASE3_BUILD_CACHE
        snap = os.path.join(
            PHASE3_BUILD_CACHE, "huggingface",
            "models--" + artifact.model_id.replace("/", "--"),
            "snapshots", artifact.revision)
        if not os.path.isdir(snap):
            return None
        tok = AutoTokenizer.from_pretrained(snap, use_fast=True)
        model = AutoModelForSequenceClassification.from_pretrained(snap)
        model.eval()
        return model, tok
    except Exception:  # noqa: BLE001
        return None


def _numerical_state(rt) -> str:
    nv = getattr(getattr(rt, "artifact", None), "numeric_validation", None)
    if isinstance(nv, dict):
        return "passed" if nv.get("passed") is True else ("failed" if nv else "not_run")
    if isinstance(nv, str):
        return nv or "not_run"
    return "not_run"


def benchmark_backends(artifact, pairs: list, seq_len: int, n: int = 50) -> list:
    """Benchmark all four backends for one seq_len. Degrades gracefully when
    torch/coremltools/artifact are unavailable."""
    results = [_bench_cpu_baseline(pairs, n, seq_len=seq_len, artifact=artifact)]
    from ..coreml.runtime import CoreMLRuntime  # lazy
    for name in ("coreml_cpu_only", "coreml_cpu_gpu", "coreml_all"):
        if not _can_attempt_coreml(artifact):
            results.append(BackendMeasurement(
                backend=name, seq_len=seq_len, batch_size=1, available=False,
                warm_p50_ms=0.0, warm_p95_ms=0.0, peak_memory_mb=0.0,
                failure_rate_percent=100.0, measured_speedup_percent=0.0,
                numerical_validation="skipped", reason="coremltools_not_installed_or_no_artifact"))
            continue
        m = _bench_coreml(artifact, name, pairs, seq_len, n=n)
        results.append(m)
    # compute speedup vs cpu baseline for qualified backends
    cpu = results[0]
    for i in range(1, len(results)):
        m = results[i]
        if m.available and cpu.available:
            sp = 0.0 if m.warm_p95_ms <= 0 else max(0.0, (cpu.warm_p95_ms - m.warm_p95_ms) / m.warm_p95_ms * 100.0)
            results[i] = replace(m, measured_speedup_percent=sp)
    return results


def _can_attempt_coreml(artifact) -> bool:
    try:
        import coremltools  # type: ignore
        from ..coreml.runtime import CoreMLRuntime  # noqa: F401
    except ImportError:
        return False
    if not artifact or not artifact.exists():
        return False
    return True


def _passes_numerical(m: BackendMeasurement) -> bool:
    return m.numerical_validation == "passed"


def _quality_passes(quality: dict | None) -> bool:
    if not quality:
        return False
    # gate B: retrieval quality must meet minimums. recall_at_10 is the
    # attainable metric for multi-relevant tasks (recall_at_1 is capped at
    # 1/num_relevant); fall back to recall_at_1 when only it is supplied.
    recall = quality.get("recall_at_10")
    if recall is None:
        recall = quality.get("recall_at_1", 0.0)
    return (recall >= 0.5
            and quality.get("ndcg_at_10", 0.0) >= 0.5
            and quality.get("mrr", 0.0) >= 0.3)


def qualify_backend(measurements: list, quality: dict | None = None) -> CalibrationOutcome:
    """Pick the best backend that clears gates. Preference order:
    coreml_all > coreml_cpu_gpu > coreml_cpu_only > cpu_deterministic."""
    gates = {"required_speedup_pct": 15,
             "max_p95_ms": MAX_P95_MS, "max_peak_memory_mb": MAX_PEAK_MEMORY_MB,
             "max_failure_rate_pct": MAX_FAILURE_RATE_PCT,
             "quality_pass": _quality_passes(quality),
             "quality": quality or {}}
    ranked = ["coreml_all", "coreml_cpu_gpu", "coreml_cpu_only", "cpu_deterministic"]
    by_backend = {m.backend: m for m in measurements}
    for name in ranked:
        m = by_backend.get(name)
        if not m:
            continue
        if name == "cpu_deterministic":
            return CalibrationOutcome(backend=name, enabled=True, measurement=m,
                                      gates=gates, reason="deterministic_only_no_coreml_qualified")
        # coreml backend gates
        if not m.available:
            continue
        ok = (m.measured_speedup_percent >= 15
              and m.warm_p95_ms <= MAX_P95_MS
              and m.peak_memory_mb <= MAX_PEAK_MEMORY_MB
              and m.failure_rate_percent <= MAX_FAILURE_RATE_PCT
              and _passes_numerical(m)
              and _quality_passes(quality))
        if ok:
            return CalibrationOutcome(backend=name, enabled=True, measurement=m, gates=gates,
                                      reason="benchmark_qualified")
    # none qualified
    best = by_backend.get("coreml_all") or by_backend.get("coreml_cpu_gpu")
    if best and best.available and not _passes_numerical(best):
        return CalibrationOutcome(backend="cpu_deterministic", enabled=False,
                                  measurement=best, gates=gates,
                                  reason="numerical_fidelity_failed")
    return CalibrationOutcome(backend="cpu_deterministic", enabled=True,
                              measurement=by_backend.get("cpu_deterministic"),
                              gates=gates, reason="no_coreml_backend_qualified")


def to_feature_measurements(outcome: CalibrationOutcome) -> dict:
    """Render into the measurement dict consumed by platform.profiles.derive_profile."""
    m = outcome.measurement
    if not m or outcome.backend == "cpu_deterministic":
        return {"backend": "cpu_deterministic", "enabled": True,
                "measured_speedup_percent": 0.0, "warm_p50_ms": m.warm_p50_ms if m else 1.0,
                "warm_p95_ms": m.warm_p95_ms if m else 2.0,
                "peak_memory_mb": m.peak_memory_mb if m else 0.0,
                "failure_rate_percent": m.failure_rate_percent if m else 0.0,
                "numerical_validation": "passed" if not m else m.numerical_validation,
                "reason": outcome.reason}
    return {"backend": outcome.backend, "enabled": True,
            "measured_speedup_percent": m.measured_speedup_percent,
            "warm_p50_ms": m.warm_p50_ms, "warm_p95_ms": m.warm_p95_ms,
            "peak_memory_mb": m.peak_memory_mb, "failure_rate_percent": m.failure_rate_percent,
            "numerical_validation": m.numerical_validation, "reason": outcome.reason,
            "quality": outcome.gates.get("quality", {})}


def mock_calibration_phase3_classified(fingerprint: str = "test") -> dict:
    """Phase 3 mock: a coreml_cpu_gpu reranker qualified on a representative host.

    Mirrors Phase 1's `mock_calibration_deterministic_only` shape; used by tests
    to assert profile-driven backend selection without running the build.
    """
    from ..platform.calibration import CalibrationBundle, CalibrationResult
    return CalibrationBundle(
        fingerprint=fingerprint,
        results=[
            CalibrationResult(
                feature="reranker", backend="coreml_cpu_gpu", enabled=True,
                measured_speedup_percent=30.0, warm_p50_ms=420.0, warm_p95_ms=470.0,
                peak_memory_mb=360.0, failure_rate_percent=0.0,
                numerical_validation="passed", reason="benchmark_qualified",
            ),
            CalibrationResult(
                feature="secret_classifier", backend="cpu_deterministic", enabled=True,
                measured_speedup_percent=0.0, warm_p50_ms=1.0, warm_p95_ms=2.0,
                peak_memory_mb=4.0, failure_rate_percent=0.0,
                numerical_validation="passed", reason="phase2_cpu_model",
            ),
        ]).to_measurements()
