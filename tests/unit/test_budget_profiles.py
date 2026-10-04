"""Budget profiles: category order/caps per task type, mandatory-safe."""
from ane_context_harness.retrieval.selector import select_evidence

from tests.unit.test_selector import _chunk, _scores, WEIGHTS


def _mixed():
    return [
        _chunk("t", "tests/test_x.py", "def test_something edge case here"),
        _chunk("s", "docs/notes.md", "background narrative documentation text"),
        _chunk("i", "src/impl.py", "def run_main workflow implementation",
               symbol="run_main"),
    ]


def test_default_order_unchanged():
    chunks = _mixed()
    sel, diag = select_evidence(chunks, _scores(chunks, "edge workflow"),
                                "edge workflow", token_budget=100,
                                explicit_paths=[], weights=WEIGHTS)
    assert "profile" not in diag
    cats = [c.path for c in sel]
    assert cats  # smoke: selection works without profiles


def test_debugging_puts_tests_first():
    chunks = _mixed()
    sel, diag = select_evidence(
        chunks, _scores(chunks, "edge workflow"), "edge workflow",
        token_budget=100, explicit_paths=[], weights=WEIGHTS,
        category_order={"test": 0, "implementation": 1, "supporting": 2})
    paths = [c.path for c in sel]
    assert paths[0] == "tests/test_x.py"


def test_caps_exclude_only_non_mandatory():
    chunks = [
        _chunk("s1", "docs/a.md", "background narrative one two three"),
        _chunk("s2", "docs/b.md", "background narrative four five six"),
        _chunk("i", "src/impl.py", "def run_main workflow implementation",
               symbol="run_main"),
    ]
    sel, _ = select_evidence(
        chunks, _scores(chunks, "workflow"), "workflow", token_budget=100,
        explicit_paths=[], weights=WEIGHTS,
        category_caps={"supporting": 0.01})
    # one supporting chunk fits via the max(tokens, cap) floor; the second
    # supporting chunk is capped out
    assert sum(1 for c in sel if c.path.startswith("docs/")) == 1
    # ...but a flagged supporting chunk is mandatory and always retained
    sel2, _ = select_evidence(
        chunks, _scores(chunks, "workflow"), "workflow", token_budget=100,
        explicit_paths=["docs/b.md"], weights=WEIGHTS,
        category_caps={"supporting": 0.01})
    assert "docs/b.md" in [c.path for c in sel2]


def test_unknown_category_names_ignored():
    chunks = _mixed()
    sel, _ = select_evidence(
        chunks, _scores(chunks, "edge"), "edge", token_budget=100,
        explicit_paths=[], weights=WEIGHTS,
        category_order={"nope": 0}, category_caps={"nope": 0.5})
    assert sel  # no crash, selection proceeds


def test_pipeline_rejects_unknown_profile(tmp_path):
    from ane_context_harness.config import build_config, merge
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness import schemas
    import pytest
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "s")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project", "bp")
    with pytest.raises(ValueError, match="unknown budget profile"):
        pipe.select_context(schemas.SelectRequest(
            repository_id="bp", task="t", token_budget=200,
            options={"profile": "nope"}))


def test_pipeline_profile_reported(tmp_path):
    from ane_context_harness.config import build_config, merge
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness import schemas
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "s")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project", "bp2")
    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="bp2", task="Fix the discount calculation",
        token_budget=2000, options={"profile": "debugging"}))
    assert pkg.metrics["diagnostics"]["profile"]["name"] == "debugging"
