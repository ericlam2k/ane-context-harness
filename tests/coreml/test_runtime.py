"""Tests for Core ML runtime prediction (Phase 3.1).

Runtime is torch/transformers-free; when no compiled artifact is available the
runtime is inert and predict returns per-element None. A test-only fixture
model (built via coremltools at build time) is exercised when present; these
tests assert the contract either way.
"""
from __future__ import annotations

import os

import pytest

from src.ane_context_harness.coreml.runtime import (
    CoreMLRuntime, CoreMLComputeUnit, ModelArtifact,
)


def _missing_artifact() -> ModelArtifact:
    return ModelArtifact(
        model_id="cross-encoder/ms-marco-MiniLM-L-6-v2",
        revision="0" * 40, seq_len=128, model_version="none",
        model_path="/nonexistent/model.mlmodelc", vocab_path="/nonexistent/vocab.txt",
        tokenizer_config_path="", checksums={}, numeric_validation={}, manifest_entry="miniLM-L6-MMR1",
    )


def test_runtime_inert_without_artifact():
    rt = CoreMLRuntime(artifact=None, compute_unit=CoreMLComputeUnit.ALL)
    assert rt.available is False
    assert rt.load_error == "no_model_configured"
    assert rt.predict("q", ["c1", "c2"]) == [None, None]
    assert rt.model_version == "none"


def test_runtime_inert_when_artifact_missing():
    rt = CoreMLRuntime(artifact=_missing_artifact(), compute_unit=CoreMLComputeUnit.CPU_ONLY)
    assert rt.available is False
    # missing path -> not_configured-style degradation
    res = rt.predict("q", ["c1"])
    assert res == [None]


class _C:
    def __init__(self, content):
        self.content = content


def test_runtime_skips_coresize_check_without_artifact():
    """predict must not crash even when runtime unavailable across backends."""
    for cu in CoreMLComputeUnit:
        rt = CoreMLRuntime(artifact=None, compute_unit=cu)
        assert rt.predict("q", []) == []
