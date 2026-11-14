"""Regression tests for the claim contract (budget-honest packing).

Two defects are pinned here:

1. Test intent inferred from WHICH CHUNKS MATCHED is circular: a
   coincidental path match on a test file licenses every test chunk as a
   claim, and test evidence crowds out the implementation evidence the
   task asked for.
2. A task may need two symbols from ONE file. The blanket "one claim
   chunk per path" rule demoted the second chunk out of claim admission,
   and it was then blocked in depth as well, so the required chunk was
   lost.
3. When claims compete for the last fitting slot, admission is not
   allowed to run on overlap class and raw score alone; the claim whose
   matched terms are stronger task evidence is admitted first, and only
   equal-strength claims fall back to the overlap-class then score order.

All tests use synthetic chunks; no fixture repositories.
"""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.structural import aggregate_scores
from src.ane_context_harness.retrieval.selector import select_evidence
from src.ane_context_harness.schemas import RepositoryChunk


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10, "git_recency_weight": 0.05,
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


def _task_asks_about_tests(task, chunks):
    from src.ane_context_harness.retrieval.selector import (
        _task_asks_about_tests as impl,
    )
    return impl(task, chunks)


def test_test_intent_is_task_driven_not_match_driven():
    """A test file whose name shares a word with the task is not test intent."""
    chunks = [
        _chunk("impl", "src/reservations.py", "def create_hold(window): return window"),
        _chunk("test", "tests/test_reservations.py", "def test_create_hold(): assert True"),
    ]
    assert _task_asks_about_tests(
        "How does a reservation hold expire, and where is the 30-minute window applied?",
        chunks) is False


def test_test_intent_true_when_task_asks_about_tests():
    chunks = [
        _chunk("impl", "src/reservations.py", "def create_hold(window): return window"),
        _chunk("test", "tests/test_reservations.py", "def test_create_hold(): assert True"),
    ]
    assert _task_asks_about_tests("keep the tests green for reservations", chunks) is True


def test_test_intent_true_when_task_names_the_test_artifact():
    """Language-neutral: naming the test file stem is asking about tests."""
    chunks = [
        _chunk("impl", "src/discount_es.py", "def calcular_descuento(): return 0"),
        _chunk("test", "tests/test_discount_es.py", "def test_descuento(): assert True"),
    ]
    assert _task_asks_about_tests("revisa test_discount_es y corrige el fallo", chunks) is True


def test_unrelated_test_chunk_does_not_evict_required_evidence():
    """Test claims must not crowd out the implementation evidence.

    Budget is tight enough that an admitted test pair pushes the required
    implementation chunk out of the pack.
    """
    chunks = [
        _chunk("impl_a", "src/reservations.py", "def create_hold(window): return window",
               symbol="create_hold", tokens=200),
        _chunk("impl_b", "src/reservations.py", "class Hold: def expired(self): return True",
               symbol="Hold.expired", tokens=200),
        _chunk("test_a", "tests/test_reservations.py", "def test_create_hold(): assert True",
               symbol="test_create_hold", tokens=150),
        _chunk("test_b", "tests/test_pricing.py", "def test_pricing(): assert True",
               symbol="test_pricing", tokens=150),
    ]
    task = "How does create_hold expire a reservation, and where is Hold.expired applied?"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=600,
                                     explicit_paths=[], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "src/reservations.py" in paths
    assert len([c for c in selected if c.path == "src/reservations.py"]) == 2
    assert "tests/test_pricing.py" not in paths


def test_two_symbols_from_one_named_path_are_both_claims():
    """A task needing two symbols from one file keeps both while they fit."""
    chunks = [
        _chunk("impl_a", "src/reservations.py", "def create_hold(window): return window",
               symbol="create_hold", tokens=200),
        _chunk("impl_b", "src/reservations.py", "class Hold: def expired(self): return True",
               symbol="Hold.expired", tokens=200),
        _chunk("other", "src/availability.py", "def hold(): return None",
               symbol="hold", tokens=200),
    ]
    task = "How does a reservation hold expire, and where is the 30-minute window applied?"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=600,
                                     explicit_paths=[], weights=WEIGHTS)
    reservations = [c for c in selected if c.path == "src/reservations.py"]
    assert len(reservations) == 2
    total = sum(c.estimated_tokens for c in selected)
    assert total <= 600


def test_claims_admit_while_they_fit_the_budget():
    """Named-symbol claims fit: both admit; none are dropped."""
    chunks = [
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=200),
        _chunk("b", "src/b.py", "def beta_widget(): return 1",
               symbol="beta_widget", tokens=200),
    ]
    task = "alpha beta widget"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=500,
                                     explicit_paths=[], weights=WEIGHTS)
    assert diag["claims_admitted"] == 2
    assert diag["claims_dropped_budget"] == 0
    assert sum(c.estimated_tokens for c in selected) <= 500


