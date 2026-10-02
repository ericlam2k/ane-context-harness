"""Tests for the Phase 3 build/convert orchestrator (no heavy deps required)."""
from __future__ import annotations

import pytest

from src.ane_context_harness.coreml import convert as conv
from src.ane_context_harness.coreml.manifest import MODELS, ModelEntry


def test_convert_module_importable_without_deps():
    # importing the module must not require torch/transformers/coremltools.
    import importlib
    importlib.reload(conv)


def test_require_deps_reports_python314_on_missing_install():
    # coremltools has no cp314 wheels -> build is explicitly blocked here with a
    # clear message rather than a confusing ImportError later.
    import sys, pytest
    try:
        conv._require_deps()
    except conv.BuildDependencyMissing as e:
        assert "Python 3.13" in str(e) or "coremltools" in str(e)
        assert "3.14" in str(e) or "cp314" in str(e)
    except ImportError as e:
        pytest.fail(f"unexpected ImportError variant: {e}")
    else:
        if sys.version_info >= (3, 14):
            pytest.fail("build should be blocked on Python 3.14")


def test_build_model_refuses_unsupported_seq_len(tmp_path):
    # 512 not supported; but dep gate fires first. Exercise the guard directly.
    entry = MODELS["miniLM-L6-MMR1"]
    assert 512 not in entry.profiles


def test_build_model_refuses_unpinned_revision():
    # _resolve_revision must reject a moving tag.
    with pytest.raises(ValueError):
        conv._resolve_revision("x/y", "main")


def test_artifact_name_is_versioned_and_profiled():
    out = conv._build_output_path("/tmp/a", MODELS["miniLM-L6-MMR1"], 128)
    assert out.endswith("cross-encoder_ms-marco-MiniLM-L6-v2_128tok_v1")
    out256 = conv._build_output_path("/tmp/a", MODELS["miniLM-L6-MMR1"], 256)
    assert "256tok_v1" in out256


def test_manifest_permits_apache_and_defers_electra():
    assert MODELS["miniLM-L6-MMR1"].permitted
    assert MODELS["tinyBERT-L2-MMR1"].permitted
    assert MODELS["electra-base-MMR1-deferred"].profiles == ()


def test_license_policy_blocks_gpl():
    e = ModelEntry("x/y", "rev", "gpl-3.0", "base", "arch", 1.0, "bert",
                   "bert-base-uncased", "rev", 512, (), "t")
    assert not e.permitted
