"""Stated-need resolution: an agent states which symbol/path it needs, the
harness validates the statement against the index at zero model cost, and
resolved items enter claim identification exactly as task-derived claims do.

Two failure classes are pinned here:

1. A stated need that is silently ignored (the pack is identical to the
   unstated one even though the agent named the evidence), or worse, a
   stated string that never existed is silently treated as real evidence.
   Resolution must be reported per item; unresolved items contribute no
   claim terms and pack nothing.
2. A backdoor around the budget contract: a resolved stated claim must be
   admitted only through the same claims-first rules every other claim
   goes through — same specificity gate, same caps, same budget admission,
   counted in claims_dropped_budget when it does not fit.

All tests use synthetic chunks; no fixture repositories.
"""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.structural import aggregate_scores
from src.ane_context_harness.retrieval.selector import (
    claim_candidates,
    identify_claim_candidates,
    resolve_stated_items,
    select_evidence,
    stated_claim_terms,
    stated_need_resolution_block,
)
from src.ane_context_harness.schemas import RepositoryChunk


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10,
    "git_recency_weight": 0.05,
    "diversity_lambda": 0.25, "top_k_for_diversity": 60,
}


def _chunk(cid, path, text, symbol=None, tokens=40, metadata=None):
    terms = lex_terms(text)
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=path, language="python",
        start_line=1, end_line=2, symbol=symbol, content_hash=cid,
        estimated_tokens=tokens, lexical_terms=tuple(terms),
        content=text, metadata=metadata or {},
    )


def _scores(chunks, task):
    bm = [1.0 - i * 0.05 for i in range(len(chunks))]
    return aggregate_scores(chunks, task, [], WEIGHTS, bm)


def _symbols(*chunks):
    return chunks


# --- resolution (lookup, no model) -----------------------------------------

def test_resolve_exact_symbol():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget"))
    rec = resolve_stated_items(chunks, ["alpha_widget"])[0]
    assert rec["resolved"] is True
    assert rec["matched_symbol"] == "alpha_widget"
    assert rec["matched_path"] is None
    assert "nearest" not in rec


def test_resolve_is_case_and_separator_insensitive():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget"))
    for stated in ("alpha_widget", "Alpha_Widget", "ALPHA_WIDGET",
                   "alpha-widget", "alpha.widget", "alpha$widget",
                   "alphawidget"):
        rec = resolve_stated_items(chunks, [stated])[0]
        assert rec["resolved"] is True, stated
        assert rec["matched_symbol"] == "alpha_widget"


def test_resolve_inflection_fold_indexed_singular_stated_plural():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def retry_policy(): pass",
               symbol="retry_policy"))
    rec = resolve_stated_items(chunks, ["retry_policies"])[0]
    assert rec["resolved"] is True
    assert rec["matched_symbol"] == "retry_policy"


def test_resolve_inflection_fold_indexed_plural_stated_singular():
    chunks = _symbols(
        _chunk("a", "src/a.py", "class RetryPolicies: pass",
               symbol="RetryPolicies"))
    rec = resolve_stated_items(chunks, ["RetryPolicy"])[0]
    assert rec["resolved"] is True
    assert rec["matched_symbol"] == "RetryPolicies"


def test_resolve_path_exact_match_and_slash_normalization():
    chunks = _symbols(
        _chunk("a", "src/widget.py", "def widget(): pass", symbol="widget"))
    for stated in ("src/widget.py", "src\\widget.py"):
        rec = resolve_stated_items(chunks, [stated])[0]
        assert rec["resolved"] is True, stated
        assert rec["matched_path"] == "src/widget.py"
        assert rec["matched_symbol"] is None


def test_unresolved_symbol_reports_never_resolves():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget"))
    rec = resolve_stated_items(chunks, ["zzz_absent_symbol"])[0]
    assert rec["resolved"] is False
    assert rec["matched_symbol"] is None
    assert rec["matched_path"] is None
    assert rec["nearest"] == []
    assert rec["nearest_note"] == "no similar indexed symbols"


def test_nearest_symbols_rank_by_shared_subtokens():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_beta(): pass", symbol="alpha_beta"),
        _chunk("b", "src/b.py", "def beta_gamma(): pass", symbol="beta_gamma"),
        _chunk("c", "src/c.py", "def zeta_beta(): pass", symbol="zeta_beta"),
        _chunk("d", "src/d.py", "def delta_epsilon(): pass",
               symbol="delta_epsilon"))
    rec = resolve_stated_items(chunks, ["beta_alpha"])[0]
    assert rec["resolved"] is False
    # alpha_beta shares both subtokens; the two one-token matches tie and
    # break alphabetically; delta_epsilon shares nothing and is omitted.
    assert rec["nearest"] == ["alpha_beta", "beta_gamma", "zeta_beta"]


def test_nearest_suggestions_cap_at_three():
    chunks = _symbols(*[
        _chunk(f"c{i}", f"src/f{i}.py", f"def widget_thing_{i}(): pass",
               symbol=f"widget_thing_{i}")
        for i in range(5)])
    rec = resolve_stated_items(chunks, ["widget_thing_x"])[0]
    assert len(rec["nearest"]) == 3


def test_resolution_keeps_input_order_and_coerces_non_strings():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["zzz_absent", 42, "alpha_widget"])
    assert [r["stated"] for r in recs] == ["zzz_absent", "42", "alpha_widget"]
    assert [r["resolved"] for r in recs] == [False, False, True]


