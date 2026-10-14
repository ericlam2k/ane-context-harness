"""Tests for repository scanning: exclusions, policy denial, file types."""
from __future__ import annotations

from pathlib import Path

from src.ane_context_harness.indexing.repository import scan_repository


def test_git_and_build_artifacts_excluded(tmp_path, py_repo):
    plan = scan_repository(py_repo, 1000000, never_read=[".env*", ".aws/**"])
    rels = {f.rel_path for f in plan.files}
    assert not any(p.startswith(".git") for p in rels)
    assert "src/discount.py" in rels
    assert "tests/test_discount.py" in rels


def test_env_file_policy_denied(tmp_path, py_repo):
    plan = scan_repository(py_repo, 1000000, never_read=[".env*", "**/.env*"])
    skipped_reasons = [s["reason"] for s in plan.skipped]
    assert "policy_deny" in skipped_reasons
    assert not any(f.rel_path == ".env" for f in plan.files)


def test_ts_local_env_denied(tmp_path, ts_repo):
    plan = scan_repository(ts_repo, 1000000, never_read=[".env*", "**/.env*", ".EnvLocal"])
    rels = {f.rel_path for f in plan.files}
    assert ".EnvLocal" not in rels
    assert "src/math.ts" in rels


def test_binary_file_skipped(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n")
    (root / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(20))
    plan = scan_repository(root, 1000000)
    rels = {f.rel_path for f in plan.files}
    assert "app.py" in rels
    assert "icon.png" not in rels


def test_language_detection():
    from src.ane_context_harness.indexing.repository import detect_language
    assert detect_language("a/b/c.py") == "python"
    assert detect_language("x/y/math.ts") == "typescript"
    assert detect_language("z/z.bin") == "unknown"


def test_large_file_skipped(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    p = root / "big.py"
    p.write_text("x" * 2000)
    plan = scan_repository(root, max_file_bytes=1000)
    assert plan.skipped and plan.skipped[0]["reason"] == "too_large"


def test_skipped_by_reason_counts_rejections_not_unchanged(tmp_path):
    from src.ane_context_harness.indexing.repository import skipped_by_reason
    root = tmp_path / "repo"
    root.mkdir()
    (root / "ok.py").write_text("x = 1\n")
    (root / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(20))
    big = root / "big.py"
    big.write_text("x" * 2000)
    plan = scan_repository(root, max_file_bytes=1000)
    counts = skipped_by_reason(plan)
    assert counts == {"binary": 1, "too_large": 1}
    # ok.py indexed, never counted as skipped
    assert {f.rel_path for f in plan.files} == {"ok.py"}


def test_index_response_carries_skipped_by_reason(tmp_path):
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness.config import build_config, merge
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50, "chunk_overlap_tokens": 5},
            "retention": {"ttl_seconds": 300}}
    pipe = Pipeline(build_config(merge(base, {})))
    root = tmp_path / "repo2"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    (root / "b.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(20))
    resp = pipe.register_repository(str(root), "sbr-live", True)
    assert resp.skipped_by_reason == {"binary": 1}
