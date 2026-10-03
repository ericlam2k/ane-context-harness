"""Deterministic reranker facade.

The portable line ships one backend: cpu_deterministic reuses the
deterministic initial_score (always available). Hardware-accelerated
reranking lives in the private distribution, never here.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..platform.profiles import CapabilityProfile


@dataclass
class RerankDecision:
    backend: str
    ml_used: bool
    fallback: bool
    reason: str
    model_version: str


def _profile_reranker_backend(profile: dict) -> str | None:
    """Portable line: always None (caller uses deterministic)."""
    return None


class CPUDeterministicReranker:
    name = "cpu_deterministic"

    def rerank(self, task, chunks, top_n):
        # No ML: return None scores (caller keeps initial_score as final).
        return [None] * len(chunks)



class RerankerFacade:
    """Deterministic-only facade (portable line).

    Always resolves CPUDeterministicReranker; the decision records why.
    ``model_artifact`` is accepted for call compatibility and ignored.
    """

    def __init__(self, profile: dict | CapabilityProfile,
                 model_artifact=None,
                 metrics=None):
        self.profile = profile.to_dict() if isinstance(profile, CapabilityProfile) else (profile or {})
        self.metrics = metrics
        self._resolved = None

    def resolve(self):
        if self._resolved is not None:
            return self._resolved
        result = (CPUDeterministicReranker(), RerankDecision(
            backend="cpu_deterministic", ml_used=False, fallback=False,
            reason="deterministic_only_no_ml_qualified", model_version="none"))
        self._resolved = result
        return result

    def rerank(self, task, chunks, top_n):
        reranker, _decision = self.resolve()
        return reranker.rerank(task, chunks, top_n)

    def decision(self):
        _, d = self.resolve()
        return d

    def close(self) -> None:
        """Idempotent; nothing to release on the portable line."""
        self._resolved = None
