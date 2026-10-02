#!/usr/bin/env python3
"""Re-run Gate A + order-preservation validation against BUILT artifacts.

Writes/refreshes numeric_validation.json and metadata.json
(numeric_summary + validation_gates) inside each located artifact directory.
Gate A thresholds are unchanged; order metrics are additive.

Usage (Python <= 3.13 with .[build] installed):
    ~/.venvs/ane-p36/bin/python scripts/revalidate_artifact.py [--seq-len 128 256]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ane_context_harness.coreml.convert import (  # noqa: E402
    MODELS, PHASE3_BUILD_CACHE, _load_pytorch, _download_snapshot,
    _validate_numerics, _emit_artifact_metadata, _build_output_path,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="miniLM-L6-MMR1")
    ap.add_argument("--seq-len", nargs="+", type=int, default=[128, 256])
    ap.add_argument("--artifacts-dir",
                    default=os.path.join(PHASE3_BUILD_CACHE, "artifacts"))
    args = ap.parse_args()

    entry = MODELS[args.entry]
    cache_dir = os.path.join(PHASE3_BUILD_CACHE, "huggingface")
    model_dir = _download_snapshot(entry, cache_dir)
    tok, pt_model = _load_pytorch(entry, model_dir)

    results = {}
    import coremltools as ct  # type: ignore
    for seq_len in args.seq_len:
        art_dir = _build_output_path(args.artifacts_dir, entry, seq_len)
        if not os.path.isdir(art_dir):
            results[seq_len] = {"status": "artifact_not_found", "path": art_dir}
            continue
        model_path = None
        for name in ("model.mlpackage", "model.mlmodelc"):
            p = os.path.join(art_dir, name)
            if os.path.isdir(p):
                model_path = p
                break
        if model_path is None:
            results[seq_len] = {"status": "no_model_file", "path": art_dir}
            continue
        mlmodel = ct.models.MLModel(model_path,
                                    compute_units=ct.ComputeUnit.CPU_ONLY)
        res = _validate_numerics(entry, tok, pt_model, mlmodel, seq_len)
        (Path(art_dir) / "numeric_validation.json").write_text(
            json.dumps(res, indent=2))
        # refresh metadata: keep existing keys, update gates + summary
        meta_path = Path(art_dir) / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta.pop("numeric_summary", None)
        _emit_artifact_metadata(str(art_dir), entry, seq_len, mlmodel,
                                {}, validation=res)
        new_meta = json.loads(meta_path.read_text())
        merged = {**meta, **new_meta}
        if "checksums" in meta:
            merged["checksums"] = meta["checksums"]
        meta_path.write_text(json.dumps(merged, indent=2))
        order = res.get("order_preservation", {})
        results[seq_len] = {
            "status": "validated",
            "gate_a_passed": res.get("passed"),
            "max_abs_logit": res.get("max_abs_logit"),
            "min_cosine": res.get("min_cosine"),
            "spearman": order.get("spearman"),
            "top10_overlap": order.get("top10_overlap"),
            "inversion_rate": order.get("pairwise_inversion_rate"),
            "future_gates_passed": res.get("future_order_gates", {}).get("passed"),
            "worst_probes": order.get("worst_case_fixture_ids"),
        }
    print(json.dumps(results, indent=2))
    ok = all(v.get("status") == "validated" and v.get("gate_a_passed")
             for v in results.values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
