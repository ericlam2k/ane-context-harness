"""Pipeline shortlist seam: claims outside top-K still reach the model.

Public-syncable: stdlib only, fixture repos only. The portable line ships a
deterministic backend; this exercises the dormant injection seam with a fake
model so a claim outside the deterministic top-K cannot be silently dropped.
"""
from __future__ import annotations

from ane_context_harness.config import build_config, merge
from ane_context_harness import schemas

FIXTURE = "tests/fixtures/synthetic_py_project"


class _FakeFacade:
    def __init__(self):
        self.seen_paths = []

    def rerank(self, task, chunks, top_n):
        self.seen_paths = [c.path for c in chunks]
        return [0.5] * len(chunks)


class _FakeDecision:
    ml_used = True
    backend = "deterministic_fake"
    fallback = False
    reason = None
    model_version = "fake"


class _FakeCache:
    def __init__(self):
        self.facade = _FakeFacade()

    def get(self):
        return self.facade, _FakeDecision()

    def close(self):
        pass


def _pipe(tmp_path):
    from ane_context_harness.pipeline import Pipeline
    base = {"index": {"storage_path": str(tmp_path / "store")}}
    pipe = Pipeline(build_config(merge(base, {})))
    pipe.register_repository(FIXTURE, "shortlist")
    return pipe


def test_pipeline_scores_claim_outside_top_k(tmp_path):
    pipe = _pipe(tmp_path)
    fake = _FakeCache()
    pipe._reranker_cache = fake
    pipe.retrieval["max_rerank_candidates"] = 1

    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="shortlist", task="Fix the discount calculation",
        token_budget=2000, explicit_paths=["src/analytics.py"]))

    diag = pkg.metrics["diagnostics"]["rerank_shortlist"]
    assert diag["active"] is True
    assert diag["claim_candidates"] >= 1
    assert diag["claims_outside_top_k"] >= 1
    assert "src/analytics.py" in fake.facade.seen_paths
    assert diag["shortlist_size"] > diag["max_candidates"]
    rel = diag["reliability"]
    assert rel["candidates_scored"] == diag["shortlist_size"]
    assert rel["invalid_predictions"] == 0
    assert rel["strict_validity"] is True


class _StatsFacade:
    def __init__(self):
        self.seen_paths = []

    def rerank_with_stats(self, task, chunks, top_n):
        self.seen_paths = [c.path for c in chunks]
        scores = [0.5] * len(chunks)
        scores[0] = None
        return scores, {
            "backend": "deterministic_fake",
            "candidates": len(chunks),
            "truncated_candidates": 2,
            "truncation_rate": round(2 / max(1, len(chunks)), 4),
            "invalid_predictions": 1,
            "strict_validity": False,
            "available": True,
        }


class _StatsCache:
    def __init__(self):
        self.facade = _StatsFacade()

    def get(self):
        return self.facade, _FakeDecision()

    def close(self):
        pass


def test_pipeline_discloses_rerank_reliability(tmp_path):
    pipe = _pipe(tmp_path)
    pipe._reranker_cache = _StatsCache()
    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="shortlist", task="Fix the discount calculation",
        token_budget=2000))

    rel = pkg.metrics["diagnostics"]["rerank_shortlist"]["reliability"]
    assert rel["candidates_scored"] > 0
    assert rel["truncated_candidates"] == 2
    assert rel["invalid_predictions"] == 1
    assert rel["strict_validity"] is False
    assert rel["fallback_used"] is False


class _IdFacade:
    def __init__(self):
        self.seen_ids = []

    def rerank(self, task, chunks, top_n):
        self.seen_ids = [c.chunk_id for c in chunks]
        return [0.5] * len(chunks)


class _IdCache:
    def __init__(self):
        self.facade = _IdFacade()

    def get(self):
        return self.facade, _FakeDecision()

    def close(self):
        pass


def test_pipeline_shortlist_is_score_ordered_not_index_ordered(tmp_path, monkeypatch):
    """The reranker must see the highest-scored chunks first, not index
    order."""
    from ane_context_harness.schemas import ChunkScore

    pipe = _pipe(tmp_path)
    fake = _IdCache()
    pipe._reranker_cache = fake
    pipe.retrieval["max_rerank_candidates"] = 2

    recorded = {}

    def scrambled_aggregate_scores(chunks, task, explicit_paths, weights, bm25_scores):
        recorded["chunks"] = list(chunks)
        return [ChunkScore(chunk_id=c.chunk_id,
                           initial_score=float(i + 1))
                for i, c in enumerate(chunks)]

    monkeypatch.setattr(
        "ane_context_harness.pipeline.aggregate_scores",
        scrambled_aggregate_scores)

    pipe.select_context(schemas.SelectRequest(
        repository_id="shortlist", task="Fix the discount calculation",
        token_budget=2000))

    chunks = recorded["chunks"]
    assert len(chunks) >= 2
    seen = fake.facade.seen_ids
    # Top-2 (score order) must lead the shortlist; claim candidates may
    # follow.
    assert seen[:2] == [chunks[-1].chunk_id, chunks[-2].chunk_id]


def test_deterministic_backend_reports_shortlist_inactive(tmp_path):
    """With no injected backend the seam reports active:false."""
    pipe = _pipe(tmp_path)
    pkg = pipe.select_context(schemas.SelectRequest(
        repository_id="shortlist", task="Fix the discount calculation",
        token_budget=2000))

    diag = pkg.metrics["diagnostics"]["rerank_shortlist"]
    assert diag["active"] is False
    assert diag["backend"] == "cpu_deterministic"
    assert diag["claim_protection"] is False
    assert diag["reliability"]["candidates_scored"] == 0