def test_resolution_block_counts_and_note():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["alpha_widget", "zzz_absent"])
    block = stated_need_resolution_block(recs)
    assert block["total"] == 2
    assert block["resolved"] == 1
    assert block["unresolved"] == 1
    assert [r["stated"] for r in block["items"]] == ["alpha_widget",
                                                     "zzz_absent"]
    assert "not inference" in block["note"]


def test_resolution_block_empty_records():
    block = stated_need_resolution_block([])
    assert block == {"items": [], "total": 0, "resolved": 0, "unresolved": 0,
                     "note": block["note"]}


# --- stated terms mined for claim identification ----------------------------

def test_stated_need_text_mined_with_task_extraction():
    terms = stated_claim_terms("partial widget handling", None)
    assert {"partial", "widget", "handling"} <= terms


def test_unresolved_stated_items_contribute_no_terms():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["zzz_absent"])
    assert stated_claim_terms(None, recs) == set()


def test_mixed_resolution_contributes_only_resolved_terms():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["alpha_widget", "zzz_absent"])
    terms = stated_claim_terms(None, recs)
    assert {"alpha", "widget"} <= terms
    assert not any("zzz" in t for t in terms)


# --- admission through the same claims-first engine ------------------------

def test_resolved_stated_symbol_is_identified_as_claim():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200))
    stated = stated_claim_terms(None, resolve_stated_items(chunks,
                                                           ["alpha_widget"]))
    mandatory, reasons, _ = identify_claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated)
    assert 0 in mandatory
    assert "named_symbol" in reasons[0]


def test_stated_symbol_claim_identified_exactly_like_task_name():
    """The stated route and the task-text route reach the same claim set."""
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "src/b.py", "def beta_widget(): return 1",
               symbol="beta_widget", tokens=200))
    task_named = claim_candidates(chunks, "alpha_widget", [],
                                  weights=WEIGHTS)
    stated = claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated_claim_terms(
            None, resolve_stated_items(chunks, ["alpha_widget"])))
    assert stated == task_named


def test_resolved_stated_claim_admitted_when_it_fits_although_task_is_silent():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "src/b.py", "totally unrelated prose about weather",
               tokens=200))
    scores = _scores(chunks, "unrelated phrasing entirely")
    stated = stated_claim_terms(None, resolve_stated_items(chunks,
                                                           ["alpha_widget"]))
    selected, diag = select_evidence(
        chunks, scores, "unrelated phrasing entirely", token_budget=500,
        explicit_paths=[], weights=WEIGHTS, stated_terms=stated)
    assert any(c.path == "src/a.py" for c in selected)
    assert diag["claims_admitted"] == 1
    reasons = next(s.selection_reasons for s in scores
                   if s.chunk_id == "a")
    assert "claim" in reasons


def test_resolved_stated_claim_is_dropped_and_counted_when_it_cannot_fit():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=400),
        _chunk("b", "src/b.py", "def beta_gadget(): return 1",
               symbol="beta_gadget", tokens=400))
    scores = _scores(chunks, "unrelated phrasing entirely")
    stated = stated_claim_terms(None, resolve_stated_items(
        chunks, ["alpha_widget", "beta_gadget"]))
    selected, diag = select_evidence(
        chunks, scores, "unrelated phrasing entirely", token_budget=500,
        explicit_paths=[], weights=WEIGHTS, stated_terms=stated)
    assert sum(c.estimated_tokens for c in selected) <= 500
    assert diag["claims_admitted"] == 1
    assert diag["claims_dropped_budget"] == 1
    assert all("claim" in s.selection_reasons or "claim_dropped_budget" in s.selection_reasons
               for s in scores)


def test_resolved_stated_path_is_identified_as_claim():
    chunks = _symbols(
        _chunk("a", "src/widget.py", "def widget(): return 1",
               symbol="widget", tokens=200))
    stated = stated_claim_terms(None, resolve_stated_items(chunks,
                                                           ["src/widget.py"]))
    mandatory, reasons, _ = identify_claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated)
    assert 0 in mandatory
    assert "named_path" in reasons[0]


def test_stated_need_free_text_admits_like_task_text():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200))
    via_task, _ = select_evidence(
        chunks, _scores(chunks, "alpha_widget"), "alpha_widget",
        token_budget=500, explicit_paths=[], weights=WEIGHTS)
    via_stated, diag = select_evidence(
        chunks, _scores(chunks, "unrelated phrasing entirely"),
        "unrelated phrasing entirely",
        token_budget=500, explicit_paths=[], weights=WEIGHTS,
        stated_terms=stated_claim_terms("alpha_widget", None))
    assert {c.path for c in via_stated} == {c.path for c in via_task}
    assert diag["claims_admitted"] == 1


def test_no_stated_terms_changes_nothing():
    """Passing stated_terms=None must not perturb the baseline decision."""
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "src/b.py", "def beta_widget(): return 1",
               symbol="beta_widget", tokens=200))
    base_sel, base_diag = select_evidence(
        chunks, _scores(chunks, "alpha_widget"), "alpha_widget",
        token_budget=500, explicit_paths=[], weights=WEIGHTS)
    same_sel, same_diag = select_evidence(
        chunks, _scores(chunks, "alpha_widget"), "alpha_widget",
        token_budget=500, explicit_paths=[], weights=WEIGHTS,
        stated_terms=None)
    assert [c.chunk_id for c in base_sel] == [c.chunk_id for c in same_sel]
    assert base_diag == same_diag
