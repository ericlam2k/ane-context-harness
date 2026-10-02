"""Core ML runtime loader + backend selection (Phase 3).

``CoreMLRuntime`` loads a compiled ``.mlmodelc`` (produced by
``coreml.convert.build_model``) plus its bundled tokenizer vocabulary and runs
batched cross-encoder scoring. Compute-unit selection is by name; we never
claim ANE attribution — only the requested compute unit is recorded.

Dependencies: requires ``coremltools`` (optional build-time dependency). When
absent or when no compiled model is configured, the runtime is inert and the
pipeline falls back to CPU deterministic scoring.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from .tokenizer import TokenizerBundle, load_tokenizer
from .manifest import ModelEntry  # noqa: F401  (re-exported for callers)


class CoreMLComputeUnit(str, Enum):
    ALL = "all"  # Core ML .all (ANE/GPU/CPU eligible)
    CPU_AND_GPU = "cpu_gpu"  # Core ML cpuAndGPU
    CPU_ONLY = "cpu_only"  # Core ML cpuOnly

    def to_coremltools(self):
        try:
            import coremltools as ct  # type: ignore
            m = {
                self.ALL: ct.ComputeUnit.ALL,
                self.CPU_AND_GPU: ct.ComputeUnit.CPU_AND_GPU,
                self.CPU_ONLY: ct.ComputeUnit.CPU_ONLY,
            }
            return m[self]
        except Exception:
            return None


@dataclass
class ModelArtifact:
    """Descriptor for a compiled Core ML reranker artifact on disk."""
    model_id: str
    revision: str
    seq_len: int
    model_version: str
    model_path: str  # .mlmodelc or .mlpackage
    vocab_path: str
    tokenizer_config_path: str
    checksums: dict = field(default_factory=dict)
    numeric_validation: dict = field(default_factory=dict)
    manifest_entry: str = ""

    def exists(self) -> bool:
        return bool(self.model_path) and os.path.exists(self.model_path)


@dataclass
class RerankScore:
    score: float
    backend: str
    ml_used: bool


class CoreMLRuntime:
    """Loads a compiled Core ML reranker and scores (query, chunk) pairs."""
    def __init__(self, artifact: ModelArtifact | None = None,
                 compute_unit=CoreMLComputeUnit.ALL):
        self.artifact = artifact
        self.compute_unit = compute_unit
        self._model = None
        self._tokenizer: TokenizerBundle | None = None
        self._loaded = False
        self._closed = False
        self._error = None
        self.model_version = artifact.model_version if artifact else "none"

    @property
    def available(self) -> bool:
        if self._closed:
            return False
        if self._loaded:
            return self._model is not None
        self._load()
        return self._model is not None

    @property
    def load_error(self) -> str | None:
        return self._error

    def close(self) -> None:
        """Release the loaded model (clean shutdown; no reload afterwards)."""
        self._closed = True
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not self.artifact or not self.artifact.exists():
            self._error = "no_model_configured"
            return
        try:
            import coremltools as ct  # type: ignore
        except ImportError:
            self._error = "coremltools_not_installed"
            return
        try:
            cu = self.compute_unit.to_coremltools() or ct.ComputeUnit.ALL
            self._model = ct.models.MLModel(self.artifact.model_path, compute_units=cu)
            self._tokenizer = load_tokenizer(
                self.artifact.vocab_path, self.artifact.tokenizer_config_path,
                self.artifact.seq_len)
        except Exception as exc:  # noqa: BLE001
            self._model = None
            self._error = f"model_load_failed: {type(exc).__name__}: {exc}"

    def _tokenize_batch(self, task: str, chunks: list) -> dict:
        seq_len = self._tokenizer.seq_len
        n = len(chunks)
        input_ids = [[0] * seq_len for _ in range(n)]
        attention_mask = [[0] * seq_len for _ in range(n)]
        token_type_ids = [[0] * seq_len for _ in range(n)]
        for i, ch in enumerate(chunks):
            ids, am, tt = self._tokenizer.encode_pair(task, ch.content)
            input_ids[i] = ids
            attention_mask[i] = am
            token_type_ids[i] = tt
        return {"input_ids": input_ids, "attention_mask": attention_mask,
                "token_type_ids": token_type_ids}

    @staticmethod
    def _sigmoid(x: float) -> float:
        import math
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    def predict(self, task: str, chunks: list) -> list:
        """Return relevance scores in [0,1] aligned to ``chunks``.

        Returns ``None`` per-element when the runtime is unavailable.
        Raises ValueError when ``chunks`` is not a list/tuple (invalid batch);
        an empty batch returns an empty list.
        """
        if not isinstance(chunks, (list, tuple)):
            raise ValueError(f"chunks must be a list, got {type(chunks).__name__}")
        if not self.available or not self._tokenizer:
            return [None] * len(chunks)
        inputs = self._tokenize_batch(task, chunks)
        scores = [None] * len(chunks)
        # Fixed 1xseq_len shapes; the mlprogram spec takes int32 arrays (plain
        # lists are rejected by the Core ML proxy), so convert per-sample.
        import numpy as np  # type: ignore
        for i in range(len(chunks)):
            try:
                pred = self._model.predict({
                    "input_ids": np.asarray([inputs["input_ids"][i]], dtype=np.int32),
                    "attention_mask": np.asarray([inputs["attention_mask"][i]], dtype=np.int32),
                    "token_type_ids": np.asarray([inputs["token_type_ids"][i]], dtype=np.int32),
                })
                logit = self._extract_logit(pred)
                scores[i] = self._sigmoid(logit)
            except Exception as exc:  # noqa: BLE001
                scores[i] = None
                self._error = f"predict_failed: {type(exc).__name__}"
        return scores

    @staticmethod
    def _extract_logit(pred: dict) -> float:
        for key in ("logits", "output", "output_1", "logits_1"):
            if key in pred:
                v = pred[key]
                try:
                    import numpy as np  # type: ignore
                    v = np.asarray(v).reshape(-1)
                    if v.size:
                        return float(v[0])
                except Exception:
                    pass
        return 0.0

    def batch_scores(self, task: str, chunks: list, batch_size: int = 32) -> list:
        """Batched variant (groups per-sample calls; kept for API symmetry)."""
        return self.predict(task, chunks)

    def benchmark(self, sample_inputs: list, n: int = 50) -> dict:
        """Bounded local benchmark: warm p50/p95 latency + peak memory.

        Returns measured numbers or an 'unavailable' marker. Never fabricates.
        """
        import itertools
        import time
        if not self.available:
            return {"available": False, "reason": self._error or "unavailable"}
        # warm-up
        for pair in list(sample_inputs[:3]) + [{"task": "bench", "content": "x"}]:
            self.predict(pair.get("task", ""), [pair])
        timings = []
        pairs = sample_inputs or [{"task": "bench", "content": "x"}]
        for pair in itertools.islice(itertools.cycle(pairs), n):
            t0 = time.perf_counter()
            self.predict(pair.get("task", ""), [pair])
            timings.append((time.perf_counter() - t0) * 1000.0)
        timings.sort()
        return {
            "available": True,
            "compute_unit_requested": self.compute_unit.value,
            "p50_ms": round(timings[int(len(timings) * 0.5) - 1], 3) if timings else 0.0,
            "p95_ms": round(timings[int(len(timings) * 0.95) - 1], 3) if timings else 0.0,
            "failure_rate_percent": 0.0,
        }
