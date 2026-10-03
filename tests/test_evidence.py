"""Frozen release-evidence bundle: checksum verification only (portable line).

Bundle construction is ANE-release infrastructure (private distribution).
These tests cover verify_bundle against hand-built manifests plus the real
frozen in-tree bundle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ane_context_harness.evidence import verify_bundle
from ane_context_harness.evidence.bundle import REQUIRED_METADATA_FIELDS

FROZEN = Path(__file__).resolve().parents[1] / "ane-context-harness-evidence-v0.1"


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _bundle(tmp_path, name="b", extra_meta=None, files=None):
    out = tmp_path / name
    payloads = {"reports/r.json": '{"ok": true}',
                "provenance/environment.json": '{"python": "3.14"}'}
    payloads.update(files or {})
    for rel, text in payloads.items():
        _write(out / rel, text)
    from ane_context_harness.evidence.bundle import REQUIRED_METADATA_FIELDS
    meta = {f: "test-value" for f in REQUIRED_METADATA_FIELDS}
    meta.update(extra_meta or {})
    manifest = {"bundle": "test", "metadata": meta, "files": {
        rel: {"sha256": _sha(out / rel), "bytes": (out / rel).stat().st_size}
        for rel in payloads}}
    _write(out / "manifest.json", json.dumps(manifest, indent=2))
    return out


def test_verify_roundtrip_ok(tmp_path):
    out = _bundle(tmp_path)
    result = verify_bundle(out)
    assert result["ok"], result
    assert result["checked"] == 2
    assert not result["missing"] and not result["changed"] and not result["unexpected"]


def test_verify_detects_changed_file(tmp_path):
    out = _bundle(tmp_path)
    (out / "reports" / "r.json").write_text("tampered", encoding="utf-8")
    result = verify_bundle(out)
    assert not result["ok"]
    assert "reports/r.json" in result["changed"]


def test_verify_detects_missing_file(tmp_path):
    out = _bundle(tmp_path)
    (out / "provenance" / "environment.json").unlink()
    result = verify_bundle(out)
    assert not result["ok"]
    assert "provenance/environment.json" in result["missing"]


def test_verify_detects_unexpected_file(tmp_path):
    out = _bundle(tmp_path)
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


def test_verify_requires_metadata_fields(tmp_path):
    out = _bundle(tmp_path)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["metadata"]["python_version"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_bundle(out)
    assert not result["ok"]
    assert any("python_version" in e for e in result["errors"])
    assert set(REQUIRED_METADATA_FIELDS) > {"python_version"}


def test_frozen_bundle_verifies(tmp_path):
    if not (FROZEN / "manifest.json").is_file():
        return
    result = verify_bundle(FROZEN)
    assert result["ok"], result


def test_cli_evidence_verify_exit_codes(tmp_path, capsys):
    from ane_context_harness.cli import main
    out = _bundle(tmp_path, "b-cli")
    assert main(["evidence", "verify", str(out)]) == 0
    (out / "reports" / "r.json").write_text("tampered", encoding="utf-8")
    assert main(["evidence", "verify", str(out)]) == 1
