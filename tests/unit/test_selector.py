"""Tests for token-budgeted selector: budget enforcement, mandatory, stable order."""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.structural import aggregate_scores
from src.ane_context_harness.retrieval.selector import (
    select_evidence, compute_final_scores, categorize, CATEGORY_ORDER,
    recovery_prompt,
)
from src.ane_context_harness.schemas import RepositoryChunk, ChunkScore


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10, "git_recency_weight": 0.05,
    "diversity_lambda": 0.25, "top_k_for_diversity": 60,
}


def _chunk(cid, path, text, symbol=None):
    terms = lex_terms(text)
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=path, language="python",
        start_line=1, end_line=2, symbol=symbol, content_hash="h",
        estimated_tokens=len(terms), lexical_terms=tuple(terms),
        content=text, metadata={},
    )


def _scores(chunks, task):
    bm = [1.0 - i * 0.05 for i in range(len(chunks))]
    return aggregate_scores(chunks, task, [], WEIGHTS, bm)


def test_budget_enforced():
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount", symbol="calculate_discount"),
        _chunk("b", "src/inventory.py", "class Inventory warehouse stock"),
        _chunk("c", "src/reporting.py", "def build_report long text here"),
        _chunk("d", "src/analytics.py", "analytics unrelated metrics"),
    ]
    scores = _scores(chunks, "discount fix")
    selected, diag = select_evidence(chunks, scores, "discount fix", token_budget=10,
                                     explicit_paths=[], weights=WEIGHTS)
    total = sum(c.estimated_tokens for c in selected)
    assert total <= 10 + 0  # within budget (allow exact)


def test_mandatory_explicit_path_retained():
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount", symbol="calculate_discount"),
        _chunk("b", "src/inventory.py", "class Inventory warehouse stock stuff"),
    ]
    scores = _scores(chunks, "discount fix")
    selected, diag = select_evidence(chunks, scores, "discount fix", token_budget=3,
                                     explicit_paths=["src/inventory.py"], weights=WEIGHTS)
    paths = [c.path for c in selected]
    assert "src/inventory.py" in paths  # mandatory overrides budget
    assert diag["budget_exceeded"] is True


def test_named_symbol_mandatory():
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount", symbol="calculate_discount"),
        _chunk("b", "src/inventory.py", "class Inventory warehouse"),
    ]
    scores = _scores(chunks, "discount fix")
    selected, diag = select_evidence(chunks, scores, "discount fix", token_budget=2,
                                     explicit_paths=[], weights=WEIGHTS)
    # Budget contract: a named-symbol claim admits only while it fits; a
    # claim that cannot fit is dropped and counted, not forced in.
    assert not any(c.symbol == "calculate_discount" for c in selected)
    assert diag["claims_dropped_budget"] >= 1
    # Explicit pins are the caller's own request and stay unconditional.
    scores = _scores(chunks, "discount fix")
    selected, diag = select_evidence(chunks, scores, "discount fix", token_budget=2,
                                     explicit_paths=["src/discount.py"], weights=WEIGHTS)
    assert any(c.symbol == "calculate_discount" for c in selected)
    assert diag["budget_exceeded"] is True


def test_stable_ordering():
    chunks = [
        _chunk("a", "tests/test_discount.py", "test_discount", symbol="test_discount"),
        _chunk("b", "src/discount.py", "def calculate_discount", symbol="calculate_discount"),
        _chunk("c", "src/inventory.py", "class Inventory"),
    ]
    scores = _scores(chunks, "discount fix")
    selected, _ = select_evidence(chunks, scores, "discount fix", token_budget=100,
                                  explicit_paths=[], weights=WEIGHTS)
    cats = [categorize(c) for c in selected]
    # implementation (b) should come before test (a) per CATEGORY_ORDER
    assert "implementation" in cats
    impl_idx = cats.index("implementation")
    if "test" in cats:
        assert cats.index("test") > impl_idx


