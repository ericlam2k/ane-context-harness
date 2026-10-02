"""Tests for the conversion orchestrator (Phase 3 build-time).

These run without torch/transformers/coremltools by exercising the
orchestration + gating layer (manifest lookups, profile validation,
license refusal, dependency-gated entry point).
"""
from __future__ import annotations

import sys

import pytest

from src.ane_context_harness.coreml import convert as conv
from src.ane_context_harness.coreml.manifest import MODELS


def test_require_deps_gate():
    """The build-dependency gate fails loudly where conversion cannot run,
    and passes where it can (build venv, Python 3.13 + `.[build]`).

    Targets `_require_deps()` directly so the check never triggers a real
    conversion (slow) in environments that have the dependencies.
    """
    if sys.version_info >= (3, 14) or sys.platform != "darwin":
        with pytest.raises(conv.BuildDependencyMissing, match="Python 3.13|macOS"):
            conv._require_deps()
        return
    try:
        for mod in ("torch", "transformers", "coremltools", "huggingface_hub", "numpy"):
            __import__(mod)
        deps_present = True
    except ImportError:
        deps_present = False
    if deps_present:
        conv._require_deps()  # must not raise in a build-capable environment
    else:
        with pytest.raises(conv.BuildDependencyMissing, match=r"\[build\]"):
            conv._require_deps()


def test_miniLM_512_is_deferred_in_manifest():
    # 512-token profile is deliberately deferred from Phase 3.
    e = MODELS["miniLM-L6-MMR1"]
    assert 128 in e.profiles and 256 in e.profiles
    assert 512 not in e.profiles


def test_artifacts_dir_helpers():
    out = conv._build_output_path("/tmp/art", MODELS["miniLM-L6-MMR1"], 128)
    assert "128tok_v1" in out
    out2 = conv._build_output_path("/tmp/art", MODELS["miniLM-L6-MMR1"], 256)
    assert "256tok_v1" in out2


def test_resolve_revision_requires_pin():
    with pytest.raises(ValueError):
        conv._resolve_revision("cross-encoder/ms-marco-MiniLM-L6-v2", None)


def test_resolve_revision_uses_pin():
    pin = MODELS["miniLM-L6-MMR1"].revision
    assert conv._resolve_revision("any/id", pin) == pin


def test_sha256_is_stable():
    import os, tempfile
    p = tempfile.mktemp()
    open(p, "wb").write(b"abc")
    assert conv._sha256(p) == conv._sha256(p)
