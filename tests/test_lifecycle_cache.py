"""Model-lifecycle + cache regression protection (WS2).

Pins the 4,400 ms repeated-loading fix: for a stable pipeline/artifact/profile
state, artifact resolution, runtime construction and model load happen ONCE;
every request still runs predictions; fallback stays false and the backend
stays the calibrated one. Also covers every invalidation dimension,
single-flight concurrency, bounded size, stale/corrupt artifacts, failure
recovery, shutdown and telemetry privacy.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from ane_context_harness.coreml.lifecycle import LifecycleMetrics
from ane_context_harness.retrieval.model_cache import RerankerCache
from ane_context_harness.retrieval.reranker import RerankDecision

PROFILE_COREML = {
    "profile_version": 1,
    "calibration_fingerprint": "machine-mac-phase01",
    "behavioral_profile": "BALANCED",
    "features": {"reranker": {"enabled": True, "backend": "coreml_all",
                              "warm_p95_ms": 4.0}},
}


class FakeFacade:
    """Stands in for RerankerFacade: counts construction/load/predict/close."""

    constructions = []
    load_calls = []
    closed = []

    def __init__(self, profile, artifact, metrics=None):
        self.profile = profile
        self.model_artifact = artifact
        self.metrics = metrics
        self._decision = None
        FakeFacade.constructions.append(self)
        if metrics is not None:
            metrics.incr("runtime_construction_count")

    def decision(self):
        if self._decision is None:
            art = self.model_artifact
            if art is None or not art.exists():
                self._decision = RerankDecision(
                    backend="cpu_deterministic", ml_used=False, fallback=True,
                    reason="coreml_model_not_bundled", model_version="none")
            else:
                FakeFacade.load_calls.append(art.model_path)
                if self.metrics is not None:
                    self.metrics.incr("model_load_count")
                self._decision = RerankDecision(
                    backend="coreml_all", ml_used=True, fallback=False,
                    reason="profile_qualified_and_loaded",
                    model_version=art.model_version)
        return self._decision

    def rerank(self, task, chunks, top_n):
        # scores associated with INPUT chunks: value derived from content
        if self.metrics is not None:
            self.metrics.incr("prediction_count", max(1, len(chunks)))
        return [float(len(c.content)) for c in chunks]

    def close(self):
        FakeFacade.closed.append(self)


class FakeArtifact:
    def __init__(self, model_path: Path, model_version="v1", seq_len=128):
        self.model_id = "cross-encoder/fake"
        self.revision = "f" * 40
        self.model_version = model_version
        self.seq_len = seq_len
        self.model_path = str(model_path)
        self.vocab_path = ""
        self.tokenizer_config_path = ""
        self.checksums = {"model.mlpackage": "aa" * 32}
        self.numeric_validation = {}

    def exists(self) -> bool:
        return Path(self.model_path).exists()


@pytest.fixture()
def state(tmp_path, monkeypatch):
    FakeFacade.constructions = []
    FakeFacade.load_calls = []
    FakeFacade.closed = []
    monkeypatch.setattr("ane_context_harness.retrieval.model_cache.RerankerFacade",
                        FakeFacade)
    art_dir = tmp_path / "artifact"
    art_dir.mkdir()
    model = art_dir / "model.mlpackage"
    model.mkdir()
    (model / "data.bin").write_text("v1", encoding="utf-8")
    meta = art_dir / "metadata.json"
    meta.write_text(json.dumps({"seq_len": 128}), encoding="utf-8")
    cal = tmp_path / "calibration_report.json"
    cal.write_text(json.dumps({"measurements": {"reranker": {"enabled": True}}}),
                   encoding="utf-8")

    cfg = {"coreml": {"calibration_report": str(cal)},
           "retrieval": {"lexical_weight": 0.35},
           "limits": {}, "runtime": {}}
    art = FakeArtifact(model)
    state = {
        "artifact": art, "meta": meta, "cal": cal, "cfg": cfg, "tmp": tmp_path,
        "profile": dict(PROFILE_COREML),
    }
    cache = RerankerCache(
        profile_provider=lambda: state["profile"],
        artifact_provider=lambda: state["artifact"],
        config_provider=lambda: state["cfg"],
        runtime_fingerprint={"test": "fp-1"},
    )
    state["cache"] = cache
    state["metrics"] = cache.metrics
    return state


def test_five_sequential_requests_load_once_predict_every_time(state):
    cache, metrics = state["cache"], state["metrics"]
    for i in range(5):
        facade, decision = cache.get()
        assert decision.fallback is False
        assert decision.backend == "coreml_all"
        scores = facade.rerank(f"task {i}", [type("C", (), {"content": "abc"})()], 1)
        assert scores == [3.0]  # prediction associated with input chunk
    snap = metrics.snapshot()
    assert snap["artifact_resolution_count"] == 1
    assert snap["runtime_construction_count"] == 1
    assert snap["model_load_count"] == 1
    assert len(FakeFacade.constructions) == 1
    assert snap["prediction_count"] == 5     # one predict call per request
    assert snap["cache_hit_count"] == 4
    assert snap["fallback_count"] == 0


def test_prediction_scores_stay_associated_with_chunks(state):
    facade, _ = state["cache"].get()
    a = type("C", (), {"content": "alpha"})()
    b = type("C", (), {"content": "beta"})()
    assert facade.rerank("t", [a, b], 2) == [5.0, 4.0]
    assert facade.rerank("t", [b, a], 2) == [4.0, 5.0]  # order respected


def _rebuild_cache(state, **over):
    kwargs = dict(
        profile_provider=lambda: state["profile"],
        artifact_provider=lambda: state["artifact"],
        config_provider=lambda: state["cfg"],
        runtime_fingerprint={"test": "fp-1"},
        metrics=over.pop("metrics", None),
    )
    kwargs.update(over)
    return RerankerCache(**kwargs)


def test_invalidation_on_artifact_metadata_change(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    assert len(FakeFacade.constructions) == 1
    # artifact metadata/checksum file changes (size differs -> stat changes)
    state["meta"].write_text(json.dumps({"seq_len": 256, "pad": "x" * 8}),
                             encoding="utf-8")
    facade, decision = cache.get()
    assert decision.fallback is False
    assert len(FakeFacade.constructions) == 2
    assert metrics.snapshot()["cache_invalidation_count"] >= 1


def test_invalidation_on_calibration_report_change(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    state["cal"].write_text(json.dumps({"measurements": {"reranker": {"enabled": True, "rev": 2}}}),
                            encoding="utf-8")
    cache.get()
    assert len(FakeFacade.constructions) == 2
    assert metrics.snapshot()["cache_invalidation_count"] >= 1


def test_invalidation_on_profile_schema_version_change(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    state["profile"]["profile_version"] = 2  # capability-profile schema bump
    cache.get()
    assert len(FakeFacade.constructions) == 2


def test_invalidation_on_runtime_fingerprint_change(state):
    fp = {"macos_version": "15.0", "coremltools_version": "9.0"}
    cache = _rebuild_cache(state, runtime_fingerprint=fp)
    cache.get()
    assert len(FakeFacade.constructions) == 1
    fp["macos_version"] = "16.0"  # macOS/Core ML runtime fingerprint changes
    cache.get()
    assert len(FakeFacade.constructions) == 2


def test_invalidation_on_harness_config_change(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    state["cfg"]["retrieval"]["lexical_weight"] = 0.50
    cache.get()
    assert len(FakeFacade.constructions) == 2


def test_invalidation_on_model_file_change(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    model_file = Path(state["artifact"].model_path) / "data.bin"
    model_file.write_text("corrupted-or-upgraded-weights", encoding="utf-8")
    facade, decision = cache.get()
    assert len(FakeFacade.constructions) == 2
    assert decision.fallback is False
    assert metrics.snapshot()["cache_invalidation_count"] >= 1


def test_concurrent_first_requests_single_construction(state):
    cache, metrics = state["cache"], state["metrics"]
    orig_init = FakeFacade.__init__

    def slow_init(self, profile, artifact, metrics=None):
        time.sleep(0.05)
        orig_init(self, profile, artifact, metrics)

    FakeFacade.__init__ = slow_init
    results = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait(timeout=5)
        results.append(cache.get())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    FakeFacade.__init__ = orig_init
    assert len(FakeFacade.constructions) == 1, "duplicate model loads"
    assert len(results) == 8
    assert all(d.backend == "coreml_all" and not d.fallback for _, d in results)
    snap = metrics.snapshot()
    assert snap["model_load_count"] == 1
    assert snap["concurrent_construction_prevented_count"] >= 1


def test_no_lock_held_during_inference(state):
    """Two concurrent rerank calls must overlap (no cache lock around predict)."""
    facade, _ = state["cache"].get()
    barrier = threading.Barrier(2, timeout=5)
    orig_rerank = facade.rerank

    def blocking_rerank(task, chunks, top_n):
        barrier.wait()
        return orig_rerank(task, chunks, top_n)

    facade.rerank = blocking_rerank
    errors = []

    def worker():
        try:
            facade.rerank("t", [type("C", (), {"content": "x"})()], 1)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, f"concurrent inference serialized or failed: {errors}"


def test_bounded_cache_size(state):
    cache = _rebuild_cache(state, max_entries=2)
    # distinct validity keys coexisting (e.g. racing configs) must be LRU-bounded
    for i in range(3):
        cache._build_entry(f"key-{i}")
    assert cache.entry_count() <= 2
    assert cache.metrics.snapshot()["cache_eviction_count"] >= 1


def test_stale_artifact_rejected(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    import shutil
    shutil.rmtree(state["artifact"].model_path)  # artifact disappears
    facade, decision = cache.get()
    assert decision.ml_used is False and decision.fallback is True
    assert metrics.snapshot()["cache_invalidation_count"] >= 1


def test_corrupted_build_recovers(state):
    cache, metrics = state["cache"], state["metrics"]
    calls = {"n": 0}
    real_factory = FakeFacade

    def flaky_factory(profile, artifact, metrics=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("corrupted model package")
        return real_factory(profile, artifact, metrics)

    cache = _rebuild_cache(state, facade_factory=flaky_factory)
    facade, decision = cache.get()
    assert decision.fallback is True            # deterministic fallback
    assert decision.ml_used is False
    assert cache.metrics.snapshot()["fallback_count"] >= 1
    facade, decision = cache.get()              # recovery on next call
    assert decision.fallback is False and decision.backend == "coreml_all"


def test_persistent_failure_keeps_deterministic_fallback(state):
    def always_broken(profile, artifact, metrics=None):
        raise OSError("still corrupted")

    cache = _rebuild_cache(state, facade_factory=always_broken)
    for _ in range(3):
        facade, decision = cache.get()
        assert decision.ml_used is False
        assert decision.fallback is True
    assert cache.metrics.snapshot()["fallback_count"] >= 3


def test_clean_shutdown(state):
    cache, metrics = state["cache"], state["metrics"]
    cache.get()
    cache.close()
    assert len(FakeFacade.closed) == 1
    assert metrics.snapshot()["shutdown_count"] == 1
    facade, decision = cache.get()   # closed cache keeps serving deterministically
    assert decision.ml_used is False
    cache.close()                    # idempotent


def test_telemetry_has_no_source_text(state):
    cache, metrics = state["cache"], state["metrics"]
    facade, decision = cache.get()
    secret = "SUPER_SECRET_SOURCE_TOKEN = 'hunter2'"
    facade.rerank("t", [type("C", (), {"content": secret})()], 1)
    snap_json = json.dumps(metrics.snapshot())
    assert secret not in snap_json
    assert "hunter2" not in snap_json


def test_pipeline_select_context_loads_once(monkeypatch, tmp_path):
    """End-to-end: 5 select_context calls -> one construction, predictions each."""
    from ane_context_harness.config import build_config
    from ane_context_harness.pipeline import Pipeline
    import ane_context_harness.retrieval.model_cache as mc

    FakeFacade.constructions = []
    FakeFacade.load_calls = []
    FakeFacade.closed = []
    monkeypatch.setattr(mc, "RerankerFacade", FakeFacade)

    # fake qualified calibration report -> profile qualifies coreml_all
    cal = tmp_path / "calibration_report.json"
    cal.write_text(json.dumps({"measurements": {"reranker": {
        "backend": "coreml_all", "enabled": True,
        "measured_speedup_percent": 100.0, "warm_p95_ms": 4.0,
        "failure_rate_percent": 0.0, "numerical_validation": "passed"}}}),
        encoding="utf-8")
    # fake artifact
    art = tmp_path / "art"
    (art / "model.mlpackage").mkdir(parents=True)
    (art / "metadata.json").write_text(json.dumps({"seq_len": 128}), encoding="utf-8")
    (art / "tokenizer").mkdir()
    (art / "tokenizer" / "vocab.txt").write_text("[PAD]\n", encoding="utf-8")

    cfg = build_config({
        "index": {"storage_path": str(tmp_path / "store")},
        "privacy": {"never_read": ["**/.env*"]},
        "coreml": {"calibration_report": str(cal), "artifact_path": str(art)},
    })
    pipe = Pipeline(cfg)
    repo = str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synthetic_ts_project")
    pipe.register_repository(repo, "ts", False)
    from ane_context_harness import schemas
    req = schemas.SelectRequest(repository_id="ts", task="fix the discount bug",
                                token_budget=500, explicit_paths=[])
    backends = []
    for i in range(5):
        pkg = pipe.select_context(req)
        backends.append(pkg.execution["reranker"])
        assert pkg.execution["fallback_used"] is False
        assert pkg.execution["reranker"] == "coreml_all"
        assert "reranker_ms" in pkg.metrics
    snap = pipe.lifecycle_metrics()
    assert len(FakeFacade.constructions) == 1
    assert snap["model_load_count"] == 1
    assert snap["prediction_count"] > 0          # every request predicted
    assert snap["cache_hit_count"] == 4
    assert snap["fallback_count"] == 0
    assert backends == ["coreml_all"] * 5
    pipe.close()
    assert pipe.lifecycle_metrics()["shutdown_count"] == 1
