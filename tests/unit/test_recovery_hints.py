"""Required-evidence recovery block: coverage accounting for named claims."""
from __future__ import annotations

from src.ane_context_harness.indexing.chunking import lex_terms
from src.ane_context_harness.retrieval.selector import select_evidence
from src.ane_context_harness.retrieval.structural import aggregate_scores
from src.ane_context_harness.schemas import RepositoryChunk


WEIGHTS = {
    "lexical_weight": 0.35, "symbol_weight": 0.25, "path_weight": 0.15,
    "dependency_weight": 0.10, "test_pair_weight": 0.10, "git_recency_weight": 0.05,
    "diversity_lambda": 0.25, "top_k_for_diversity": 60,
}


def _chunk(cid, path, text, symbol=None, tokens=None):
    terms = lex_terms(text)
    return RepositoryChunk(
        chunk_id=cid, repository_id="r", path=path, language="python",
        start_line=1, end_line=2, symbol=symbol, content_hash="h",
        estimated_tokens=tokens if tokens is not None else len(terms),
        lexical_terms=tuple(terms),
        content=text, metadata={},
    )


def _scores(chunks, task):
    bm = [1.0 - i * 0.05 for i in range(len(chunks))]
    return aggregate_scores(chunks, task, [], WEIGHTS, bm)


def test_starved_budget_emits_recovery_block_with_missed_claims():
    # Failure caught: required evidence the pack could not admit passes
    # unnoticed, and the agent's next turn guesses instead of re-selecting.
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount",
               symbol="calculate_discount", tokens=50),
        _chunk("b", "src/inventory.py", "class Inventory warehouse stock",
               tokens=50),
    ]
    scores = _scores(chunks, "calculate_discount fix")
    _, diag = select_evidence(chunks, scores, "calculate_discount fix",
                              token_budget=10, explicit_paths=[],
                              weights=WEIGHTS)
    rec = diag.get("recovery")
    assert rec is not None, "required evidence missed; block must be present"
    assert rec["required_claims_total"] >= 1
    assert rec["required_claims_covered"] == 0
    assert rec["required_evidence_recall"] == 0.0
    assert len(rec["missed_claims"]) >= 1
    entry = rec["missed_claims"][0]
    assert set(entry) == {"chunk_id", "path", "symbol", "why", "reasons", "command"}
    assert entry["why"] == "budget"
    assert "claim_dropped_budget" in entry["reasons"]
    assert rec["required_claims_total"] >= rec["required_claims_covered"] + 1


def test_covered_selection_emits_no_recovery_keys():
    # Failure caught: an additive disclosure that fires anyway leaks into
    # byte-identical covered runs and breaks the no-flag contract.
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount",
               symbol="calculate_discount", tokens=10),
        _chunk("b", "src/inventory.py", "class Inventory warehouse stock",
               tokens=10),
    ]
    scores = _scores(chunks, "calculate_discount fix")
    _, diag = select_evidence(chunks, scores, "calculate_discount fix",
                              token_budget=2000, explicit_paths=[],
                              weights=WEIGHTS)
    assert "recovery" not in diag
    assert "recovery_tool" not in diag


def test_claim_chunk_cap_emits_capped_reason():
    # Failure caught: a claim dropped only because of the chunk cap gets
    # reported as a budget miss, sending the agent to look for tokens it
    # does not need.
    chunks = [
        _chunk(f"c{i}", f"src/mod_{i}.py", f"def shared_symbol_{i}",
               symbol="shared_symbol", tokens=5)
        for i in range(3)
    ]
    scores = _scores(chunks, "shared_symbol")
    _, diag = select_evidence(chunks, scores, "shared_symbol",
                              token_budget=5, explicit_paths=[],
                              weights={**WEIGHTS, "max_claim_chunks": 1,
                                       "mandatory_symbol_specificity":
                                       {"enabled": False}})
    rec = diag.get("recovery")
    assert rec is not None
    whys = [m["why"] for m in rec["missed_claims"]]
    assert "capped" in whys
    assert any("claim_capped" in m["reasons"] for m in rec["missed_claims"])


def test_required_paths_uncovered_not_indexed_fires_block():
    # Failure caught: a benchmark-labelled required path with no indexed
    # chunk silently reads as covered.
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount",
               symbol="calculate_discount", tokens=10),
    ]
    scores = _scores(chunks, "calculate_discount fix")
    _, diag = select_evidence(chunks, scores, "calculate_discount fix",
                              token_budget=2000, explicit_paths=[],
                              weights=WEIGHTS,
                              required_paths=["src/discount.py",
                                              "docs/never_indexed.md"])
    rec = diag.get("recovery")
    assert rec is not None
    assert rec["required_paths_total"] == 2
    assert rec["required_paths_covered"] == 1
    assert rec["required_paths_recall"] == 0.5
    assert rec["missed_required_paths"] == [
        {"path": "docs/never_indexed.md", "why": "not_indexed"}]


def test_required_paths_all_covered_keeps_no_recovery_keys():
    # Failure caught: the paths half of the coverage check fires on covered
    # labels and reintroduces the covered-run noise.
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount",
               symbol="calculate_discount", tokens=10),
    ]
    scores = _scores(chunks, "calculate_discount fix")
    _, diag = select_evidence(chunks, scores, "calculate_discount fix",
                              token_budget=2000, explicit_paths=[],
                              weights=WEIGHTS,
                              required_paths=["src/discount.py"])
    assert "recovery" not in diag
    assert "recovery_tool" not in diag


def test_no_search_tools_emit_empty_commands(monkeypatch):
    # Failure caught: on a host with neither search tool the block still
    # emits a plausible-looking command the agent cannot run.
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    chunks = [
        _chunk("a", "src/discount.py", "def calculate_discount",
               symbol="calculate_discount", tokens=50),
    ]
    scores = _scores(chunks, "calculate_discount fix")
    _, diag = select_evidence(chunks, scores, "calculate_discount fix",
                              token_budget=10, explicit_paths=[],
                              weights=WEIGHTS)
    rec = diag.get("recovery")
    assert rec is not None
    assert diag["recovery_tool"] == {"rg": None, "grep": None}
    assert all(m["command"] == "" for m in rec["missed_claims"])


def test_missed_listing_bounded_but_counts_exact():
    # Failure caught: the block either floods the agent with more than the
    # listing cap, or lies about the totals to stay under it.
    chunks = []
    for i in range(8):
        chunks.append(_chunk(f"c{i}", f"src/mod_{i}.py",
                             f"def policy_engine_{i}", symbol="policy_engine",
                             tokens=50))
    scores = _scores(chunks, "policy_engine")
    _, diag = select_evidence(chunks, scores, "policy_engine",
                              token_budget=10, explicit_paths=[],
                              weights={**WEIGHTS,
                                       "mandatory_symbol_specificity":
                                       {"enabled": False}})
    rec = diag.get("recovery")
    assert rec is not None
    assert len(rec["missed_claims"]) <= 5
    assert rec["required_claims_total"] >= 6
    assert rec["required_claims_covered"] == 0
