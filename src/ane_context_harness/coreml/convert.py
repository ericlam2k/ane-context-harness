"""Phase 3 model conversion: PyTorch checkpoint -> versioned Core ML artifact.

This module is **build-time only**. It is importable without any heavy
dependencies; the heavy imports (torch / transformers / coremltools /
huggingface_hub) happen lazily inside :func:`build_model`, which raises a clear
``BuildDependencyMissing`` error if they are absent.

Contract:
  * Downloads the model + tokenizer vocab into an explicit build cache
    (``PHASE3_BUILD_CACHE``); **never** at runtime or from the default HF
    cache alone.
  * Fixed-shape INT token inputs (``input_ids``, ``attention_mask``,
    ``token_type_ids``) for a pinned sequence length (128 or 256).
  * Direct PyTorch -> Core ML conversion (traced ``torch.jit``) — no
    intermediate ONNX/Quantized graph in Phase 3.
  * Versioned ``.mlpackage`` + ``tokenizer/vocab.txt`` + ``tokenizer_config.json``.
  * ``metadata.json``, ``checksums.sha256`` and ``LICENSE.txt`` emitted.
  * Numerical validation: Core ML logits vs PyTorch checkpoint (cosine /
    max-abs tolerance). Conversion fidelity is gate A; ranking-quality is
    gate B (see coreml.calibration).
  * Atomic publish: build to a ``.tmp`` dir, validate, then move into place.
  * Deferred models (empty ``profiles``) and non-permitted licenses are refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .manifest import MODELS, ModelEntry, PERMITTED_LICENSES

PHASE3_BUILD_CACHE = os.environ.get(
    "ANEHARNESS_PHASE3_BUILD_CACHE",
    str(Path.home() / ".ane_context_harness" / "phase3" / "build_cache"),
)

_ARTIFACT_VERSION = "v1"
# Numerical fidelity tolerances (gate A).
_COSINE_TOL = 0.999
_MAX_ABS_LOGIT = 0.05
_VAL_SAMPLES = 32


class BuildDependencyMissing(ImportError):
    pass


def _require_deps():
    # coremltools ships no cp314 wheels; Phase 3 conversion requires Python 3.13.
    if sys.version_info >= (3, 14):
        raise BuildDependencyMissing(
            "Phase 3 conversion requires Python 3.13 on macOS/arm64: coremltools "
            "does not publish cp314 wheels. Use a Python 3.13 environment.")
    missing = []
    for mod in ("torch", "transformers", "coremltools", "huggingface_hub", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise BuildDependencyMissing(
            "Phase 3 conversion requires the optional build dependencies: "
            f"{', '.join(missing)}. Install with: pip install -e '.[build]'")
    if sys.platform != "darwin":
        raise BuildDependencyMissing(
            "Phase 3 conversion requires macOS with Metal/ANE (coremltools).")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    if os.path.isdir(path):
        # .mlpackage is a directory bundle: hash relpaths + contents, sorted.
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for name in sorted(files):
                fp = os.path.join(root, name)
                h.update(os.path.relpath(fp, path).encode("utf-8"))
                h.update(b"\0")
                with open(fp, "rb") as fh:
                    for block in iter(lambda: fh.read(1 << 20), b""):
                        h.update(block)
        return h.hexdigest()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _resolve_revision(model_id: str, explicit_revision: str | None) -> str:
    """Return a concrete commit hash. Refuses moving tags/refs — builds always use
    an exact, immutable commit pin from the manifest."""
    moving = {"", None, "main", "master", "latest", "HEAD", "head"}
    if explicit_revision in moving:
        raise ValueError(
            f"Refusing to build {model_id}: revision must be a pinned commit, "
            f"not a moving ref ({explicit_revision!r}).")
    if len(explicit_revision) != 40 or not all(c in "0123456789abcdef" for c in explicit_revision):
        raise ValueError(
            f"Refusing to build {model_id}: revision is not a 40-char commit hash.")
    return explicit_revision


def _build_output_path(output_dir: str, entry: ModelEntry, seq_len: int) -> str:
    safe = entry.model_id.replace("/", "_")
    name = f"{safe}_{seq_len}tok_{_ARTIFACT_VERSION}"
    return os.path.join(output_dir, name)


def _download_snapshot(entry: ModelEntry, cache_dir: str) -> str:
    """Materialize the model + tokenizer vocab at the pinned revision into the
    build cache. Returns the directory containing the snapshot."""
    from huggingface_hub import snapshot_download  # type: ignore

    model_rev = _resolve_revision(entry.model_id, entry.revision)
    vocab_rev = _resolve_revision(entry.tokenizer_vocab_id, entry.tokenizer_revision)
    model_dir = snapshot_download(
        repo_id=entry.model_id, revision=model_rev,
        cache_dir=cache_dir, repo_type="model",
        allow_patterns=["config.json", "vocab.txt", "tokenizer*.json",
                        "special_tokens_map.json", "*.safetensors",
                        "pytorch_model.bin"],
    )
    snapshot_download(
        repo_id=entry.tokenizer_vocab_id, revision=vocab_rev,
        cache_dir=cache_dir, repo_type="model",
        allow_patterns=["config.json", "vocab.txt", "tokenizer*.json",
                        "special_tokens_map.json"],
    )
    return model_dir


def _load_pytorch(entry: ModelEntry, model_dir: str):
    from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
    import torch  # type: ignore

    tok = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    return tok, model


def _make_traced(entry: ModelEntry, tok, model, seq_len: int):
    """Trace the PyTorch model with fixed-shape inputs for the given length."""
    import torch  # type: ignore

    class _LogitsOnly(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, input_ids, attention_mask, token_type_ids):
            out = self.inner(input_ids=input_ids, attention_mask=attention_mask,
                             token_type_ids=token_type_ids)
            return out.logits if hasattr(out, "logits") else out["logits"]

    torch.manual_seed(0)
    input_ids = torch.randint(0, tok.vocab_size, (1, seq_len), dtype=torch.long)
    attention_mask = torch.ones(1, seq_len, dtype=torch.long)
    token_type_ids = torch.zeros(1, seq_len, dtype=torch.long)
    example = (input_ids, attention_mask, token_type_ids)
    traced = torch.jit.trace(_LogitsOnly(model), example, strict=False)
    traced.eval()
    return traced, {
        "input_ids": (1, seq_len),
        "attention_mask": (1, seq_len),
        "token_type_ids": (1, seq_len),
    }


def _tokenizer_probe_set() -> list:
    """(query, passage) fixtures spanning NL, code, paths, stack traces, Unicode."""
    return [
        ("fix the incorrect discount calculation",
         "def calculate_discount(price, rate): return price - (price * rate)"),
        ("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature auth",
         "Authorization: Bearer token here"),
        ("postgres://user:secretpw@db.internal:5432/synth",
         "db_url connects to the synth database on db.internal"),
        ("src/ane_context_harness/pipeline.py line 42",
         "the storage base path under ~/.ane_context_harness"),
        ("TypeError: unsupported operand",
         "Traceback (most recent call last)\n  File \"x.py\", line 3, in <module>"),
        ("contact ops@example.com or admin@company.com",
         "support email addresses are redacted placeholders"),
        ("café résumé naïve — unicode path src/ünïcödé.py",
         "paths with non-ascii characters must tokenize identically"),
        ("x" * 500, "y" * 500),  # long input -> exercises truncation
    ]


def _validate_tokenizer(tok, stdlib_tok, seq_len: int) -> dict:
    """Gate: the pure-stdlib tokenizer must EXACTLY match the pinned HF
    BertTokenizerFast on input_ids/attention_mask/token_type_ids for all probes."""
    import numpy as np  # type: ignore
    probes = _tokenizer_probe_set()
    mismatches = []
    for i, (q, c) in enumerate(probes):
        enc = tok(q, c, truncation=True, padding="max_length",
                  max_length=seq_len, return_tensors="pt")
        hf = {
            "input_ids": enc["input_ids"][0].tolist(),
            "attention_mask": enc["attention_mask"][0].tolist(),
            "token_type_ids": enc["token_type_ids"][0].tolist(),
        }
        mine = stdlib_tok.encode_pair(q, c)  # (input_ids, attention_mask, token_type_ids)
        got = {"input_ids": mine[0], "attention_mask": mine[1], "token_type_ids": mine[2]}
        for k in ("input_ids", "attention_mask", "token_type_ids"):
            if got[k] != hf[k]:
                mismatches.append({"probe": i, "field": k,
                                   "expected_len": len(hf[k]), "actual_len": len(got[k]),
                                   "expected_head": hf[k][:8], "actual_head": got[k][:8]})
    return {"passed": not mismatches, "mismatches": mismatches[:5],
            "n_probes": len(probes)}


def _convert_to_coreml(entry: ModelEntry, traced, input_shapes: dict, seq_len: int):
    import numpy as np  # type: ignore
    import coremltools as ct  # type: ignore

    # int32 keeps token ids exact (fp16 would corrupt ids > 2048); a named
    # float32 output gives consumers a stable "logits" key instead of "var_N".
    inputs = [
        ct.TensorType(name=name, shape=shape, dtype=np.int32)
        for name, shape in input_shapes.items()
    ]
    outputs = [ct.TensorType(name="logits", dtype=np.float32)]
    mlmodel = ct.convert(traced, inputs=inputs, outputs=outputs,
                         minimum_deployment_target=ct.target.iOS17)
    return mlmodel


def _validate_numerics(entry: ModelEntry, tok, pt_model, mlmodel, seq_len: int) -> dict:
    """Gate A: compare Core ML **raw logits** to the PyTorch checkpoint.

    Both sides are the pre-sigmoid logits of the sequence-classification head
    (shape [1, 1] for this binary cross-encoder). We never apply sigmoid here —
    the runtime applies it once at scoring time, so comparing raw logits avoids
    a double-sigmoid mismatch.

    Gate A (unchanged): per-sample min cosine >= 0.999 and max abs logit
    <= 0.05 decides ``passed``. Order-preservation metrics (p50/p95/p99/max
    abs diff, vector cosine, Spearman, top-5/top-10 overlap, pairwise
    inversion rate, sign flips, worst-case probe ids) are computed over the
    full probe set and the suggested future-release gates are evaluated and
    recorded — they do not retroactively change Gate A.
    """
    import torch  # type: ignore
    import numpy as np  # type: ignore
    from .validation_metrics import (FUTURE_ORDER_GATES, GATE_A_THRESHOLDS,
                                     evaluate_gates, order_preservation_metrics)

    pt_model.eval()
    max_abs = 0.0
    cos_min = 1.0
    pt_vec: list = []
    cm_vec: list = []
    probe_ids: list = []
    samples = _numeric_validation_samples()
    for idx, (q, c) in enumerate(samples[:_VAL_SAMPLES]):
        enc = tok(q, c, truncation=True, padding="max_length",
                  max_length=seq_len, return_tensors="pt")
        with torch.no_grad():
            pt_logits = pt_model(**enc).logits
        cm_preds = mlmodel.predict({
            "input_ids": enc["input_ids"].numpy().astype(np.int32),
            "attention_mask": enc["attention_mask"].numpy().astype(np.int32),
            "token_type_ids": enc["token_type_ids"].numpy().astype(np.int32),
        })
        cm_logits = _extract_logits(cm_preds)
        pt_np = np.asarray(pt_logits).reshape(-1)
        cm_np = np.asarray(cm_logits).reshape(-1)
        # shape must match (both [1] after squeeze for a single output logit)
        assert pt_np.shape == cm_np.shape, (pt_np.shape, cm_np.shape)
        max_abs = max(max_abs, float(np.max(np.abs(pt_np - cm_np))))
        denom = float(np.linalg.norm(pt_np) * np.linalg.norm(cm_np))
        if denom > 0:
            cos_min = min(cos_min, float(np.dot(pt_np, cm_np) / denom))
        pt_vec.append(float(pt_np[0]))
        cm_vec.append(float(cm_np[0]))
        probe_ids.append(f"probe_{idx}")

    gate_a_pass = cos_min >= GATE_A_THRESHOLDS["min_cosine"] and max_abs <= GATE_A_THRESHOLDS["max_abs_logit"]
    order = order_preservation_metrics(pt_vec, cm_vec, probe_ids)
    future_results = evaluate_gates(order, FUTURE_ORDER_GATES)
    return {
        "max_abs_logit": round(max_abs, 6), "min_cosine": round(cos_min, 6),
        "compared_raw_logits": True,
        "passed": gate_a_pass,
        "order_preservation": order,
        "gate_a_thresholds": dict(GATE_A_THRESHOLDS),
        "future_order_gates": {
            "configured": dict(FUTURE_ORDER_GATES),
            "results": future_results,
            "passed": all(future_results.values()) if future_results else None,
            "enforced": False,
            "note": "suggested future-release gates; recorded, not enforced "
                    "against this build (Gate A governs `passed`)",
        },
    }


def _numeric_validation_samples() -> list:
    """Diverse (query, passage) probe pairs for numerical fidelity."""
    return [
        ("how does the discount calculation work in python",
         "def calculate_discount(price, rate): return price - (price * rate)"),
        ("fix the bug in apply_coupon",
         "rate = coupons.get(coupon_code, 0)"),
        ("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig the token",
         "authorization header carries the bearer token for auth"),
        ("user contact admin@company.com for access",
         "email ops@example.com is the support address"),
        ("postgres://user:pw@db.internal:5432/synth",
         "the database url connects to the synth database"),
        ("price - price * rate returns the discounted total",
         "discount = price * rate  # WRONG: should be price - (price * rate)"),
    ]


def _extract_logits(preds: dict) -> Any:
    """Robustly pull logits out of a Core ML prediction dict."""
    import numpy as np  # type: ignore[import-not-found]
    for key in ("logits", "output", "output_1", "logits_1"):
        if key in preds:
            return preds[key]
    # fall back to the first multi-element numeric output
    for v in preds.values():
        a = np.asarray(v)  # type: ignore[name-defined]
        if a.size > 1:
            return a
    raise RuntimeError("no logit output found in Core ML prediction")


def _emit_artifact_metadata(staging_dir: str, entry: ModelEntry, seq_len: int,
                            mlmodel, checksums: dict,
                            validation: dict | None = None) -> None:
    from .validation_metrics import FUTURE_ORDER_GATES, GATE_A_THRESHOLDS
    meta = {"model": entry.model_id, "revision": entry.revision,
            "artifact_version": _ARTIFACT_VERSION, "seq_len": seq_len,
            "architecture": entry.architecture, "parameters_millions": entry.parameters_millions,
            "license": entry.license, "tokenizer": entry.tokenizer,
            "base_model": entry.base_model, "purpose": entry.purpose,
            "validation_gates": {
                "gate_a": dict(GATE_A_THRESHOLDS),
                "future_order_gates": dict(FUTURE_ORDER_GATES),
            }}
    if validation:
        meta["numeric_summary"] = {
            "passed": validation.get("passed"),
            "max_abs_logit": validation.get("max_abs_logit"),
            "min_cosine": validation.get("min_cosine"),
            "order_preservation": validation.get("order_preservation"),
            "future_order_gates": validation.get("future_order_gates"),
        }
    (Path(staging_dir) / "metadata.json").write_text(json.dumps(meta, indent=2))
    (Path(staging_dir) / "checksums.sha256").write_text(
        "\n".join(f"{h}  {name}" for name, h in checksums.items()) + "\n")
    license_text = ("Licensed under the Apache License, Version 2.0 (the \"License\"); "
                    "you may not use this file except in compliance with the License.")
    (Path(staging_dir) / "LICENSE.txt").write_text(license_text + "\n")


def build_model(entry_key: str, seq_len: int,
                output_dir: str | None = None,
                validate_numerics: bool = True) -> dict:
    """Build a versioned, validated Core ML reranker artifact.

    Steps: resolve pinned revision -> snapshot to build cache -> trace PyTorch
    -> convert to Core ML (fixed-shape) -> bundle tokenizer -> validate
    numerics -> atomic publish. Returns a descriptor dict.
    """
    _require_deps()
    entry = MODELS[entry_key]
    if not entry.permitted:
        raise ValueError(f"Refusing build: license '{entry.license}' not permitted.")
    if seq_len not in entry.profiles:
        raise ValueError(
            f"seq_len {seq_len} not in allowed profiles {entry.profiles} for {entry_key}.")
    if seq_len not in (128, 256):
        raise ValueError("Phase 3 supports only 128 and 256 token profiles.")

    output_dir = output_dir or os.path.join(PHASE3_BUILD_CACHE, "artifacts")
    os.makedirs(output_dir, exist_ok=True)
    final_path = _build_output_path(output_dir, entry, seq_len)

    cache_dir = os.path.join(PHASE3_BUILD_CACHE, "huggingface")
    model_dir = _download_snapshot(entry, cache_dir)
    tok, pt_model = _load_pytorch(entry, model_dir)

    # Gate T (P3.6): the pure-stdlib runtime tokenizer must exactly match the
    # pinned HF tokenizer before any conversion time is spent.
    from .tokenizer import TokenizerBundle
    stdlib_tok = TokenizerBundle(os.path.join(model_dir, "vocab.txt"), seq_len)
    tok_gate = _validate_tokenizer(tok, stdlib_tok, seq_len)
    if not tok_gate["passed"]:
        raise RuntimeError(
            f"Tokenizer fidelity gate FAILED for {entry_key} seq={seq_len}: {tok_gate}")

    traced, input_shapes = _make_traced(entry, tok, pt_model, seq_len)
    mlmodel = _convert_to_coreml(entry, traced, input_shapes, seq_len)

    # Stage artifact.
    tmp_dir = final_path + ".staging"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    mlmodel.save(os.path.join(tmp_dir, "model.mlpackage"))
    tok_dir = os.path.join(tmp_dir, "tokenizer")
    os.makedirs(tok_dir, exist_ok=True)
    # bundle the plain vocab + tokenizer config (runtime uses these)
    vocab_src = getattr(tok, "vocab_file", None) or os.path.join(model_dir, "vocab.txt")
    if not os.path.exists(vocab_src):
        raise RuntimeError(
            f"vocab.txt not found for {entry_key} (looked at {vocab_src!r}); "
            "the runtime tokenizer bundle cannot be built without it")
    shutil.copyfile(vocab_src, os.path.join(tok_dir, "vocab.txt"))
    (Path(tok_dir) / "tokenizer_config.json").write_text(json.dumps({
        "model_type": entry.tokenizer, "max_seq_len": seq_len,
        "pad_id": 0, "cls_id": 101, "sep_id": 102, "unk_id": 100, "mask_id": 103,
    }, indent=2))

    checksums = {
        "model.mlpackage": _sha256(os.path.join(tmp_dir, "model.mlpackage")),
        "tokenizer/vocab.txt": _sha256(os.path.join(tok_dir, "vocab.txt")) if os.path.exists(os.path.join(tok_dir, "vocab.txt")) else "missing",
    }
    (Path(tmp_dir) / "tokenizer_validation.json").write_text(
        json.dumps(tok_gate, indent=2))
    desc = {"numeric_validation": True, "tokenizer_validation": tok_gate}
    validation = None
    if validate_numerics:
        res = _validate_numerics(entry, tok, pt_model, mlmodel, seq_len)
        validation = res
        (Path(tmp_dir) / "numeric_validation.json").write_text(json.dumps(res, indent=2))
        ok = res.get("passed", False)
        desc["numeric_validation"] = res
        if not ok:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(
                f"Numerical fidelity gate A FAILED for {entry_key} seq={seq_len}: {res}")
    _emit_artifact_metadata(tmp_dir, entry, seq_len, mlmodel, checksums,
                            validation=validation)

    if os.path.exists(final_path):
        shutil.rmtree(final_path)
    os.replace(tmp_dir, final_path)

    return {
        "entry_key": entry_key, "model_id": entry.model_id, "revision": entry.revision,
        "seq_len": seq_len, "output_path": final_path,
        "artifact_version": _ARTIFACT_VERSION, "license": entry.license,
        "numeric_validation": desc, "atomic": True,
    }
