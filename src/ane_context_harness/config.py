"""Configuration loader.

Loads YAML defaults from the package/config; allows user override via
`ANE_HARNESS_CONFIG` env var or an explicit path. Pure data access, no ML.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover
    _HAVE_YAML = False


DEFAULT_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 8765},
    "index": {
        "storage": "sqlite",
        "max_file_bytes": 1000000,
        "chunk_target_tokens": 350,
        "chunk_overlap_tokens": 40,
        "incremental": True,
    },
    "retrieval": {
        "max_initial_candidates": 500,
        "lexical_weight": 0.35,
        "symbol_weight": 0.25,
        "path_weight": 0.15,
        "dependency_weight": 0.10,
        "test_pair_weight": 0.10,
        "git_recency_weight": 0.05,
        "diversity_lambda": 0.25,
        "top_k_for_diversity": 60,
        # Multi-pass query expansion for ranking only ("off" | "max" | "sum").
        # Pins, reasons, and budgets always use the original task. "max"
        # (fused best-pass score) won the frozen-eval comparison over "sum"
        # on robustness grounds at equal metrics; see
        # benchmarks/reports/eval_expansion.json.
        "query_expansion": "max",
    },
    "runtime": {
        "compute_mode": "deterministic_only",
        "fail_closed": False,
    },
    "privacy": {
        "redact_secrets": False,
        "fail_closed_for_cloud": False,
        "never_read": ["**/.git/**", "**/.env*", "**/.EnvLocal",
                       "**/.aws/**", "**/.ssh/**", "**/*.pem"],
    },
    "limits": {
        "request_body_bytes": 10000000,
        "candidate_token_limit": 100000,
        "default_output_token_budget": 12000,
        "max_output_token_budget": 30000,
        # Live provider calls are disabled until this is deliberately raised;
        # stages 0-1 (mock/dry-run) need no cap. See
        # docs/provider-evaluation-stages.md.
        "max_provider_spend_usd": 0.0,
    },
    "telemetry": {"enabled": True, "include_source_text": False},
}


def _search_config_paths() -> list:
    paths = []
    # src/ane_context_harness/config.py -> repo root is three parents up.
    here = Path(__file__).resolve().parent.parent.parent
    paths.append(here / "config" / "default.yaml")
    env = os.environ.get("ANE_HARNESS_CONFIG")
    if env:
        paths.append(Path(env))
    return paths


def load_user_config(path: str | os.PathLike | None = None) -> dict:
    if path is None:
        path = _search_config_paths()[0]
    path = Path(path)
    if not path.exists():
        return {}
    if not _HAVE_YAML:
        raise RuntimeError("PyYAML is required to load YAML config")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def build_config(overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for p in _search_config_paths():
        if p.exists():
            cfg = merge(cfg, load_user_config(p))
    if overrides:
        cfg = merge(cfg, overrides)
    return cfg
