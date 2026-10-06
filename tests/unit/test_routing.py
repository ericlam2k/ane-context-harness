"""Content-type router: classification, strategy table, pipeline report."""
from ane_context_harness.routing import (
    COMPACT,
    EXTRACTIVE,
    STRUCTURAL,
    VERBATIM,
    classify_content,
    compact_evidence,
    route_evidence,
    strategy_for,
)


def test_classify_by_extension():
    assert classify_content("src/a.py") == "code"
    assert classify_content("src/a.TS") == "code"
    assert classify_content("config/x.yaml") == "config"
    assert classify_content("a/b/.env") == "config"
    assert classify_content("fix.diff") == "diff"
    assert classify_content("docs/r.md") == "prose"
    assert classify_content("notes.txt", "Traceback (most recent call last): x") == "prose"
    assert classify_content("weird.xyz") == "unknown"


def test_classify_log_sniffing():
    assert classify_content("out.log", "Traceback (most recent call last): boom") == "log"
    assert classify_content("run.out", "3 passed, 1 failed, retrying") == "log"
    assert classify_content("run.out", "all green, nothing to see") == "unknown"


def test_strategy_table():
    assert strategy_for("code") == STRUCTURAL
    assert strategy_for("config") == STRUCTURAL
    assert strategy_for("diff") == STRUCTURAL
    assert strategy_for("log") == COMPACT
    assert strategy_for("prose") == EXTRACTIVE
    assert strategy_for("conversation") == EXTRACTIVE
    assert strategy_for("unknown") == EXTRACTIVE
    assert strategy_for("whatever") == EXTRACTIVE
    # protection overrides everything
    for ct in ("code", "config", "diff", "log", "prose", "unknown"):
        assert strategy_for(ct, protected=True) == VERBATIM


def test_route_annotates_without_changing_content():
    ev = [
        {"path": "src/a.py", "content": "def f(): pass",
         "selection_reasons": ["mandatory"]},
        {"path": "docs/r.md", "content": "background notes here",
         "selection_reasons": ["lexical_rerank"]},
    ]
    counts = route_evidence(ev)
    assert ev[0]["strategy"] == VERBATIM
    assert ev[0]["content_type"] == "code"
    assert ev[1]["strategy"] == EXTRACTIVE
    assert ev[0]["content"] == "def f(): pass"  # untouched
    assert counts == {VERBATIM: 1, EXTRACTIVE: 1}
    assert route_evidence([]) == {}


def test_pipeline_reports_routing(tmp_path):
    from ane_context_harness.config import build_config, merge
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness import schemas
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "s")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project", "route")
    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="route", task="Fix the discount calculation",
        token_budget=2000))
    routing = pkg.metrics["diagnostics"]["routing"]
    assert sum(routing["strategies"].values()) == len(pkg.evidence)
    assert set(routing["strategies"]) <= {VERBATIM, STRUCTURAL, COMPACT,
                                          EXTRACTIVE}
    assert all("strategy" in e and "content_type" in e
               for e in pkg.evidence)
    assert set(routing["compaction"]) == {"compacted", "tokens_before",
                                          "tokens_after", "skipped"}


_REPETITIVE_LOG = "\n".join(
    ["Collecting package-%d" % i for i in range(30)]
    + ["....", "....", "...."]
    + ["Traceback (most recent call last):",
       '  File "app.py", line 3, in <module>',
       "ValueError: bad discount"]
)


def _log_ev(content, reasons=None):
    return {"path": "run/pytest.out", "content": content,
            "selection_reasons": reasons or ["lexical_rerank"]}


def test_compact_shrinks_repetitive_log_with_digest():
    ev = [_log_ev(_REPETITIVE_LOG)]
    route_evidence(ev)
    assert ev[0]["strategy"] == COMPACT
    stats = compact_evidence(ev)
    assert ev[0]["compacted"] is True
    assert ev[0]["content_sha256"].startswith("sha256:")
    assert "ValueError: bad discount" in ev[0]["content"]
    assert stats["compacted"] == 1
    assert stats["tokens_after"] < stats["tokens_before"]
    # deterministic: same input bytes, same output bytes
    again = [_log_ev(_REPETITIVE_LOG)]
    route_evidence(again)
    compact_evidence(again)
    assert again[0]["content"] == ev[0]["content"]


def test_compact_never_touches_protected():
    ev = [_log_ev(_REPETITIVE_LOG, ["mandatory"])]
    route_evidence(ev)
    assert ev[0]["strategy"] == VERBATIM
    stats = compact_evidence(ev)
    assert ev[0]["content"] == _REPETITIVE_LOG
    assert "compacted" not in ev[0]
    assert stats == {"compacted": 0, "tokens_before": 0,
                     "tokens_after": 0, "skipped": 0}


def test_compact_skips_tiny_log_without_growth():
    tiny = "Traceback (most recent call last): boom"
    ev = [_log_ev(tiny)]
    route_evidence(ev)
    stats = compact_evidence(ev)
    assert "compacted" not in ev[0]
    assert ev[0]["content"] == tiny
    assert stats["skipped"] == 1


def test_compact_ignores_non_log_strategies():
    ev = [{"path": "src/a.py", "content": "def f(): pass",
           "selection_reasons": ["lexical_rerank"]}]
    route_evidence(ev)
    assert ev[0]["strategy"] == STRUCTURAL
    assert compact_evidence(ev)["compacted"] == 0
    assert ev[0]["content"] == "def f(): pass"
