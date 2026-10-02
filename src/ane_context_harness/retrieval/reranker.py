"""Reranker facade with profile-driven backend selection.

Backends (Phase 1/3):
- cpu_deterministic : reuses the deterministic initial_score (always available).
- coreml_all / coreml_cpu_gpu / coreml_cpu_only : Core ML cross-encoder reranker,
  activated ONLY when the capability profile qualifies it (calibration passed)
  AND a compiled ``.mlmodelc`` artifact is present on disk.

Selection is independent of indexing/retrieval/provider logic.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..coreml.runtime import CoreMLRuntime, CoreMLComputeUnit, ModelArtifact
from ..platform.profiles import CapabilityProfile


@dataclass
class RerankDecision:
    backend: str
    ml_used: bool
    fallback: bool
    reason: str
    model_version: str


def _profile_reranker_backend(profile: dict) -> str | None:
    """Inspect the serialized capability profile to choose a backend.

    Returns a CoreML backend name only if the profile benchmark-qualified the
    Core ML backend; otherwise None (caller uses deterministic).
    """
    features = (profile or {}).get("features", {})
    reranker = features.get("reranker", {})
    backend = reranker.get("backend", "cpu_deterministic")
    if backend in ("coreml_all", "coreml_cpu_gpu", "coreml_cpu_only"):
        return backend
    return None


def _compute_unit_for(name: str) -> CoreMLComputeUnit:
    return {
        "coreml_all": CoreMLComputeUnit.ALL,
        "coreml_cpu_gpu": CoreMLComputeUnit.CPU_AND_GPU,
        "coreml_cpu_only": CoreMLComputeUnit.CPU_ONLY,
    }.get(name, CoreMLComputeUnit.ALL)


class CPUDeterministicReranker:
    name = "cpu_deterministic"

    def rerank(self, task, chunks, top_n):
        # No ML: return None scores (caller keeps initial_score as final).
        return [None] * len(chunks)


class CoreMLReranker:
    name = "coreml"

    def __init__(self, runtime: CoreMLRuntime):
        self.runtime = runtime

    def rerank(self, task, chunks, top_n):
        if not self.runtime.available:
            return [None] * len(chunks)
        return self.runtime.batch_scores(task, chunks, batch_size=32)


class RerankerFacade:
    """Resolves a reranker from the capability profile; falls back safely.

    ``model_artifact`` is the optional compiled Core ML artifact descriptor. The
    Core ML backend is only activated when BOTH the profile qualifies it AND an
    artifact exists and loads successfully; otherwise the deterministic path is
    used and the decision records the fallback reason.

    Resolution is memoized (one runtime/model load per facade) and, when a
    ``metrics`` LifecycleMetrics is supplied, construction/load/prediction are
    counted. ``close()`` releases the loaded model (clean shutdown).
    """
    def __init__(self, profile: dict | CapabilityProfile,
                 model_artifact: ModelArtifact | None = None,
                 metrics=None):
        self.profile = profile.to_dict() if isinstance(profile, CapabilityProfile) else (profile or {})
        self.model_artifact = model_artifact
        self.metrics = metrics
        self._resolved = None

    def resolve(self):
        # Resolve once per facade: loading the .mlpackage takes seconds and the
        # pipeline calls decision() + rerank() around the same profile/artifact.
        if self._resolved is not None:
            return self._resolved
        result = self._resolve_uncached()
        self._resolved = result
        return result

    def _count(self, key: str, n: int = 1) -> None:
        if self.metrics is not None:
            self.metrics.incr(key, n)

    def _resolve_uncached(self):
        name = _profile_reranker_backend(self.profile)
        if name is None:
            # Profile chose the deterministic CPU path (no ML qualified). Not a fallback.
            return CPUDeterministicReranker(), RerankDecision(
                backend="cpu_deterministic", ml_used=False, fallback=False,
                reason="deterministic_only_no_ml_qualified", model_version="none")
        try:
            has_artifact = bool(self.model_artifact and self.model_artifact.exists())
            if not has_artifact:
                return CPUDeterministicReranker(), RerankDecision(
                    backend="cpu_deterministic", ml_used=False, fallback=True,
                    reason="coreml_model_not_bundled", model_version="none")
            rt = CoreMLRuntime(self.model_artifact, compute_unit=_compute_unit_for(name))
            self._count("runtime_construction_count")
            if rt.available:
                self._count("model_load_count")
                return CoreMLReranker(rt), RerankDecision(
                    backend=name, ml_used=True, fallback=False,
                    reason="profile_qualified_and_loaded",
                    model_version=rt.model_version or "loaded")
            return CPUDeterministicReranker(), RerankDecision(
                backend="cpu_deterministic", ml_used=False, fallback=True,
                reason=rt.load_error or "coreml_load_failed", model_version="none")
        except Exception as exc:  # noqa: BLE001
            return CPUDeterministicReranker(), RerankDecision(
                backend="cpu_deterministic", ml_used=False, fallback=True,
                reason=f"coreml_load_error:{type(exc).__name__}", model_version="none")

    def rerank(self, task, chunks, top_n):
        reranker, _decision = self.resolve()
        scores = reranker.rerank(task, chunks, top_n)
        self._count("prediction_count", max(1, len(chunks)))
        return scores

    def decision(self):
        _, d = self.resolve()
        return d

    def close(self) -> None:
        """Release the loaded model (idempotent; safe on fallback facades)."""
        if self._resolved is None:
            return
        reranker, _decision = self._resolved
        rt = getattr(reranker, "runtime", None)
        if rt is not None and hasattr(rt, "close"):
            rt.close()
        self._resolved = None