def test_squeezed_budget_never_packs_claims_past_request():
    """Inferred claims that do not fit are dropped and counted, never forced."""
    chunks = [
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=400),
        _chunk("b", "src/b.py", "def beta_widget(): return 1",
               symbol="beta_widget", tokens=400),
        _chunk("c", "src/c.py", "def gamma_widget(): return 1",
               symbol="gamma_widget", tokens=400),
    ]
    task = "alpha beta gamma widget"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=500,
                                     explicit_paths=[], weights=WEIGHTS)
    assert sum(c.estimated_tokens for c in selected) <= 500
    assert diag["claims_admitted"] == 1
    assert diag["claims_dropped_budget"] == 2
    assert [c.path for c in selected] == ["src/a.py"]


def test_explicit_pin_stays_unconditional_past_the_budget():
    """The caller's own pin is admitted even when it exceeds the budget."""
    chunks = [
        _chunk("a", "src/a.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=400),
        _chunk("pin", "src/pin.py", "unrelated content here",
               tokens=600),
    ]
    task = "alpha widget"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=500,
                                     explicit_paths=["src/pin.py"], weights=WEIGHTS)
    assert any(c.path == "src/pin.py" for c in selected)
    assert diag["budget_exceeded"] is True
    assert diag["budget_feasible"] is False
    assert diag["unconditional_tokens"] == 600
    assert diag["claims_dropped_budget"] == 1


def test_breadth_admits_one_best_chunk_per_path():
    """Distinct paths enter the pack before any path gets a second chunk."""
    chunks = [
        _chunk("p1a", "src/alpha.py", "reserve window policy alpha", tokens=100),
        _chunk("p2", "src/beta.py", "reserve window policy beta", tokens=100),
        _chunk("p1b", "src/alpha.py", "gamma epsilon sigma delta", tokens=100),
    ]
    task = "reserve window policy"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=1000,
                                     explicit_paths=[], weights=WEIGHTS)
    assert diag["breadth_chunks"] == 2  # one chunk per distinct path
    assert diag["depth_chunks"] == 1    # the second chunk of the same path
    assert diag["breadth_paths"] == 2
    assert {c.path for c in selected} == {"src/alpha.py", "src/beta.py"}


def test_tail_reserve_fills_crowded_out_chunk():
    """A chunk crowded out of the core budget still fits the reserved tail."""
    chunks = [
        _chunk("claim", "src/discount.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=190),
        _chunk("tail", "src/notes.py", "gamma epsilon sigma delta",
               tokens=10),
    ]
    task = "alpha widget"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=200,
                                     explicit_paths=[], weights=WEIGHTS)
    assert any(c.path == "src/notes.py" for c in selected)
    assert diag["tail_fill"] == 1
    assert diag["used_tokens"] == 200
    assert diag["budget_exceeded"] is False


def test_duplicate_chunk_ids_do_not_double_bill_the_budget():
    """Duplicate index rows are admitted once, not once per row."""
    chunks = [
        _chunk("dup", "src/dup.py", "def alpha_widget(): return 1",
               symbol="alpha_widget", tokens=100),
        _chunk("dup", "src/dup.py", "def alpha_widget(): return 2",
               symbol="alpha_widget", tokens=100),
    ]
    task = "alpha widget"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=1000,
                                     explicit_paths=[], weights=WEIGHTS)
    assert len([c for c in selected if c.path == "src/dup.py"]) == 1
    assert diag["claims_admitted"] == 1
    assert diag["used_tokens"] == 100
    assert diag["per_file_tokens"]["src/dup.py"] == 100


def test_per_file_cap_demotes_excess_symbol_claims():
    """A file with many task-matching symbols keeps only the top claims."""
    symbols = ["alpha", "beta", "gamma", "delta"]
    chunks = [_chunk(f"s{n}", "src/big.py", f"def {sym}(): return {n}",
                     symbol=sym, tokens=10)
              for n, sym in enumerate(symbols)]
    task = "alpha beta gamma delta"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=1000,
                                     explicit_paths=[], weights=WEIGHTS)
    demoted = [c for c in scores
               if "mandatory_demoted_per_file_cap" in c.selection_reasons]
    assert len(demoted) == 2
    assert diag["mandatory_count"] == 2


def _identify(chunks, task, explicit_paths=None):
    from src.ane_context_harness.retrieval.selector import (
        identify_claim_candidates,
    )
    return identify_claim_candidates(chunks, task, explicit_paths or [])


def test_named_path_claim_via_inflection_fold():
    """An -ing token in the task folds to its base stem for path matching."""
    chunks = [_chunk("doc", "docs/pricing-rules.md",
                     "The cap applies to every concession.")]
    idx, reasons, _ = _identify(
        chunks, "What caps apply to the customer's price concession?")
    assert idx == {0}
    assert "named_path" in reasons[0]


def test_specificity_gate_rejects_terms_ubiquitous_across_files():
    """A term named by more files than the floor pins nothing."""
    chunks = [_chunk(f"c{n}", f"src/m{n}.py", f"def delta_{n}(): return {n}",
                     symbol=f"delta_{n}")
              for n in range(4)]
    idx, reasons, _ = _identify(chunks, "delta handling")
    assert idx == set()
    assert all("named_symbol" not in rs for rs in reasons.values())


