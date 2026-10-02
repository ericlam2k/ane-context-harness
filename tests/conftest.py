"""Shared test fixtures (Pytest)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Never collect the synthetic fixture repositories (they contain test files
# that import a non-package `src` and are not part of the harness test suite).
collect_ignore = ["fixtures"]

from src.ane_context_harness.config import build_config
from src.ane_context_harness.pipeline import Pipeline

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@pytest.fixture
def tmp_storage(tmp_path):
    return str(tmp_path / "store")


@pytest.fixture
def config(tmp_storage):
    return build_config({"index": {"storage_path": tmp_storage}, "privacy": {"never_read": [
        "**/.env*", "**/.aws/**", "**/.ssh/**", "**/*.pem", "**/.EnvLocal",
    ]}})


@pytest.fixture
def pipeline(config):
    return Pipeline(config)


@pytest.fixture
def py_repo():
    return str((FIXTURE_ROOT / "synthetic_py_project").resolve())


@pytest.fixture
def ts_repo():
    return str((FIXTURE_ROOT / "synthetic_ts_project").resolve())


@pytest.fixture
def benchmark_tasks_dir():
    return str((Path(__file__).resolve().parent.parent / "benchmarks" / "tasks"))
