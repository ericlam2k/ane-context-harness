"""Versioned release-evidence bundle: build + checksum verification.

Layout of ``ane-context-harness-evidence-v0.1/``:

    manifest.json            file checksums + all required metadata fields
    METRICS.md               measured / calculated / estimated / unmeasured
    reports/calibration_report.json
    reports/phase5-ab-evaluation.json
    reports/phase5-ab-evaluation.md
    provenance/model_manifest.json
    provenance/numeric_validation.json
    provenance/tokenizer_validation.json
    provenance/conversion_lock.json
    provenance/environment.json
    provenance/fingerprints.json

Privacy: copies reports and fingerprints only. No source code, no fixture
contents, no secrets, no credentials are ever written into the bundle.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _pf
import shutil
import subprocess
import sys
import time
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


def _canonical_hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _git_state(repo_root: Path) -> dict:
    def _run(*args):
        return subprocess.run(["git", "-C", str(repo_root), *args],
                              capture_output=True, text=True, timeout=10)
    try:
        head = _run("rev-parse", "HEAD")
        if head.returncode != 0:
            return {"commit": None, "dirty": None,
                    "status": "not_a_git_repository"}
        dirty = _run("status", "--porcelain")
        return {
            "commit": head.stdout.strip(),
            "dirty": bool(dirty.stdout.strip()),
            "status": "clean" if not dirty.stdout.strip() else "dirty",
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None, "status": "git_unavailable"}


def _package_versions() -> dict:
    def _ver(name):
        try:
            mod = __import__(name)
            return getattr(mod, "__version__", "unknown")
        except Exception:
            return "not_installed"
    return {
        "python": sys.version.split()[0],
        "coremltools": _ver("coremltools"),
        "torch": _ver("torch"),
        "transformers": _ver("transformers"),
        "numpy": _ver("numpy"),
        "huggingface_hub": _ver("huggingface_hub"),
    }


def _find_source_checkpoint(model_id: str) -> dict:
    """Locate + hash the local HF source checkpoint (optional input)."""
    safe = "models--" + model_id.replace("/", "--")
    hub = Path(os.path.expanduser("~/.cache/huggingface/hub")) / safe
    if not hub.is_dir():
        return {"status": "not_available_locally",
                "reason": "huggingface_hub cache not found; revision recorded "
                          "instead of a content hash"}
    for snap in sorted((hub / "snapshots").glob("*")):
        for name in ("model.safetensors", "pytorch_model.bin"):
            p = snap / name
            if p.is_file():
                return {"status": "hashed", "path_hint": name,
                        "sha256": _sha256_file(p),
                        "revision_dir": snap.name}
    return {"status": "not_available_locally",
            "reason": "no weight file in snapshot"}


def _artifact_inputs(storage_base: Path) -> dict:
    """Locate built artifacts (128 required, 256 optional)."""
    arts = storage_base / "phase3" / "build_cache" / "artifacts"
    found = {"required_128": None, "optional_256": None}
    if not arts.is_dir():
        return found
    for name in sorted(os.listdir(arts)):
        d = arts / name
        if not d.is_dir():
            continue
        meta_p = d / "metadata.json"
        if not meta_p.is_file():
            continue
        try:
            meta = _load_json(meta_p)
        except (OSError, ValueError):
            continue
        if meta.get("seq_len") == 128:
            found["required_128"] = d
        elif meta.get("seq_len") == 256:
            found["optional_256"] = d
    return found


def _parse_checksums(artifact_dir: Path) -> dict:
    ck = artifact_dir / "checksums.sha256"
    out = {}
    if ck.is_file():
        for line in ck.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                out[parts[1].strip()] = parts[0].strip()
    return out


def _capability_profile_fingerprint(storage_base: Path) -> str:
    from ..config import build_config
    from ..pipeline import Pipeline
    pipe = Pipeline(build_config({"index": {"storage_path": str(storage_base)}}))
    return _canonical_hash(pipe._profile())


def _harness_config_hash() -> str:
    from ..config import build_config
    return _canonical_hash(build_config())


def _evidence_classification() -> dict:
    return {
        "measured": [
            "agreement cosines and raw-logit differences",
            "warm p50/p95 latency per compute unit",
            "benchmark failure rates",
            "phase5 selection latency (p50/p95) and peak RSS",
            "arm A/B/C token counts and required-evidence recall",
            "gate-B quality metrics (recall@k, nDCG@10, MRR)",
            "cold model-load latency",
        ],
        "calculated": [
            "token-reduction percentages and all aggregation statistics",
            "checksums and fingerprints",
            "task-set and configuration hashes",
            "derived cost figures (from counts under a stated price)",
        ],
        "estimated": [
            "cost_usd figures (price assumption stated in the report)",
            "TTFT sensitivity values (token delta at illustrative prefill rates)",
        ],
        "unmeasured": [
            "energy consumption",
            "time-to-first-token on any real provider/model",
            "provider-reported tokens, cost or tool-call behavior",
            "Neural Engine execution share (coreml_all does not attribute units)",
            "performance on machines other than the tested configuration",
        ],
    }


_METRICS_MD = """# Evidence classification

