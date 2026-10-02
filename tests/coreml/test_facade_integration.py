"""Integration: a qualified profile + valid artifact activates CoreMLRuntime (Phase 3.6).

Proves the RerankerFacade selects the Core ML reranker (ml_used=True) instead of
the deterministic scorer when the capability profile qualifies a coreml backend
AND a compiled artifact exists. Uses a stub runtime in place of the real
coremltools-backed CoreMLRuntime so the test is dependency-free, then asserts
the production wiring (profile -> artifact -> CoreMLReranker -> batch_scores).
"""
from __future__ import annotations

import os

from src.ane_context_harness.coreml.calibration import mock_calibration_phase3_classified
from src.ane_context_harness.coreml.runtime import ModelArtifact
from src.ane_context_harness.platform.profiles import derive_profile
from src.ane_context_harness.retrieval.reranker import RerankerFacade, CoreMLReranker
import src.ane_context_harness.retrieval.reranker as reranker_mod


DISC = {
    "machine_id": "abc123",
    "hardware": {"architecture": "arm64", "is_apple_silicon": True, "unified_memory_bytes": 17179869184},
    "software": {"macos_version": "14.0", "python_version": "3.14.0"},
    "devices": {"coreml_available": True, "neural_engine_observed": True},
    "runtime": {"compute_mode": "deterministic_only"},
}


class _StubChunk:
    def __init__(self, content, path="f.py", line=1):
        self.content = content; self.path = path
        self.start_line = line; self.end_line = line


class StubRuntime:
    """Stand-in for CoreMLRuntime when coremltools is unavailable in tests."""
    def __init__(self, artifact, compute_unit=None):
        self.artifact = artifact
        self.compute_unit = compute_unit
        self.available = True
        self.model_version = "stub-model-v1"

    def batch_scores(self, task, chunks, batch_size=32):
        # deterministic stand-in scores so the wiring (not the model) is tested
        return [round(0.5 + 0.01 * (i % 10), 4) for i in range(len(chunks))]


def _qualified_profile():
    return derive_profile(DISC, measurements=mock_calibration_phase3_classified("integration")).to_dict()


def _make_artifact(tmpdir):
    mp = os.path.join(tmpdir, "model.mlpackage")
    os.makedirs(mp)
    vp = os.path.join(tmpdir, "tokenizer", "vocab.txt")
    os.makedirs(os.path.dirname(vp))
    open(vp, "w").write("[PAD]\n[UNK]\n[CLS]\n[SEP]\nhello\nworld\n")
    return ModelArtifact(
        model_id="cross-encoder/ms-marco-MiniLM-L6-v2",
        revision="233902d" + "0" * 33, seq_len=128, model_version="phase3-build-v1",
        model_path=mp, vocab_path=vp,
        tokenizer_config_path=os.path.join(tmpdir, "tokenizer", "tokenizer_config.json"),
        checksums={}, numeric_validation={"passed": True}, manifest_entry="miniLM-L6-MMR1",
    )


def test_qualified_profile_with_artifact_activates_coreml(monkeypatch, tmp_path):
    art = _make_artifact(str(tmp_path))
    # Inject the stub runtime into the facade's construction path.
    monkeypatch.setattr(reranker_mod, "CoreMLRuntime", StubRuntime)

    facade = RerankerFacade(_qualified_profile(), model_artifact=art)
    reranker, decision = facade.resolve()

    assert isinstance(reranker, CoreMLReranker)
    assert decision.backend == "coreml_cpu_gpu"  # what the mock qualified
    assert decision.ml_used is True
    assert decision.fallback is False
    assert decision.model_version == "stub-model-v1"

    chunks = [_StubChunk(f"chunk {i}") for i in range(3)]
    scores = reranker.rerank("fix the discount bug", chunks, top_n=3)
    assert scores == [0.5, 0.51, 0.52]
    assert facade.decision().ml_used is True


def test_no_artifact_degrades_to_deterministic(monkeypatch, tmp_path):
    monkeypatch.setattr(reranker_mod, "CoreMLRuntime", StubRuntime)
    facade = RerankerFacade(_qualified_profile(), model_artifact=None)
    reranker, decision = facade.resolve()
    # No artifact path -> deterministic fallback, even though profile qualified coreml.
    from src.ane_context_harness.retrieval.reranker import CPUDeterministicReranker
    assert isinstance(reranker, CPUDeterministicReranker)
    assert decision.backend == "cpu_deterministic"
    assert decision.fallback is True
    assert decision.reason == "coreml_model_not_bundled"


def test_unqualified_profile_does_not_invoke_runtime(monkeypatch, tmp_path):
    calls = {"n": 0}
    class CountingStub:
        def __init__(self, *a, **k):
            calls["n"] += 1
            self.available = True
            self.model_version = "v"
        def batch_scores(self, *a, **k):
            return [1.0] * len(a[1])
    monkeypatch.setattr(reranker_mod, "CoreMLRuntime", CountingStub)
    # default profile (DETERMINISTIC_ONLY) -> no coreml backend requested
    prof = derive_profile(
        {**DISC, "devices": {"coreml_available": False, "neural_engine_observed": False}}
    ).to_dict()
    art = _make_artifact(str(tmp_path))
    facade = RerankerFacade(prof, model_artifact=art)
    d = facade.decision()
    assert d.backend == "cpu_deterministic"
    assert calls["n"] == 0  # runtime never constructed
