"""P3.6 gate: numerical agreement between the Core ML artifact and the pinned
PyTorch checkpoint over >= 1,000 (query, passage) pairs.

Pair generation is deterministic (fixed seed, local files only) so the check is
reproducible. Agreement is measured on RAW logits (pre-sigmoid), mirroring
``convert._validate_numerics``: min cosine >= 0.999 and max abs logit delta
<= 0.05 across all pairs. Heavy imports (torch/transformers/coremltools) are
lazy so the module stays importable on build-less hosts.
"""
from __future__ import annotations

import os
import random

from ..benchmark import load_benchmark_tasks

DEFAULT_MIN_PAIRS = 1000
_COSINE_TOL = 0.999
_MAX_ABS_LOGIT = 0.05
_SEED = 20261002
_SOURCE_ROOTS = ("src/ane_context_harness", "tests/fixtures")
_SOURCE_SUFFIXES = (".py", ".ts", ".js", ".json", ".md", ".yaml", ".yml", ".txt")
_QUERY_TEMPLATES = (
    "how does {name} work",
    "fix the bug in {name}",
    "what is {name}",
    "{name} implementation details",
    "where is {name} defined",
    "error traceback in {name}",
    "{name} usage example",
    "related functions for {name}",
    "tests for {name}",
    "{name} configuration",
)


def _read_passages(roots, min_len: int = 40, max_len: int = 2048) -> list:
    passages = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fn in sorted(filenames):
                if not fn.endswith(_SOURCE_SUFFIXES):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read(max_len)
                except (OSError, UnicodeDecodeError):
                    continue
                if len(text) >= min_len:
                    passages.append((path, text))
    return passages


def generate_agreement_pairs(target: int = DEFAULT_MIN_PAIRS,
                             tasks_dir: str = "benchmarks/tasks",
                             source_roots=None) -> list:
    """Deterministic (query, passage) pairs spanning tasks, file paths and
    content-derived queries. Returns at most ``target`` pairs; raises when the
    corpus cannot support ``target`` (so a short run never silently passes)."""
    roots = list(source_roots) if source_roots else list(_SOURCE_ROOTS)
    passages = _read_passages(roots)
    if not passages:
        raise ValueError(f"no readable passages under {roots}")

    queries = []
    try:
        for t in load_benchmark_tasks(tasks_dir):
            queries.append(t.task)
            queries.extend(rc["path"] for rc in t.required_chunks if rc.get("path"))
    except (OSError, ValueError):
        pass
    if not queries:
        queries = ["how does the discount calculation work"]

    pairs, seen = [], set()
    for q in queries:
        for path, text in passages:
            if (q, path) not in seen:
                seen.add((q, path))
                pairs.append((q, text))
    capacity = len(passages) * len(_QUERY_TEMPLATES)
    idx = 0
    while len(pairs) < target and idx < capacity:
        path, text = passages[idx % len(passages)]
        name = os.path.splitext(os.path.basename(path))[0]
        q = _QUERY_TEMPLATES[(idx // len(passages)) % len(_QUERY_TEMPLATES)].format(name=name)
        if (q, path) not in seen:
            seen.add((q, path))
            pairs.append((q, text))
        idx += 1
    if len(pairs) < target:
        raise ValueError(
            f"corpus too small for agreement gate: {len(pairs)} pairs < {target}")
    rng = random.Random(_SEED)
    rng.shuffle(pairs)
    return pairs[:target]


def run_agreement_check(artifact, pairs: list, seq_len: int) -> dict:
    """Compare Core ML raw logits vs the PyTorch checkpoint on every pair."""
    import numpy as np  # type: ignore
    import torch  # type: ignore
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

    from .convert import PHASE3_BUILD_CACHE
    from .runtime import CoreMLComputeUnit, CoreMLRuntime

    snap = os.path.join(
        PHASE3_BUILD_CACHE, "huggingface",
        "models--" + artifact.model_id.replace("/", "--"),
        "snapshots", artifact.revision)
    if not os.path.isdir(snap):
        return {"passed": False, "n_pairs": 0, "error": f"snapshot missing: {snap}"}
    tok = AutoTokenizer.from_pretrained(snap, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(snap)
    model.eval()

    rt = CoreMLRuntime(artifact, compute_unit=CoreMLComputeUnit.ALL)
    if not rt.available:
        return {"passed": False, "n_pairs": 0, "error": rt.load_error or "coreml_unavailable"}
    mlmodel = rt._model

    cos_min, max_abs, cos_sum = 1.0, 0.0, 0.0
    worst = None
    n = len(pairs)
    for i, (q, c) in enumerate(pairs):
        enc = tok(q, c, truncation=True, padding="max_length",
                  max_length=seq_len, return_tensors="pt")
        with torch.no_grad():
            pt_logits = model(**enc).logits
        preds = mlmodel.predict({
            "input_ids": enc["input_ids"].numpy().astype(np.int32),
            "attention_mask": enc["attention_mask"].numpy().astype(np.int32),
            "token_type_ids": enc["token_type_ids"].numpy().astype(np.int32),
        })
        cm_logits = None
        for key in ("logits", "output", "output_1", "logits_1"):
            if key in preds:
                cm_logits = preds[key]
                break
        if cm_logits is None:
            return {"passed": False, "n_pairs": i, "error": "no logit output"}
        pt_np = np.asarray(pt_logits, dtype=np.float64).reshape(-1)
        cm_np = np.asarray(cm_logits, dtype=np.float64).reshape(-1)
        if pt_np.shape != cm_np.shape:
            return {"passed": False, "n_pairs": i,
                    "error": f"shape mismatch {pt_np.shape} vs {cm_np.shape}"}
        delta = float(np.max(np.abs(pt_np - cm_np)))
        denom = float(np.linalg.norm(pt_np) * np.linalg.norm(cm_np))
        cos = float(np.dot(pt_np, cm_np) / denom) if denom > 0 else 1.0
        cos_min = min(cos_min, cos)
        cos_sum += cos
        if delta > max_abs:
            max_abs = delta
            worst = {"pair_index": i, "max_abs_logit": round(delta, 6)}
        if (i + 1) % 250 == 0:
            print(f"  agreement: {i + 1}/{n} pairs "
                  f"(min_cos={cos_min:.6f}, max_abs={max_abs:.6f})", flush=True)

    passed = cos_min >= _COSINE_TOL and max_abs <= _MAX_ABS_LOGIT
    return {
        "passed": passed,
        "n_pairs": n,
        "seq_len": seq_len,
        "model_id": artifact.model_id,
        "revision": artifact.revision,
        "compute_unit": CoreMLComputeUnit.ALL.value,
        "min_cosine": round(cos_min, 6),
        "mean_cosine": round(cos_sum / max(n, 1), 6),
        "max_abs_logit": round(max_abs, 6),
        "worst_pair": worst,
        "thresholds": {"min_cosine": _COSINE_TOL, "max_abs_logit": _MAX_ABS_LOGIT},
        "pair_source": "deterministic local corpus (tasks + source files), "
                       f"seed={_SEED}",
    }