def test_specificity_gate_keeps_rare_terms():
    chunks = [_chunk("c", "src/zephyr.py", "def zephyr_handler(): return 1",
                     symbol="zephyr_handler")]
    idx, reasons, _ = _identify(chunks, "zephyr handling")
    assert idx == {0}
    assert "named_symbol" in reasons[0]


def test_intent_boilerplate_terms_never_pin_files():
    """Prompt-navigation vocabulary pins nothing by itself."""
    chunks = [_chunk("c", "src/render.py", "def render_name(): return 1",
                     symbol="render_name")]
    idx, reasons, _ = _identify(chunks, "Name the relevant files")
    assert idx == set()
    assert all("named_symbol" not in rs for rs in reasons.values())


def test_required_path_claim_leads_discretionary_claim():
    """A required path's claim is admitted before a higher-scored
    discretionary claim while both compete for the budget."""
    chunks = [
        _chunk("cand", "src/apply.ts", "def apply(): return 1",
               symbol="apply", tokens=400),
        _chunk("req", "docs/pricing-rules.md",
               "the cap and the rounding rule", tokens=400),
    ]
    task = "apply the rounding rule"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(
        chunks, scores, task, token_budget=450, explicit_paths=[],
        weights=WEIGHTS, required_paths=["docs/pricing-rules.md"])
    paths = [c.path for c in selected]
    assert "docs/pricing-rules.md" in paths
    assert "src/apply.ts" not in paths
    assert diag["claims_dropped_budget"] == 1


def _filler_chunks(n, tokens=10):
    return [_chunk(f"filler{k}", f"src/filler{k}.py",
                   "apply apply apply yard stick minted", tokens=tokens)
            for k in range(n)]


def test_stronger_task_evidence_wins_last_slot_over_higher_score():
    """The claim whose terms are stronger task evidence wins the last slot
    even though the competing claim scores higher."""
    chunks = [
        _chunk("a", "src/apply.ts", "def apply_config(order): return order",
               symbol="applyConfig", tokens=200),
        _chunk("b", "docs/pricing-rules.md",
               "Concessions are rounded at the line level.", tokens=200),
        *_filler_chunks(6),
    ]
    task = "apply the rounding rule"
    scores = _scores(chunks, task)
    assert scores[0].initial_score > scores[1].initial_score
    selected, diag = select_evidence(chunks, scores, task, token_budget=250,
                                     explicit_paths=[], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "docs/pricing-rules.md" in paths
    assert "src/apply.ts" not in paths
    assert diag["claims_admitted"] == 1
    assert diag["claims_dropped_budget"] == 1
    assert sum(c.estimated_tokens for c in selected) <= 250


def test_equal_relevance_orders_by_overlap_class_then_score():
    """Equal-strength claims fall back to the overlap class, then score."""
    # Same matched term on both claims -> equal relevance; the class decides
    # even though the path claim carries the higher score.
    chunks = [
        _chunk("doc", "docs/rule-guide.md", "rule reference notes",
               tokens=200),
        _chunk("impl", "src/rule_engine.ts", "def rule_engine(): return 1",
               symbol="ruleEngine", tokens=200),
    ]
    task = "apply the rounding rule"
    scores = _scores(chunks, task)
    selected, _ = select_evidence(chunks, scores, task, token_budget=250,
                                  explicit_paths=[], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "src/rule_engine.ts" in paths
    assert "docs/rule-guide.md" not in paths
    # Same class as well -> the higher score is admitted.
    chunks = [
        _chunk("doc1", "docs/rule-guide.md", "rule reference notes",
               tokens=200),
        _chunk("doc2", "docs/rule-archive.md", "rule archive notes",
               tokens=200),
    ]
    task = "apply the rounding rule"
    scores = _scores(chunks, task)
    selected, _ = select_evidence(chunks, scores, task, token_budget=250,
                                  explicit_paths=[], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "docs/rule-guide.md" in paths
    assert "docs/rule-archive.md" not in paths


def test_pricing_doc_packs_without_labels_on_tight_budget():
    """The pricing doc survives on task evidence alone, no required_paths.

    Distilled from the doc-vs-code competition under a budget that fits
    only one of the two claims, with corpus terms that make the code
    claim's matched term the weaker signal."""
    chunks = [
        _chunk("apply", "src/discounts/apply.ts",
               "export function applyPromo(lines, promoCode): number { return lines.length }",
               tokens=310,
               metadata={"file_symbols": ["computeDiscount", "tierRate",
                                          "applyPromo", "applyLoyalty",
                                          "describePolicy"]}),
        _chunk("rules", "docs/pricing-rules.md",
               "Concessions are rounded at the line level.",
               tokens=240),
        *_filler_chunks(6),
    ]
    task = "What is the authoritative rounding rule and the order in which charges are applied?"
    scores = _scores(chunks, task)
    selected, diag = select_evidence(chunks, scores, task, token_budget=450,
                                     explicit_paths=[], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "docs/pricing-rules.md" in paths
    assert "src/discounts/apply.ts" not in paths
    assert diag["claims_admitted"] == 1
    assert sum(c.estimated_tokens for c in selected) <= 450
