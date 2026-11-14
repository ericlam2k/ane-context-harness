"""Claim-origin tagging: stated-born claims carry provenance.

The runtime half of "did the agent aim right" — the harness can say that
a packed claim cited a stated-origin term, because the origin is minted
with the term and threaded to admission. What it cannot say is why the
chunk fit the budget from the pack alone; an incidental rider (a stated-
anchored claim whose chunk rode in for reasons unrelated to the aim) is
indistinguishable from an aimed admission at runtime, so riders are
never counted. Attribution limit: a stated term that also appears
verbatim in the task text is credited as stated (term-level provenance,
not exclusivity). Task-text claims and explicit/authority pins carry no
stated origin, ever.

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
    stated_claim_origins,
    stated_claim_terms,
)
from src.ane_context_harness.schemas import RepositoryChunk


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10,
    "git_recency_weight": 0.05,
    "diversity_lambda": 0.25, "top_k_for_diversity": 60,
}


def _chunk(cid, path, text, symbol=None, tokens=40):
    terms = lex_terms(text)
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=path, language="python",
        start_line=1, end_line=2, symbol=symbol, content_hash=cid,
        estimated_tokens=tokens, lexical_terms=tuple(terms),
        content=text, metadata={},
    )


def _scores(chunks, task):
    bm = [1.0 - i * 0.05 for i in range(len(chunks))]
    return aggregate_scores(chunks, task, [], WEIGHTS, bm)


def _origins(chunks, stated_need, stated_symbols):
    resolution = resolve_stated_items(chunks, stated_symbols)
    return stated_claim_origins(stated_need, resolution, chunks), resolution


# --- origin map minting -----------------------------------------------------

def test_symbol_origin_minted_for_resolved_symbol():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, None, ["alpha_widget"])
    assert origins["alpha_widget"] == {"stated_symbol"}
    # subtokens inherit the origin of the term they were minted from
    assert origins["alpha"] == {"stated_symbol"}


def test_path_origin_minted_for_resolved_path():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, None, ["src/a.py"])
    assert origins  # a path is a perfectly good aim
    assert all(o == {"stated_path"} for o in origins.values())


def test_need_origin_minted_for_anchored_need_term():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, "alpha_widget", [])
    assert origins["alpha_widget"] == {"stated_need"}


def test_unresolved_item_mints_no_origins():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, None, ["nonexistent_thing"])
    assert origins == {}


def test_unanchored_need_mints_no_origins():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, "zzzq unanchored blorp", [])
    assert origins == {}


def test_term_minted_by_symbol_and_need_carries_both_origins():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget")]
    origins, _ = _origins(chunks, "alpha_widget", ["alpha_widget"])
    assert origins["alpha_widget"] == {"stated_symbol", "stated_need"}


# --- origin threading into candidate construction ----------------------------

def test_stated_symbol_candidate_carries_origin():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    mandatory, reasons, _, idx_origins = identify_claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    assert 0 in mandatory
    assert "named_symbol" in reasons[0]
    assert idx_origins[0] == {"stated_symbol"}


def test_stated_path_candidate_carries_origin():
    chunks = [_chunk("a", "src/widget_handler.py", "def alpha_thing(): return 1",
                     symbol="alpha_thing", tokens=200)]
    resolution = resolve_stated_items(chunks, ["src/widget_handler.py"])
    stated_terms, _ = stated_claim_terms(None, resolution, chunks)
    stated_origins, _ = _origins(chunks, None, ["src/widget_handler.py"])
    mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    assert 0 in mandatory
    assert idx_origins[0] == {"stated_path"}


def test_stated_need_candidate_carries_origin():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    stated_terms, _ = stated_claim_terms("alpha_widget", None, chunks)
    stated_origins, _ = _origins(chunks, "alpha_widget", [])
    mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "unrelated phrasing entirely", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    assert 0 in mandatory
    assert idx_origins[0] == {"stated_need"}


def test_task_born_candidate_carries_no_origin():
    # The task text names the symbol; no stated flag is involved. The
    # claim is real but must not be credited to the agent's stated aim.
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "alpha_widget is broken", [], weights=WEIGHTS,
        stated_origins={})
    assert 0 in mandatory
    assert idx_origins == {}


def test_no_stated_origins_given_no_tags():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    _mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "alpha_widget is broken", [], weights=WEIGHTS)
    assert idx_origins == {}


def test_mixed_candidate_carries_stated_tags_alongside_task_claim():
    # The task names the file (task-born path claim) and also matches
    # the stated symbol term; both influences are real, and the stated
    # provenance is preserved on the candidate.
    chunks = [_chunk("a", "src/alpha_widget.py",
                     "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "look at src/alpha_widget.py", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    assert 0 in mandatory
    assert idx_origins[0] == {"stated_symbol"}


def test_test_pair_candidate_citing_nothing_gets_no_origin():
    # The pair claim flows from the source claim; the test chunk cites no
    # term of its own and must not be credited as an aimed admission.
    chunks = [
        _chunk("src", "src/q.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("tst", "tests/test_q.py",
               "def test_q(): pass", symbol="test_q", tokens=200),
    ]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    mandatory, reasons, _, idx_origins = identify_claim_candidates(
        chunks, "bland generic phrasing", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    pair_idx = {i for i, rs in reasons.items() if "test_pair" in rs}
    assert pair_idx == {1}  # the pair claim fired
    assert pair_idx.isdisjoint(idx_origins)


def test_test_chunk_citing_stated_terms_carries_origin_on_its_own_account():
    # Per-term attribution, not pair inheritance: a test chunk whose own
    # name cites stated-origin terms is tagged for THAT citation. The
    # pair claim itself mints no tags.
    chunks = [
        _chunk("src", "src/alpha_widget.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("tst", "tests/test_alpha_widget.py",
               "def test_case_one(): pass",
               symbol="test_case_one", tokens=200),
    ]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    mandatory, reasons, _, idx_origins = identify_claim_candidates(
        chunks, "bland generic phrasing", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    pair_idx = {i for i, rs in reasons.items() if "test_pair" in rs}
    assert pair_idx == {1}
    # chunk 1 cites stated terms through its own path basename: tagged
    # on its own account, not through the pair claim.
    assert idx_origins[1] == {"stated_symbol"}


def test_stated_term_also_in_task_text_is_credited_as_stated():
    # Attribution limit, pinned as behaviour: provenance is per term, not
    # per exclusivity. The task names the symbol verbatim AND the agent
    # stated it; the admission is credited as stated.
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    _mandatory, _reasons, _, idx_origins = identify_claim_candidates(
        chunks, "alpha_widget is broken", [], weights=WEIGHTS,
        stated_terms=stated_terms, stated_origins=stated_origins)
    assert idx_origins[0] == {"stated_symbol"}


def test_claim_candidates_accepts_stated_origins():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    tagged = claim_candidates(chunks, "unrelated phrasing entirely", [],
                              weights=WEIGHTS, stated_terms=stated_terms,
                              stated_origins=stated_origins)
    plain = claim_candidates(chunks, "unrelated phrasing entirely", [],
                             weights=WEIGHTS, stated_terms=stated_terms)
    assert tagged == plain  # origins never widen the claim set


# --- admission-side hand-off (select_evidence) ------------------------------

def test_claim_origins_handoff_records_admitted_stated_claim():
    chunks = [
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "docs/guide.md", "felines compare poorly", tokens=200),
    ]
    scores = _scores(chunks, "unrelated phrasing entirely")
    stated_terms, _ = stated_claim_terms(
        None, resolve_stated_items(chunks, ["alpha_widget"]), chunks)
    stated_origins, _ = _origins(chunks, None, ["alpha_widget"])
    _selected, diag = select_evidence(
        chunks, scores, "unrelated phrasing entirely", 1000, [],
        weights=WEIGHTS, stated_terms=stated_terms,
        stated_origins=stated_origins)
    handoff = diag["claim_origins"]
    assert handoff == {"a": ["stated_symbol"]}


def test_breadth_admission_is_not_recorded_as_aim():
    # A stated-anchored claim is recorded only when the claims-first pass
    # admits it; a chunk that enters through breadth (one best chunk per
    # remaining path) is an ordinary admission, never an aimed one.
    chunks = [
        _chunk("b", "docs/guide.md", "felines compare poorly", tokens=200),
    ]
    scores = _scores(chunks, "unrelated phrasing entirely")
    # stated term anchors to nothing in b, so b enters via breadth with
    # an empty origin hand-off even though the flag was given.
    selected, diag = select_evidence(
        chunks, scores, "unrelated phrasing entirely", 1000, [],
        weights=WEIGHTS, stated_terms={"alpha_widget"},
        stated_origins={"alpha_widget": {"stated_need"}})
    assert [c.chunk_id for c in selected] == ["b"]
    assert diag["claim_origins"] == {}


def test_no_stated_origins_no_handoff_key():
    chunks = [_chunk("a", "src/a.py", "def alpha_widget(): return 1",
                     symbol="alpha_widget", tokens=200)]
    scores = _scores(chunks, "alpha_widget is broken")
    _selected, diag = select_evidence(
        chunks, scores, "alpha_widget is broken", 1000, [],
        weights=WEIGHTS)
    assert "claim_origins" not in diag
