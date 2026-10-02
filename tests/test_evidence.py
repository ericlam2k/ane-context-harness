"""Release-evidence bundle: build, checksum verification, privacy, metadata."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ane_context_harness.evidence import (BUNDLE_NAME, EvidenceError,
                                          build_bundle, verify_bundle)
from ane_context_harness.evidence.bundle import REQUIRED_METADATA_FIELDS


def _write(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj,
                 encoding="utf-8")
    return p


@pytest.fixture()
def sources(tmp_path):
    """Minimal but structurally real evidence inputs."""
    storage = tmp_path / "storage"
    art = storage / "phase3" / "build_cache" / "artifacts" / "cross-encoder_ms-marco-MiniLM-L6-v2_128tok_v1"
    art.mkdir(parents=True)
    _write(art / "metadata.json", {
        "model": "cross-encoder/ms-marco-MiniLM-L6-v2",
        "revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "seq_len": 128, "artifact_version": "v1"})
    _write(art / "numeric_validation.json",
           {"max_abs_logit": 0.016, "min_cosine": 1.0, "passed": True})
    _write(art / "tokenizer_validation.json",
           {"passed": True, "probes": [{"probe": i, "pass": True} for i in range(8)]})
    (art / "checksums.sha256").write_text(
        "aa" * 32 + "  model.mlpackage/weights/weight.mlprogram\n"
        + "bb" * 32 + "  tokenizer/vocab.txt\n"
        + "cc" * 32 + "  tokenizer/tokenizer_config.json\n", encoding="utf-8")
    _write(storage / "calibration_report.json", {
        "agreement": {"n_pairs": 1000, "min_cosine": 1.0, "max_abs_logit": 0.044,
                      "thresholds": {"min_cosine": 0.999, "max_abs_logit": 0.05}},
        "p36_gates": {"release_gate_pass": True,
                      "compute_units": {"coreml_all@128tok": {"warm_p50_ms": 1.7}}},
        "measurements": {"reranker": {"backend": "coreml_all", "enabled": True}}})

    reports = tmp_path / "reports"
    _write(reports / "phase5-ab-evaluation.json", {
        "provenance": {
            "methodology": {"repeats": 5, "warmup_runs_excluded": 1,
                            "coreml_arm": {"backend": "coreml_all",
                                           "artifact": "x@rev"}},
            "provider": "none invoked (local evaluation; no network)",
            "prompt_cache_state": "cold index; no provider prompt cache"}})
    _write(reports / "phase5-ab-evaluation.md", "# phase 5 report\n")

    repo_root = tmp_path / "repo"
    tasks = repo_root / "benchmarks" / "tasks"
    _write(tasks / "t1.json", {
        "task_id": "t1", "task": "q", "repository_id": "r",
        "difficulty": "small", "category": "unit", "token_budget": 100,
        "required_chunks": [{"path": "a.py"}], "challenge": "c",
        "expected_retrieval_behavior": "e", "expected_final_package": "p",
        "ground_truth_provenance": "manual"})
    return {"storage_base": storage, "reports_dir": reports, "repo_root": repo_root}


def _build(tmp_path, sources, name="bundle-v0.1", **kw):
    out = tmp_path / name
    kw.update(sources)
    return out, build_bundle(out, **kw)


def test_build_and_verify_roundtrip(tmp_path, sources):
    out, info = _build(tmp_path, sources)
    assert info["bundle_name"] == BUNDLE_NAME
    assert Path(info["manifest"]).is_file()
    result = verify_bundle(out)
    assert result["ok"], result
    assert result["checked"] == info["files_count"]
    assert not result["missing"] and not result["changed"] and not result["unexpected"]


def test_manifest_carries_all_required_metadata(tmp_path, sources):
    out, _ = _build(tmp_path, sources, "b-meta")
    manifest = json.loads((out / "manifest.json").read_text())
    meta = manifest["metadata"]
    missing = [f for f in REQUIRED_METADATA_FIELDS if f not in meta]
    assert not missing, missing
    # spot-check values
    assert meta["model_revision"].startswith("233902d")
    assert meta["conversion_dependency_lock"]["python"].startswith("3.")
    assert meta["benchmark_schema_version"]
    assert meta["warmup_runs"] == 1 and meta["measured_repetitions"] == 5
    assert meta["compute_units_requested"] == ["coreml_all@128tok"]
    assert set(meta["evidence_classification"]) == {
        "measured", "calculated", "estimated", "unmeasured"}


def test_verify_detects_changed_file(tmp_path, sources):
    out, _ = _build(tmp_path, sources, "b-tamper")
    target = out / "reports" / "phase5-ab-evaluation.json"
    target.write_text(target.read_text() + " ", encoding="utf-8")
    result = verify_bundle(out)
    assert not result["ok"]
    assert "reports/phase5-ab-evaluation.json" in result["changed"]


def test_verify_detects_missing_file(tmp_path, sources):
    out, _ = _build(tmp_path, sources, "b-missing")
    (out / "provenance" / "environment.json").unlink()
    result = verify_bundle(out)
    assert not result["ok"]
    assert "provenance/environment.json" in result["missing"]


def test_verify_detects_unexpected_file(tmp_path, sources):
    out, _ = _build(tmp_path, sources, "b-extra")
    (out / "reports" / "smuggled.txt").write_text("payload", encoding="utf-8")
    result = verify_bundle(out)
    assert not result["ok"]
    assert "reports/smuggled.txt" in result["unexpected"]


def test_verify_missing_manifest(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = verify_bundle(empty)
    assert not result["ok"]
    assert result["errors"]


def test_build_fails_when_required_input_missing(tmp_path, sources):
    (sources["storage_base"] / "calibration_report.json").unlink()
    with pytest.raises(EvidenceError, match="calibration report"):
        build_bundle(tmp_path / "nope", **sources)


def test_build_refuses_nonempty_dir_without_force(tmp_path, sources):
    out = tmp_path / "occupied"
    out.mkdir()
    (out / "stray").write_text("x")
    with pytest.raises(EvidenceError, match="not empty"):
        build_bundle(out, **sources)
    # force=True replaces it
    build_bundle(out, force=True, **sources)
    assert verify_bundle(out)["ok"]


def test_bundle_contains_no_source_code_or_fixture_content(tmp_path, sources):
    """Privacy: reports + provenance only; no repo/fixture source text."""
    marker = "def calculate_discount(price, rate)"
    out, _ = _build(tmp_path, sources, "b-privacy")
    for p in out.rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert marker not in text, p


def test_cli_evidence_verify_exit_codes(tmp_path, sources, capsys):
    from ane_context_harness.cli import main
    out, _ = _build(tmp_path, sources, "b-cli")
    assert main(["evidence", "verify", str(out)]) == 0
    (out / "METRICS.md").write_text("tampered", encoding="utf-8")
    assert main(["evidence", "verify", str(out)]) == 1
