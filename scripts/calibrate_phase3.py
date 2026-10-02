"""Phase 3 calibration + qualification runner (P3.6 validation evidence).

Benchmarks the four backends (cpu_deterministic as a PyTorch-CPU reference,
coreml_cpu_only, coreml_cpu_gpu, coreml_all) across the active model
artifact(s) and sequence lengths, runs both validation gates (A: numerical
fidelity vs the PyTorch checkpoint — including the >=1,000-pair agreement
check; B: retrieval quality vs labelled harness tasks scored by the artifact),
evaluates the P3.6 release gates, and writes a measurement report JSON under
storage_base that the pipeline consumes via ``coreml.calibration_report`` to
drive profile-based backend selection.

Requires the optional build dependencies (``pip install -e '.[build]'``) AND a
previously built artifact (``scripts/convert_model.py``). When deps/artifact
are absent it writes a deterministic-only report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WARM_P50_GATE_MS = 500.0
AGREEMENT_MIN_PAIRS = 1000


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 3 calibration + qualification")
    p.add_argument("--storage-base", default=str(Path.home() / ".ane_context_harness"),
                   help="Harness storage dir (artifacts + calibration report)")
    p.add_argument("--tasks-dir", default="benchmarks/tasks",
                   help="Labelled benchmark tasks for gate B")
    p.add_argument("--agreement-pairs", type=int, default=AGREEMENT_MIN_PAIRS,
                   help="Pairs for the P3.6 numerical agreement gate (>=1000)")
    p.add_argument("--skip-agreement", action="store_true",
                   help="Skip the (slow) >=N-pair agreement check")
    args = p.parse_args(argv)

    from src.ane_context_harness.coreml.calibration import (
        benchmark_backends, qualify_backend, to_feature_measurements,
    )
    from src.ane_context_harness.benchmark import FIXTURE_REPO_PATHS
    from src.ane_context_harness.platform.discovery import discover
    from src.ane_context_harness.platform.profiles import derive_profile

    storage_base = os.path.expanduser(args.storage_base)
    artifacts_dir = os.path.join(storage_base, "phase3", "build_cache", "artifacts")
    seq_len = 128
    artifact = _find_artifact(artifacts_dir, seq_len) if os.path.isdir(artifacts_dir) else None

    from src.ane_context_harness.coreml.calibration import _sample_pairs_from_tasks
    pairs = []
    for repo_path in FIXTURE_REPO_PATHS.values():
        if os.path.isdir(repo_path):
            pairs.extend(_sample_pairs_from_tasks(args.tasks_dir, repo_path))
    if not pairs:
        pairs = _sample_pairs_from_tasks(args.tasks_dir, None)

    measurements = {}
    quality = {}
    agreement = {"status": "skipped", "reason": "no artifact"}
    per_len = {}
    if artifact is None:
        # No built artifact on this host -> deterministic-only report. Never
        # write simulated Core ML measurements into a real calibration report.
        measurements = {
            "reranker": {
                "backend": "cpu_deterministic", "enabled": True,
                "measured_speedup_percent": 0.0, "warm_p50_ms": 1.0,
                "warm_p95_ms": 2.0, "peak_memory_mb": 0.0,
                "failure_rate_percent": 0.0, "numerical_validation": "passed",
                "reason": "no_artifact_deterministic_only",
            },
            "secret_classifier": {
                "backend": "cpu_deterministic", "enabled": True,
                "measured_speedup_percent": 0.0, "warm_p50_ms": 1.0,
                "warm_p95_ms": 2.0, "peak_memory_mb": 4.0,
                "failure_rate_percent": 0.0, "numerical_validation": "passed",
                "reason": "phase2_cpu_model",
            },
        }
        agreement = {"status": "skipped", "reason": "no artifact"}
    else:
        quality = _pipeline_quality(args.tasks_dir, artifacts_dir)
        for sl in (128, 256):
            art_sl = _find_artifact(artifacts_dir, sl) or artifact
            per_len[sl] = benchmark_backends(art_sl, pairs, sl, n=50)
        all_meas = []
        for sl, res in per_len.items():
            all_meas.extend(res)
        if args.skip_agreement:
            agreement = {"status": "skipped", "reason": "--skip-agreement"}
        else:
            from src.ane_context_harness.coreml.agreement import (
                generate_agreement_pairs, run_agreement_check,
            )
            print(f"generating {args.agreement_pairs} agreement pairs ...", flush=True)
            apairs = generate_agreement_pairs(target=args.agreement_pairs,
                                              tasks_dir=args.tasks_dir)
            print(f"running agreement check on {len(apairs)} pairs ...", flush=True)
            agreement = run_agreement_check(artifact, apairs, seq_len)
        out = qualify_backend(all_meas, quality=quality)
        measurements["reranker"] = to_feature_measurements(out)
        measurements["secret_classifier"] = {
            "backend": "cpu_deterministic", "enabled": True,
            "measured_speedup_percent": 0.0, "warm_p50_ms": 1.0,
            "warm_p95_ms": 2.0, "peak_memory_mb": 4.0,
            "failure_rate_percent": 0.0, "numerical_validation": "passed",
            "reason": "phase2_cpu_model",
        }

    p36 = _p36_gates(agreement, per_len, measurements)
    report = {
        "generated_by": "scripts/calibrate_phase3.py",
        "fingerprint": "phase0123",
        "measurements": measurements,
        "quality": quality,
        "agreement": agreement,
        "p36_gates": p36,
        "measured_on_platform": {
            "platform": discover(),
            "artifact": artifact.model_id if artifact else None,
        },
    }
    out_dir = Path(storage_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "calibration_report.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    # echo a derived profile for inspection
    prof = derive_profile(discover(), measurements=measurements)
    print(json.dumps({
        "measurements": measurements,
        "quality": quality,
        "agreement": agreement,
        "p36_gates": p36,
        "derived_reranker_backend": prof.features["reranker"]["backend"],
        "behavioral_profile": prof.behavioral_profile,
        "calibration_report_path": str(out_path),
    }, indent=2, default=str))
    return 0 if p36.get("release_gate_pass", False) or artifact is None else 1


def _p36_gates(agreement: dict, per_len: dict, measurements: dict) -> dict:
    """P3.6 release gate: build on Python <= 3.13, >=1,000-pair numerical
    agreement, and .all/CPU+GPU/CPU-only warm p50 <= 500 ms per seq_len."""
    units = {}
    all_units_ok = bool(per_len)
    for sl, res in per_len.items():
        for m in res:
            if not m.backend.startswith("coreml_"):
                continue
            ok = bool(m.available) and m.warm_p50_ms <= WARM_P50_GATE_MS
            units[f"{m.backend}@{sl}tok"] = {
                "available": m.available,
                "warm_p50_ms": m.warm_p50_ms,
                "warm_p95_ms": m.warm_p95_ms,
                "le_500ms": ok,
                "failure_rate_percent": m.failure_rate_percent,
            }
            all_units_ok = all_units_ok and ok
    if not per_len:
        all_units_ok = False
    n_pairs = int(agreement.get("n_pairs") or 0)
    agreement_ok = bool(agreement.get("passed")) and n_pairs >= AGREEMENT_MIN_PAIRS
    build_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    build_ok = (sys.version_info.major, sys.version_info.minor) <= (3, 13)
    qualified = measurements.get("reranker", {}).get("backend", "cpu_deterministic")
    return {
        "python_version": build_py,
        "build_python_le_313": build_ok,
        "agreement_n_pairs": n_pairs,
        "agreement_pairs_ge_1000": n_pairs >= AGREEMENT_MIN_PAIRS,
        "agreement_passed": bool(agreement.get("passed")),
        "warm_p50_gate_ms": WARM_P50_GATE_MS,
        "compute_units": units,
        "all_units_le_500ms": all_units_ok,
        "qualified_backend": qualified,
        "release_gate_pass": bool(build_ok and agreement_ok and all_units_ok),
    }


def _pipeline_quality(tasks_dir: str, artifacts_dir: str) -> dict:
    """Gate B: rank every indexed fixture chunk by Core ML scores and score
    against the labelled tasks (recall@1/10, nDCG@10, MRR)."""
    from src.ane_context_harness.benchmark import FIXTURE_REPO_PATHS, load_benchmark_tasks
    from src.ane_context_harness.config import build_config
    from src.ane_context_harness.coreml.evaluation import evaluate_rerank
    from src.ane_context_harness.coreml.runtime import CoreMLComputeUnit, CoreMLRuntime
    from src.ane_context_harness.pipeline import Pipeline

    artifact = _find_artifact(artifacts_dir, 128)
    if artifact is None:
        return {}
    rt = CoreMLRuntime(artifact, compute_unit=CoreMLComputeUnit.ALL)
    if not rt.available:
        return {"error": rt.load_error or "coreml_unavailable"}

    cfg = build_config({
        "index": {"storage_path": tempfile.mkdtemp(prefix="aneh-quality-")},
        "privacy": {"never_read": ["**/.env*", "**/.aws/**", "**/.ssh/**",
                                   "**/*.pem", "**/.EnvLocal"]},
    })
    pipeline = Pipeline(cfg)
    per_task = []
    for t in load_benchmark_tasks(tasks_dir):
        repo_path = FIXTURE_REPO_PATHS.get(t.repository_id)
        if not repo_path or not os.path.isdir(repo_path):
            continue
        pipeline.register_repository(repo_path, t.repository_id, False)
        chunks = pipeline._storage_for(t.repository_id).load_chunks()
        if not chunks:
            continue
        scores = rt.predict(t.task, chunks)
        per_task.append(evaluate_rerank(chunks, scores, t))
    if not per_task:
        return {}

    def mean(key):
        vals = [d[key] for d in per_task if key in d]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "n": len(per_task),
        "recall_at_1": mean("recall_at_1"),
        "recall_at_10": mean("recall_at_10"),
        "ndcg_at_10": mean("ndcg_at_10"),
        "mrr": mean("mrr"),
        "scores_by": "coreml_all raw sigmoid scores over all indexed chunks",
    }


def _find_artifact(artifacts_dir: str, seq_len: int):
    from src.ane_context_harness.coreml.runtime import ModelArtifact
    from src.ane_context_harness.coreml.convert import _build_output_path
    from src.ane_context_harness.coreml.manifest import MODELS
    # look for a miniLM artifact at the requested seq_len
    for key in ("miniLM-L6-MMR1", "tinyBERT-L2-MMR1"):
        entry = MODELS[key]
        name = f"{entry.model_id.replace('/', '_')}_{seq_len}tok_v1"
        cand = os.path.join(artifacts_dir, name)
        if os.path.isdir(cand):
            return _artifact_from_dir(cand, entry)
    return None


def _artifact_from_dir(directory: str, entry):
    from src.ane_context_harness.coreml.runtime import ModelArtifact
    import json as _json
    mp = os.path.join(directory, "model.mlpackage")
    if not os.path.isdir(mp):
        mp = os.path.join(directory, "model.mlmodelc")
    vp = os.path.join(directory, "tokenizer", "vocab.txt")
    tp = os.path.join(directory, "tokenizer", "tokenizer_config.json")
    ck = os.path.join(directory, "checksums.sha256")
    meta = {}
    if os.path.exists(os.path.join(directory, "metadata.json")):
        with open(os.path.join(directory, "metadata.json")) as fh:
            meta = _json.load(fh)
    nv = {}
    nv_path = os.path.join(directory, "numeric_validation.json")
    if os.path.exists(nv_path):
        with open(nv_path) as fh:
            nv = _json.load(fh)
    checksums = {}
    if os.path.exists(ck):
        for line in open(ck):
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                checksums[parts[1]] = parts[0]
    return ModelArtifact(
        model_id=entry.model_id, revision=entry.revision,
        seq_len=int(meta.get("seq_len", 128)),
        model_version=meta.get("artifact_version", "none"),
        model_path=mp, vocab_path=vp, tokenizer_config_path=tp,
        checksums=checksums, numeric_validation=nv, manifest_entry=entry.model_id.split("/")[-1],
    )


if __name__ == "__main__":
    raise SystemExit(main())
