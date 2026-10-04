"""Authority flags: developer-crowned sources pin as mandatory.

Portable (no silicon deps): match_authority is stdlib fnmatch; pinning
reuses the explicit-path mandatory mechanism, scoring untouched.
"""
from ane_context_harness.authority import match_authority
from ane_context_harness.retrieval.selector import select_evidence
from ane_context_harness.schemas import ChunkScore

from tests.unit.test_selector import _chunk, _scores, WEIGHTS


def _ranked_scores(chunks, order):
    """Manual ranking: first id in order scores highest (lexical content aside)."""
    n = len(chunks)
    return [ChunkScore(chunk_id=c.chunk_id,
                       initial_score=float(n - order.index(c.chunk_id)))
            for c in chunks]


def test_match_authority_exact_glob_and_basename():
    assert match_authority("docs/pricing-rules.md", ["docs/pricing-rules.md"])
    assert match_authority("docs/pricing-rules.md", ["docs/*.md"])
    assert match_authority("docs/pricing-rules.md", ["pricing-rules.md"])
    assert match_authority("a/b/docs/pricing-rules.md", ["docs/pricing-rules.md"])
    assert match_authority("README.md", ["docs/pricing-rules.md"]) == []
    assert match_authority("docs/pricing-rules.md", []) == []
    assert match_authority("docs/pricing-rules.md", ["", None]) == []


def test_authority_pins_over_higher_scoring_stale_doc():
    # Stale README outranks the authoritative rules doc, and the budget
    # fits only one chunk: without the flag the README wins and the rules
    # doc is dropped; with it the rules doc is retained (mandatory) and
    # reported as fired.
    rules = _chunk("rules", "docs/pricing-rules.md",
                   "authoritative concession rounding policy")
    stale = _chunk("stale", "README.md",
                   "warehouse stock audit shelves history")
    chunks = [rules, stale]
    task = "warehouse stock audit"
    budget = stale.estimated_tokens  # fits exactly one chunk
    assert rules.estimated_tokens <= budget  # either chunk fits alone

    scores = _ranked_scores(chunks, ["stale", "rules"])
    plain, _ = select_evidence(chunks, scores, task, token_budget=budget,
                               explicit_paths=[], weights=WEIGHTS)
    assert [c.path for c in plain] == ["README.md"]

    scores2 = _ranked_scores(chunks, ["stale", "rules"])
    flagged, diag = select_evidence(
        chunks, scores2, task, token_budget=budget, explicit_paths=[],
        weights=WEIGHTS, authority_paths=["docs/pricing-rules.md"])
    assert "docs/pricing-rules.md" in [c.path for c in flagged]
    assert diag["authority_flags"] == ["docs/pricing-rules.md"]


def test_authority_empty_by_default():
    chunks = [_chunk("a", "src/discount.py", "def calculate_discount",
                     symbol="calculate_discount")]
    scores = _scores(chunks, "discount fix")
    _, diag = select_evidence(chunks, scores, "discount fix", token_budget=100,
                             explicit_paths=[], weights=WEIGHTS)
    assert diag["authority_flags"] == []
