"""Pinned freshness: silent refresh + change notices (pinned scope only).

Portable: tmp repos, temp storage, stdlib only.
"""
import json

from ane_context_harness import freshness as fresh
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness import schemas


def _pipe(tmp_path, extra=None):
    from ane_context_harness.config import merge
    base = {"index": {"storage_path": str(tmp_path / "store"),
                      "chunk_target_tokens": 50,
                      "chunk_overlap_tokens": 5}}
    cfg = build_config(merge(base, extra or {}))
    return Pipeline(cfg)


def _repo(tmp_path, files):
    root = tmp_path / "repo"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return str(root)


def _select(pipe, rid, task, budget=2000, explicit=None):
    req = schemas.SelectRequest(repository_id=rid, task=task,
                                token_budget=budget,
                                explicit_paths=explicit or [])
    return pipe.select_context(req)


def test_expand_pinned_exact_and_glob(tmp_path):
    root = _repo(tmp_path, {"docs/rules.md": "a", "README.md": "b",
                            "src/x.py": "c"})
    assert fresh.expand_pinned(root, ["docs/rules.md"], []) == ["docs/rules.md"]
    assert fresh.expand_pinned(root, [], ["docs/*.md"]) == ["docs/rules.md"]
    assert fresh.expand_pinned(root, ["nope.md"], ["nomatch/*.md"]) == []
    # unpinned files never expand
    assert "src/x.py" not in fresh.expand_pinned(root, [], ["docs/*.md"])


def test_find_stale_changed_and_missing(tmp_path):
    root = _repo(tmp_path, {"docs/rules.md": "v1", "src/x.py": "x"})
    stored = {"docs/rules.md": ("deadbeef", 0)}
    changed, missing = fresh.find_stale(root, ["docs/rules.md"], stored)
    assert changed == ["docs/rules.md"]
    assert missing == []
    changed, missing = fresh.find_stale(root, ["gone.md"], stored)
    assert changed == []
    assert missing == ["gone.md"]
    # unchanged is silent
    h = fresh.file_hash(root, "docs/rules.md")
    changed, missing = fresh.find_stale(
        root, ["docs/rules.md"], {"docs/rules.md": (h, 0)})
    assert (changed, missing) == ([], [])


def test_select_refreshes_pinned_and_notices(tmp_path):
    root = _repo(tmp_path, {"docs/rules.md": "round half up always",
                            "src/main.py": "def main(): pass"})
    pipe = _pipe(tmp_path)
    pipe.register_repository(root, "fresh-repo")
    pkg = _select(pipe, "fresh-repo", "rounding rule",
                  explicit=["docs/rules.md"])
    assert pkg.metrics["diagnostics"]["pinned_changed"] == []
    assert pkg.metrics["diagnostics"]["pinned_missing"] == []
    assert pkg.metrics["diagnostics"]["full_changed"] == []
    assert pkg.metrics["diagnostics"]["full_missing"] == []

    # change the pinned file underneath
    (tmp_path / "repo" / "docs" / "rules.md").write_text(
        "round half to even always", encoding="utf-8")
    pkg2 = _select(pipe, "fresh-repo", "rounding rule",
                   explicit=["docs/rules.md"])
    # Full incremental refresh runs first and handles the change
    assert pkg2.metrics["diagnostics"]["full_changed"] == ["docs/rules.md"]
    assert pkg2.metrics["diagnostics"]["pinned_changed"] == []
    # refreshed content is what the agent receives (silent refresh done)
    texts = " ".join(e["content"] for e in pkg2.evidence)
    assert "half to even" in texts

    # unpinned edits are now caught by the full refresh too
    (tmp_path / "repo" / "src" / "main.py").write_text(
        "def main(): return 1", encoding="utf-8")
    pkg3 = _select(pipe, "fresh-repo", "rounding rule",
                   explicit=["docs/rules.md"])
    assert pkg3.metrics["diagnostics"]["pinned_changed"] == []
    assert pkg3.metrics["diagnostics"]["full_changed"] == ["src/main.py"]


def test_select_reports_missing_pinned(tmp_path):
    root = _repo(tmp_path, {"docs/rules.md": "rules"})
    pipe = _pipe(tmp_path)
    pipe.register_repository(root, "fresh-missing")
    (tmp_path / "repo" / "docs" / "rules.md").unlink()
    pkg = _select(pipe, "fresh-missing", "rules",
                  explicit=["docs/rules.md"])
    assert pkg.metrics["diagnostics"]["full_missing"] == ["docs/rules.md"]
    # pinned_missing is empty because full refresh already handled it
    assert pkg.metrics["diagnostics"]["pinned_missing"] == []


def test_select_without_recorded_root_skips_silently(tmp_path):
    # legacy DBs (indexed before repo_root persistence) never crash
    root = _repo(tmp_path, {"docs/rules.md": "rules"})
    pipe = _pipe(tmp_path)
    pipe.register_repository(root, "fresh-legacy")
    pipe._storage_for("fresh-legacy")._conn.execute(
        "DELETE FROM meta WHERE k='repo_root'")
    pkg = _select(pipe, "fresh-legacy", "rules",
                  explicit=["docs/rules.md"])
    assert pkg.metrics["diagnostics"]["pinned_changed"] == []
    assert pkg.metrics["diagnostics"]["pinned_missing"] == []
    assert pkg.metrics["diagnostics"]["full_changed"] == []
    assert pkg.metrics["diagnostics"]["full_missing"] == []