def test_empty_chunks_returns_empty():
    selected, diag = select_evidence([], [], "anything", token_budget=10,
                                    explicit_paths=[], weights=WEIGHTS)
    assert selected == []
    assert diag["selected_count"] == 0


def test_compute_final_scores_without_ml():
    chunks = [_chunk("a", "p.py", "def x", symbol="x"), _chunk("b", "q.py", "def y", symbol="y")]
    scores = _scores(chunks, "x fix")
    compute_final_scores(scores, WEIGHTS, use_ml=False, ml_scores=None)
    # normalized, max == 1
    assert max(s.final_score for s in scores) <= 1.0


def test_recovery_prompt_emission_branches():
    """The ask affordance fires only on considered evidence that was cut
    or a stated symbol that did not resolve, and the fired text carries
    the exact missed count taken from the recovery block plus the missed
    pointers — or nothing at all otherwise. Caught failure classes: a
    fabricated fire on a covered run (invented count, invented promise),
    an unstated run whose recovery block is empty saying anything at all,
    and two conditions opening two prompts instead of one."""
    assert recovery_prompt(None, None) is None
    assert recovery_prompt({}, []) is None
    assert recovery_prompt(None, [{"stated": "thing", "resolved": True,
                                   "matched_symbol": "thing",
                                   "matched_path": None}]) is None
    recovery = {"required_claims_total": 3, "required_claims_covered": 1,
                "required_evidence_recall": 0.3333,
                "missed_claims": [
                    {"chunk_id": "1", "path": "src/a.py", "symbol": "a",
                     "why": "budget", "reasons": ["claim_dropped_budget"],
                     "command": "rg a"},
                    {"chunk_id": "2", "path": "src/b.py", "symbol": None,
                     "why": "budget", "reasons": ["claim_dropped_budget"],
                     "command": "rg b"},
                    {"chunk_id": "3", "path": "src/c.py",
                     "symbol": "c_helper", "why": "capped",
                     "reasons": ["claim_capped"], "command": "rg c"}]}
    prompt = recovery_prompt(recovery, None)
    assert prompt is not None
    assert "2 required claims" in prompt
    assert "a (budget)" in prompt and "src/b.py (budget)" in prompt
    assert "--stated-symbol" in prompt and "--stated-need" in prompt
    paths_only = {"required_claims_total": 0, "required_claims_covered": 0,
                  "required_evidence_recall": 1.0,
                  "missed_claims": [],
                  "required_paths_total": 2, "required_paths_covered": 1,
                  "required_paths_recall": 0.5,
                  "missed_required_paths": [{"path": "src/gone.py",
                                             "why": "not_indexed"}]}
    prompt = recovery_prompt(paths_only, None)
    assert prompt is not None
    assert "1 required path" in prompt
    assert "src/gone.py (not_indexed)" in prompt
    assert "--stated-symbol" in prompt
    unresolved = recovery_prompt(
        None, [{"stated": "zzz_absent", "resolved": False,
                "matched_symbol": None, "nearest": [],
                "nearest_note": "no similar indexed symbols"}])
    assert unresolved is not None
    assert "Stated symbol(s) not found in index: zzz_absent." in unresolved
    assert "no similar indexed symbols" in unresolved
    with_nearest = recovery_prompt(
        None, [{"stated": "calcluate_discount", "resolved": False,
                "matched_symbol": None,
                "nearest": ["calculate_discount",
                            "calculate_total_with_discount"]}])
    assert "calculate_discount" in with_nearest
    both = recovery_prompt(
        recovery, [{"stated": "zzz_absent", "resolved": False,
                    "matched_symbol": None, "nearest": [],
                    "nearest_note": "no similar indexed symbols"}])
    assert both is not None
    assert "2 required claims" in both
    assert "Stated symbol(s) not found in index: zzz_absent." in both
    # One affordance, not two: the re-select instruction appears once.
    assert both.count("--stated-symbol") == 1
