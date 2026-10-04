"""Frozen release-evidence bundle: checksum verification (portable line).

Verifies ``manifest.json`` checksums + required metadata fields of a frozen
bundle such as ``ane-context-harness-evidence-v0.1/``. Bundle *construction*
is ANE-release infrastructure and lives in the private distribution.

Privacy: reads reports and fingerprints only. No source code, no fixture
contents, no secrets, no credentials are ever read out of the bundle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BUNDLE_NAME = "ane-context-harness-evidence-v0.1"
BUNDLE_SCHEMA_VERSION = "evidence-1"

# Metadata fields the bundle must carry (checked by verify_metadata_fields).
REQUIRED_METADATA_FIELDS = (
    "phase3_qualification_report",
    "phase5_reports",
    "model_id",
    "model_revision",
    "tokenizer_revision",
    "source_artifact_checksums",
    "compiled_artifact_checksums",
    "conversion_dependency_lock",
    "python_version",
    "coremltools_version",
    "pytorch_version",
    "transformers_version",
    "macos_version",
    "machine_architecture",
    "compute_units_requested",
    "calibration_report",
    "capability_profile_fingerprint",
    "harness_configuration_hash",
    "benchmark_task_set_hash",
    "benchmark_schema_version",
    "git_commit",
    "git_dirty",
    "token_estimator",
    "token_estimator_version",
    "warmup_runs",
    "measured_repetitions",
    "index_condition",
    "provider_state",
    "prompt_cache_state",
    "evidence_classification",
)


class EvidenceError(RuntimeError):
    """Evidence bundle build failed (missing required input, etc.)."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def verify_bundle(bundle_dir: str | Path) -> dict:
    """Recalculate checksums; report missing/changed/unexpected files.

    ``ok`` is False when the manifest is missing/incomplete, any listed file
    is missing or changed, or unknown files are present. Never raises on
    findings — callers translate ``ok`` into an exit code.
    """
    bundle = Path(bundle_dir)
    result = {"bundle_dir": str(bundle), "ok": False, "checked": 0,
              "missing": [], "changed": [], "unexpected": [],
              "errors": []}
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        result["errors"].append("manifest.json not found")
        return result
    try:
        manifest = _load_json(manifest_path)
    except (OSError, ValueError) as exc:
        result["errors"].append(f"manifest.json unreadable: {exc}")
        return result

    files = manifest.get("files") or {}
    if not files:
        result["errors"].append("manifest lists no files")
    for rel, info in files.items():
        p = bundle / rel
        if not p.is_file():
            result["missing"].append(rel)
            continue
        if _sha256_file(p) != info.get("sha256"):
            result["changed"].append(rel)
        else:
            result["checked"] += 1

    listed = set(files) | {"manifest.json"}
    for p in sorted(bundle.rglob("*")):
        if p.is_file():
            # Forward slashes on every platform: bundle manifests are
            # cross-platform evidence (Windows str() would emit backslashes).
            rel = p.relative_to(bundle).as_posix()
            if rel not in listed:
                result["unexpected"].append(rel)

    meta = manifest.get("metadata") or {}
    meta_missing = [f for f in REQUIRED_METADATA_FIELDS if f not in meta]
    if meta_missing:
        result["errors"].append(f"manifest metadata missing fields: {meta_missing}")

    result["ok"] = (not result["missing"] and not result["changed"]
                    and not result["unexpected"] and not result["errors"]
                    and result["checked"] == len(files) and len(files) > 0)
    return result