This bundle separates four kinds of statements. Every number in the included
reports belongs to exactly one category.

## Measured

Produced by executing code on the tested host and reading counters/clocks:

- agreement cosines and raw-logit differences (Gate A, {agreement_pairs} pairs)
- warm p50/p95 latency per compute unit and failure rates
- phase5 selection latency (p50/p95), peak RSS
- arm A/B/C token counts, required-evidence recall, gate-B ranking metrics
- cold model-load latency, prediction counts

## Calculated

Deterministic functions of measurements or inputs:

- token-reduction percentages; every aggregate names its method
  (mean/median/min/max of per-task values, weighted total, totals ratio)
- checksums, fingerprints, task-set hash, configuration hash

## Estimated

Explicitly assumed, never presented as measurements:

- derived cost figures (stated $/M-token price)
- TTFT sensitivity (token delta at illustrative prefill rates)

## Unmeasured

Recorded as unknown; never inferred:

- energy, real-provider TTFT/cost/tool behavior
- Neural Engine execution share (backend `coreml_all` requests all compute
  units; it does not attribute where ops ran)
- performance on any machine other than the tested configuration
"""


def build_bundle(out_dir: str | Path, *, storage_base: str | Path | None = None,
                 reports_dir: str | Path | None = None,
                 repo_root: str | Path | None = None,
                 force: bool = False) -> dict:
    """Create the versioned evidence bundle at ``out_dir``.

    Raises EvidenceError when a REQUIRED input is missing (calibration report,
    phase5 reports, 128-token artifact metadata) so evidence can never be
    silently incomplete.
    """
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        if not force:
            raise EvidenceError(f"{out} exists and is not empty (use force)")
        shutil.rmtree(out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "provenance").mkdir(parents=True, exist_ok=True)

    storage = Path(os.path.expanduser(
        str(storage_base or "~/.ane_context_harness")))
    root = Path(repo_root) if repo_root else _default_repo_root()
    reports = Path(reports_dir) if reports_dir else root / "benchmarks" / "reports"

    # ---- required inputs -------------------------------------------------
    cal_report = storage / "calibration_report.json"
    p5_json = reports / "phase5-ab-evaluation.json"
    p5_md = reports / "phase5-ab-evaluation.md"
    arts = _artifact_inputs(storage)
    art128 = arts["required_128"]
    for label, p in (("calibration report", cal_report),
                     ("phase5 report (json)", p5_json),
                     ("phase5 report (markdown)", p5_md),
                     ("128-token artifact", art128)):
        if p is None or not Path(p).exists():
            raise EvidenceError(f"missing required input: {label} ({p})")

    cal = _load_json(cal_report)
    p5 = _load_json(p5_json)
    meta128 = _load_json(Path(art128) / "metadata.json")

    # ---- copy report/provenance files -----------------------------------
    copies = {
        "reports/calibration_report.json": cal_report,
        "reports/phase5-ab-evaluation.json": p5_json,
        "reports/phase5-ab-evaluation.md": p5_md,
        "provenance/model_manifest.json": Path(art128) / "metadata.json",
        "provenance/numeric_validation.json": Path(art128) / "numeric_validation.json",
        "provenance/tokenizer_validation.json": Path(art128) / "tokenizer_validation.json",
        "provenance/conversion_lock.json": None,   # written below
        "provenance/environment.json": None,       # written below
        "provenance/fingerprints.json": None,      # written below
        "METRICS.md": None,                        # written below
    }
    for rel, src in copies.items():
        if src is None:
            continue
        if not Path(src).exists():
            raise EvidenceError(f"missing required input: {rel} ({src})")
        shutil.copyfile(src, out / rel)

    versions = _package_versions()
    conv_lock = {
        "conversion_dependency_lock": {
            "python": versions["python"],
            "coremltools": versions["coremltools"],
            "torch": versions["torch"],
            "transformers": versions["transformers"],
            "numpy": versions["numpy"],
            "huggingface_hub": versions["huggingface_hub"],
            "lock_kind": "exact installed versions at bundle creation",
        }
    }
    (out / "provenance" / "conversion_lock.json").write_text(
        json.dumps(conv_lock, indent=2), encoding="utf-8")

    machine = _pf.machine()
    env = {
        "python_version": versions["python"],
        "macos_version": _pf.mac_ver()[0] or "unknown",
        "machine_architecture": machine,
        "platform": _pf.platform(),
        "coremltools_version": versions["coremltools"],
        "pytorch_version": versions["torch"],
        "transformers_version": versions["transformers"],
    }
    (out / "provenance" / "environment.json").write_text(
        json.dumps(env, indent=2), encoding="utf-8")

    methodology = (p5.get("provenance") or {}).get("methodology") or {}
    p5_prov = p5.get("provenance") or {}
    coreml_arm = methodology.get("coreml_arm") or {}
    agreement = cal.get("agreement") or {}
    agreement_pairs = agreement.get("n_pairs", 0)
    comp_units = sorted(((cal.get("p36_gates") or {}).get("compute_units") or {}).keys())
    fingerprint = _capability_profile_fingerprint(storage)
    cfg_hash = _harness_config_hash()
    from ..benchmark import BENCHMARK_SCHEMA_VERSION, load_benchmark_tasks
    tasks = load_benchmark_tasks(root / "benchmarks" / "tasks",
                                 repo_total_tokens=None, validate=False)
    from ..benchmark import task_set_hash
    from ..tokens import BACKEND as TOKEN_BACKEND, TOKEN_ESTIMATOR_VERSION

    git = _git_state(root)
    source_ckpt = _find_source_checkpoint(meta128.get("model", ""))
    compiled = {
        "128tok": _parse_checksums(Path(art128)),
    }
    if arts["optional_256"] is not None:
        compiled["256tok"] = _parse_checksums(arts["optional_256"])

    tokenizer_revision = {
        "vocab_sha256": compiled["128tok"].get("tokenizer/vocab.txt"),
        "tokenizer_config_sha256": compiled["128tok"].get(
            "tokenizer/tokenizer_config.json"),
        "source": "content hashes of the tokenizer files shipped in the artifact",
    }

    fingerprints = {
        "capability_profile_fingerprint": fingerprint,
        "harness_configuration_hash": cfg_hash,
        "benchmark_task_set_hash": task_set_hash(tasks),
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "git": git,
        "token_estimator": {"backend": TOKEN_BACKEND,
                            "version": TOKEN_ESTIMATOR_VERSION},
        "index_condition": p5_prov.get("prompt_cache_state", "unspecified"),
        "provider_state": p5_prov.get("provider", "unspecified"),
        "prompt_cache_state": p5_prov.get("prompt_cache_state", "unspecified"),
        "warmup_runs": methodology.get("warmup_runs_excluded"),
        "measured_repetitions": methodology.get("repeats"),
        "compute_units_requested": comp_units,
        "agreement": {
            "n_pairs": agreement_pairs,
            "min_cosine": agreement.get("min_cosine"),
            "max_abs_logit": agreement.get("max_abs_logit"),
            "thresholds": agreement.get("thresholds"),
        },
        "arm_c_backend": coreml_arm.get("backend"),
        "arm_c_artifact": coreml_arm.get("artifact"),
    }
    (out / "provenance" / "fingerprints.json").write_text(
        json.dumps(fingerprints, indent=2), encoding="utf-8")

    classification = _evidence_classification()
    (out / "METRICS.md").write_text(
        _METRICS_MD.format(agreement_pairs=agreement_pairs), encoding="utf-8")

    # ---- manifest --------------------------------------------------------
    files = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            rel = str(p.relative_to(out))
            files[rel] = {"sha256": _sha256_file(p), "bytes": p.stat().st_size}
    files["METRICS.md"]["category"] = "metrics-classification"
    for rel in files:
        if rel.startswith("reports/"):
            files[rel]["category"] = "report"
        elif rel.startswith("provenance/"):
            files[rel]["category"] = "provenance"

    metadata = {
        "phase3_qualification_report": "reports/calibration_report.json",
        "phase5_reports": ["reports/phase5-ab-evaluation.json",
                           "reports/phase5-ab-evaluation.md"],
        "model_id": meta128.get("model"),
        "model_revision": meta128.get("revision"),
        "tokenizer_revision": tokenizer_revision,
        "source_artifact_checksums": source_ckpt,
        "compiled_artifact_checksums": compiled,
        "conversion_dependency_lock": conv_lock["conversion_dependency_lock"],
        "python_version": versions["python"],
        "coremltools_version": versions["coremltools"],
        "pytorch_version": versions["torch"],
        "transformers_version": versions["transformers"],
        "macos_version": env["macos_version"],
        "machine_architecture": machine,
        "compute_units_requested": comp_units,
        "calibration_report": "reports/calibration_report.json",
        "capability_profile_fingerprint": fingerprint,
        "harness_configuration_hash": cfg_hash,
        "benchmark_task_set_hash": task_set_hash(tasks),
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "git_status": git["status"],
        "token_estimator": TOKEN_BACKEND,
        "token_estimator_version": TOKEN_ESTIMATOR_VERSION,
        "warmup_runs": methodology.get("warmup_runs_excluded"),
        "measured_repetitions": methodology.get("repeats"),
        "index_condition": fingerprints["index_condition"],
        "provider_state": fingerprints["provider_state"],
        "prompt_cache_state": fingerprints["prompt_cache_state"],
        "evidence_classification": classification,
    }
    missing_fields = [f for f in REQUIRED_METADATA_FIELDS if f not in metadata]
    if missing_fields:
        raise EvidenceError(f"metadata missing required fields: {missing_fields}")

    manifest = {
        "bundle_name": BUNDLE_NAME,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files,
        "metadata": metadata,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "bundle_dir": str(out),
        "bundle_name": BUNDLE_NAME,
        "files_count": len(files),
        "manifest": str(out / "manifest.json"),
        "git_status": git["status"],
    }


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
            rel = str(p.relative_to(bundle))
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
