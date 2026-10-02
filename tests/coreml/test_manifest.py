"""Tests for the immutable model manifest + license policy (Phase 3)."""
from __future__ import annotations

from src.ane_context_harness.coreml.manifest import MODELS, PERMITTED_LICENSES


def test_miniLM_is_primary_and_permitted():
    e = MODELS["miniLM-L6-MMR1"]
    assert e.model_id == "cross-encoder/ms-marco-MiniLM-L6-v2"
    assert e.permitted
    assert e.license == "apache-2.0"
    assert 128 in e.profiles and 256 in e.profiles
    assert 512 not in e.profiles  # 512 deferred
    assert e.tokenizer == "bert"


def test_tinyBERT_is_latency_fallback_and_permitted():
    e = MODELS["tinyBERT-L2-MMR1"]
    assert e.model_id == "cross-encoder/ms-marco-TinyBERT-L2-v2"
    assert e.permitted
    assert e.architecture.startswith("TinyBERT")


def test_electra_is_deferred_with_no_profiles():
    e = MODELS["electra-base-MMR1-deferred"]
    assert e.profiles == ()
    assert "deferred" in e.purpose.lower()


def test_all_active_models_have_real_pinned_revisions():
    for key, e in MODELS.items():
        if "deferred" in key:
            continue
        # 40-char hex commit (not a moving tag)
        assert len(e.revision) == 40
        assert all(c in "0123456789abcdef" for c in e.revision)
        assert len(e.tokenizer_revision) == 40


def test_license_policy_is_restrictive():
    assert "apache-2.0" in PERMITTED_LICENSES
    assert "gpl-3.0" not in PERMITTED_LICENSES
