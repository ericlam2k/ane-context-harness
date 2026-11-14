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
    _gate_need_terms,
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

def test_stated_need_text_mined_then_anchored_to_index():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def widget_thing(): pass",
               symbol="widget_thing"))
    terms, note = stated_claim_terms("partial widget handling", None, chunks)
    assert terms == {"widget"}
    assert note == {"kept": ["widget"],
                    "dropped": ["handl", "handle", "handling", "partial"]}


def test_stated_need_nothing_anchors_yields_no_terms():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    terms, note = stated_claim_terms("quixotic zephyr preamble", None, chunks)
    assert terms == set()
    assert note == {"kept": [],
                    "dropped": ["preamble", "quixotic", "zephyr"]}


def test_stated_need_unmineable_yields_empty_note_not_absent():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    terms, note = stated_claim_terms("!!!", None, chunks)
    assert terms == set()
    assert note == {"kept": [], "dropped": []}


# --- need-text anchoring gate ----------------------------------------------

def _gate_chunks():
    return _symbols(
        _chunk("a", "src/auth_session.py",
               "def logout_user(): pass", symbol="logout_user"),
        _chunk("b", "src/reorder.py",
               "def needs_reorder(): pass", symbol="needs_reorder"),
        _chunk("c", "docs/runbook.md",
               "Operational runbook for the reorder service."))


def test_gate_keeps_symbol_name_case_and_separator_variants():
    chunks = _gate_chunks()
    for term in ["logout_user", "Logout_User", "logout-user", "logout.user",
                 "logout$user", "logoutuser"]:
        kept, note = _gate_need_terms({term}, chunks)
        assert kept == {term}, term
        assert note["dropped"] == []


def test_gate_keeps_symbol_name_inflection_fold():
    chunks = _symbols(
        _chunk("a", "src/s.py", "def retry_policy(): pass",
               symbol="retry_policy"))
    kept, note = _gate_need_terms({"retry_policies"}, chunks)
    assert kept == {"retry_policies"}
    assert note["dropped"] == []


def test_gate_subtoken_branch_keeps_exact_subtokens():
    chunks = _gate_chunks()
    kept, note = _gate_need_terms({"logout", "user", "needs", "reorder"},
                                  chunks)
    assert kept == {"logout", "user", "needs", "reorder"}
    assert note["dropped"] == []


def test_gate_subtoken_branch_rejects_stem_of_fold():
    chunks = _gate_chunks()
    kept, note = _gate_need_terms({"need"}, chunks)
    assert kept == set()
    assert note["dropped"] == ["need"]


def test_gate_keeps_indexed_path_occurrence():
    chunks = _gate_chunks()
    kept, note = _gate_need_terms({"runbook"}, chunks)
    assert kept == {"runbook"}
    assert note["dropped"] == []


def test_gate_drops_generic_unanchored_terms():
    chunks = _gate_chunks()
    kept, note = _gate_need_terms({"zzz", "quixotic", "banana"}, chunks)
    assert kept == set()
    assert note["dropped"] == ["banana", "quixotic", "zzz"]


def test_gate_prevents_substring_claim_on_folded_stem():
    """The mined term 'need' must never claim the symbol needs_reorder.

    Caught failure (the flip): an unvalidated stated need reaches the
    claim pass, the bounded substring fallback matches the stem inside
    needs_reorder, and a chunk the task never asked for is admitted.
    The gate drops the term before claims see it.
    """
    chunks = _gate_chunks()
    task = "unrelated phrasing entirely"
    mandatory, _reasons, _, _ = identify_claim_candidates(
        chunks, task, [], weights=WEIGHTS, stated_terms={"need"})
    assert 1 in mandatory  # pre-gate shape: the substring fallback fires
    terms, note = stated_claim_terms("need", None, chunks)
    assert terms == set()
    assert note["dropped"] == ["need"]
    mandatory, _reasons, _, _ = identify_claim_candidates(
        chunks, task, [], weights=WEIGHTS, stated_terms=terms or None)
    assert mandatory == set()


def test_gate_note_lists_are_sorted_and_deduplicated():
    chunks = _gate_chunks()
    _kept, note = _gate_need_terms({"user", "logout", "banana", "logout"},
                                   chunks)
    assert note["kept"] == sorted(set(note["kept"]))
    assert note["dropped"] == sorted(set(note["dropped"]))


def test_unresolved_stated_items_contribute_no_terms():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["zzz_absent"])
    terms, note = stated_claim_terms(None, recs, chunks)
    assert terms == set()
    assert note is None


def test_mixed_resolution_contributes_only_resolved_terms():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): pass",
               symbol="alpha_widget"))
    recs = resolve_stated_items(chunks, ["alpha_widget", "zzz_absent"])
    terms, _note = stated_claim_terms(None, recs, chunks)
    assert {"alpha", "widget"} <= terms
    assert not any("zzz" in t for t in terms)


# --- admission through the same claims-first engine ------------------------

def test_resolved_stated_symbol_is_identified_as_claim():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200))
    stated, _ = stated_claim_terms(None, resolve_stated_items(chunks,
                                                             ["alpha_widget"]),
                                  chunks)
    mandatory, reasons, _, _ = identify_claim_candidates(
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
            None, resolve_stated_items(chunks, ["alpha_widget"]),
            chunks)[0])
    assert stated == task_named


def test_resolved_stated_claim_admitted_when_it_fits_although_task_is_silent():
    chunks = _symbols(
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "src/b.py", "totally unrelated prose about weather",
               tokens=200))
    scores = _scores(chunks, "unrelated phrasing entirely")
    stated, _ = stated_claim_terms(None, resolve_stated_items(chunks,
                                                             ["alpha_widget"]),
                                  chunks)
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
    stated, _ = stated_claim_terms(None, resolve_stated_items(
        chunks, ["alpha_widget", "beta_gadget"]), chunks)
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
    stated, _ = stated_claim_terms(None, resolve_stated_items(chunks,
                                                             ["src/widget.py"]),
                                  chunks)
    mandatory, reasons, _, _ = identify_claim_candidates(
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
        stated_terms=stated_claim_terms("alpha_widget", None, chunks)[0])
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
