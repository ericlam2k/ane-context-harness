"""Integrity validation: span presence, polarity inventory, pipeline hook."""
from ane_context_harness.integrity import (
    protected_spans,
    verify_package,
)


def _ev(path, content, reasons):
    return {"path": path, "start_line": 1, "end_line": 2, "symbol": None,
            "score": 1.0, "selection_reasons": reasons,
            "content_hash": "h", "content": content}


def test_unprotected_evidence_is_unchecked():
    out = verify_package([_ev("a.py", "nothing special here", ["lexical_rerank"])],
                         ["nothing special here"])
    assert out["ok"] is True
    assert out["checked"] == 0
    assert out["altered"] == [] and out["spans"] == []


def test_intact_protected_span_passes():
    content = "retry only when enabled and count >= 3, never when failed"
    out = verify_package(
        [_ev("docs/rules.md", content, ["mandatory"])],
        ["## Evidence\n```\n" + content + "\n```"])
    assert out["ok"] is True
    assert out["checked"] == 1
    assert out["altered"] == []
    assert out["spans"][0]["sha256"] is not None


def test_polarity_inventory_recorded():
    content = "retry only when enabled and count >= 3, never when failed"
    spans = protected_spans([_ev("docs/rules.md", content, ["mandatory"])])
    assert spans[0]["polarity"] == [">=", "enabled", "failed", "never"]


def test_altered_span_detected():
    out = verify_package(
        [_ev("docs/rules.md", "do not ship before tests pass", ["authority"])],
        ["## Evidence\n```\ndo ship before tests pass\n```"])
    assert out["ok"] is False
    assert out["altered"] == [{"path": "docs/rules.md", "symbol": None,
                               "reason": "content_absent"}]


def test_dropped_negation_is_content_absent():
    # Exactness is the gate: a dropped "not" changes the bytes, so the
    # span no longer verifies — no separate polarity verdict needed.
    src = "concessions are not capped below 10"
    rendered = "## Evidence\n```\nconcessions are capped below 10\n```"
    out = verify_package([_ev("docs/rules.md", src, ["explicit_path"])],
                         [rendered])
    assert out["ok"] is False
    assert out["altered"][0]["reason"] == "content_absent"


def test_dropped_operator_is_content_absent():
    src = "applies when total > 100 and rate != 0"
    rendered = "## Evidence\n```\napplies when total 100 and rate 0\n```"
    out = verify_package([_ev("a.py", src, ["mandatory"])], [rendered])
    assert out["ok"] is False
    assert out["altered"][0]["reason"] == "content_absent"


def test_word_boundary_no_false_positive():
    # "cannot" must not satisfy a "not" sentinel; intact spans pass.
    out = verify_package(
        [_ev("a.py", "this cannot proceed", ["mandatory"])],
        ["this cannot proceed"])
    assert out["ok"] is True


def test_empty_package_ok():
    assert verify_package([], [""]) == {"ok": True, "checked": 0,
                                        "altered": [], "spans": []}


def test_pipeline_reports_integrity(tmp_path):
    from ane_context_harness.config import build_config, merge
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness import schemas
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "store")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project",
                             "int-check")
    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="int-check",
        task="Fix the incorrect discount calculation",
        token_budget=2000,
        explicit_paths=["src/discount.py"]))
    integ = pkg.metrics["diagnostics"]["integrity"]
    assert integ["checked"] >= 1
    assert integ["ok"] is True
    assert integ["altered"] == []
