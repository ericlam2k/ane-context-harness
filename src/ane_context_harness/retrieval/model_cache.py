"""Keyed, single-flight reranker model cache.

Guards against the repeated-loading regression (4.4 s p50 from reloading the
``.mlpackage`` on every select): one facade — one Core ML runtime, one model
load — per stable (artifact, calibration, profile, runtime, configuration)
state. Subsequent requests are cache hits; predictions still run per request.

Design rules:
- single-flight construction per key (concurrent first requests share one load;
  a follower never duplicates the leader's load);
- per-key events only — no global lock is ever held across inference;
- artifact provider is consulted at BUILD time only; staleness of an existing
  entry is checked with cheap ``stat`` calls (per-file stats of the model
  package + metadata.json — catches in-place weight edits);
- the validity key covers calibration-report content, capability profile,
  OS/Core ML runtime fingerprint and the relevant harness configuration;
- bounded LRU eviction; explicit close() for clean shutdown;
- build/load failures are NOT cached — the caller gets a deterministic
  fallback this call and the next call retries (recovery path).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _pf
import threading
import time
from collections import OrderedDict

from ..coreml.lifecycle import LifecycleMetrics
from .reranker import RerankerFacade


def _hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def default_runtime_fingerprint() -> dict:
    try:
        import coremltools as ct  # type: ignore
        ct_ver = getattr(ct, "__version__", "unknown")
    except Exception:
        ct_ver = "not_installed"
    return {
        "platform": _pf.platform(),
        "macos_version": _pf.mac_ver()[0],
        "machine": _pf.machine(),
        "coremltools_version": ct_ver,
    }


class RerankerCache:
    """Per-pipeline facade cache with keyed invalidation + telemetry."""

    def __init__(self, *, profile_provider, artifact_provider, config_provider,
                 metrics: LifecycleMetrics | None = None,
                 max_entries: int = 2,
                 facade_factory=None,
                 runtime_fingerprint: dict | None = None):
        self._profile_provider = profile_provider
        self._artifact_provider = artifact_provider
        self._config_provider = config_provider
        self._metrics = metrics or LifecycleMetrics()
        self._max_entries = max(1, int(max_entries))
        self._facade_factory = facade_factory or RerankerFacade
        self._runtime_fingerprint = runtime_fingerprint or default_runtime_fingerprint()
        self._entries: OrderedDict[str, dict] = OrderedDict()
        self._building: dict[str, threading.Event] = {}
        self._lock = threading.Lock()   # guards dicts only, never inference
        self._closed = False

    # ---- keys -----------------------------------------------------------
    def validity_key(self) -> str:
        """Key over everything EXCEPT the artifact (checked via stat)."""
        profile = self._profile_provider()
        cfg = self._config_provider()
        path = cfg.get("coreml", {}).get("calibration_report")
        cal = None
        if path:
            try:
                with open(os.path.expanduser(path), "rb") as f:
                    cal = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                cal = f"unreadable:{path}"
        return _hash({
            "calibration": cal,
            "profile": {
                "profile_version": profile.get("profile_version"),
                "calibration_fingerprint": profile.get("calibration_fingerprint"),
                "behavioral_profile": profile.get("behavioral_profile"),
                "reranker": (profile.get("features") or {}).get("reranker"),
            },
            "runtime": self._runtime_fingerprint,
            "config": {k: cfg.get(k) for k in
                       ("retrieval", "coreml", "limits", "runtime")},
        })

    @staticmethod
    def _artifact_stat(artifact) -> dict | None:
        """Cheap fingerprint of the artifact: per-file size+mtime inside the
        model package (in-place edits don't touch the directory mtime) plus
        metadata.json. The package holds a handful of files, so this stays a
        few dozen ``stat`` calls at most."""
        if artifact is None or not getattr(artifact, "model_path", None):
            return None
        out: dict = {"files": {}}
        root = artifact.model_path
        if os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                for name in sorted(filenames):
                    rel = os.path.relpath(os.path.join(dirpath, name), root)
                    try:
                        st = os.stat(os.path.join(dirpath, name))
                        out["files"][rel] = [st.st_size, st.st_mtime_ns]
                    except OSError:
                        out["files"][rel] = None
        else:
            try:
                st = os.stat(root)
                out["files"]["<model>"] = [st.st_size, st.st_mtime_ns]
            except OSError:
                out["files"]["<model>"] = None
        meta = os.path.join(os.path.dirname(root), "metadata.json")
        try:
            st = os.stat(meta)
            out["metadata"] = [st.st_size, st.st_mtime_ns]
        except OSError:
            out["metadata"] = None
        return out

    # ---- construction ---------------------------------------------------
    def _build_entry(self, validity: str) -> dict:
        self._metrics.incr("artifact_resolution_count")
        t0 = time.perf_counter()
        artifact = self._artifact_provider()
        facade = self._facade_factory(self._profile_provider(), artifact,
                                      metrics=self._metrics)
        decision = facade.decision()
        ms = (time.perf_counter() - t0) * 1000.0
        self._metrics.record_construction_ms(
            ms, first_load=bool(decision.ml_used and not decision.fallback))
        if decision.fallback:
            # Not cached: next get() retries (recovery) and this call already
            # falls back deterministically.
            self._metrics.record_fallback(decision.reason)
            return {"entry": None, "facade": facade, "decision": decision}
        entry = {"validity": validity, "stat": self._artifact_stat(artifact),
                 "facade": facade, "decision": decision, "hits": 0}
        with self._lock:
            self._entries[validity] = entry
            while len(self._entries) > self._max_entries:
                old_key, old = self._entries.popitem(last=False)
                if old_key != validity:
                    self._metrics.incr("cache_eviction_count")
                    old["facade"].close()
        return {"entry": entry, "facade": facade, "decision": decision}

    def _fresh(self, entry: dict) -> bool:
        """Artifact still present and unchanged since this entry was built."""
        if entry.get("stat") is None:
            return False
        art = entry["facade"].model_artifact
        if art is None:
            return False
        return self._artifact_stat(art) == entry.get("stat")

    def _take_fresh(self, validity: str) -> dict | None:
        """Return a fresh hit entry, dropping + closing a stale one."""
        stale = None
        with self._lock:
            entry = self._entries.get(validity)
            if entry is None:
                return None
            if self._fresh(entry):
                self._entries.move_to_end(validity)
                entry["hits"] += 1
            else:
                stale = self._entries.pop(validity)
                entry = None
        if stale is not None:
            stale["facade"].close()
            self._metrics.incr("cache_invalidation_count")
            return None
        self._metrics.incr("cache_hit_count")
        return entry

    def _fallback(self, reason: str) -> tuple:
        det = RerankerFacade(self._profile_provider(), None,
                             metrics=self._metrics)
        decision = det.decision()
        self._metrics.record_fallback(reason)
        return det, decision

    def _drop_obsolete(self, validity: str) -> None:
        """Close entries superseded by a changed validity key (calibration
        report, profile schema, runtime fingerprint or config change)."""
        with self._lock:
            keys = [k for k in list(self._entries) if k != validity]
            removed = [self._entries.pop(k) for k in keys]
        for e in removed:
            e["facade"].close()
        if removed:
            self._metrics.incr("cache_invalidation_count", len(removed))

    def get(self) -> tuple:
        """Return ``(facade, decision)`` — single-flight, cached, or fallback."""
        if self._closed:
            det = RerankerFacade(self._profile_provider(), None,
                                 metrics=self._metrics)
            return det, det.decision()
        validity = self.validity_key()
        self._drop_obsolete(validity)
        entry = self._take_fresh(validity)
        if entry is not None:
            return entry["facade"], entry["decision"]
        while True:
            with self._lock:
                event = self._building.get(validity)
                if event is None:
                    event = threading.Event()
                    self._building[validity] = event
                    leader = True
                else:
                    leader = False
            if not leader:
                # A concurrent builder owns this key; never duplicate the load.
                self._metrics.incr("concurrent_construction_prevented_count")
                event.wait(timeout=120)
                entry = self._take_fresh(validity)
                if entry is not None:
                    return entry["facade"], entry["decision"]
                # leader failed -> fall back deterministically this call;
                # the next call becomes leader and retries (recovery path).
                return self._fallback("construction_failed_elsewhere")
            self._metrics.incr("cache_miss_count")
            try:
                entry = self._take_fresh(validity)  # double-check
                if entry is not None:
                    return entry["facade"], entry["decision"]
                built = self._build_entry(validity)
                return built["facade"], built["decision"]
            except Exception as exc:  # noqa: BLE001 — cache must never raise
                return self._fallback(f"cache_build_error:{type(exc).__name__}")
            finally:
                with self._lock:
                    self._building.pop(validity, None)
                event.set()

    # ---- lifecycle ------------------------------------------------------
    def invalidate(self, reason: str = "manual") -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for e in entries:
            e["facade"].close()
        if entries:
            self._metrics.incr("cache_invalidation_count", len(entries))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for e in entries:
            e["facade"].close()
        self._metrics.incr("shutdown_count")

    @property
    def metrics(self) -> LifecycleMetrics:
        return self._metrics

    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)
