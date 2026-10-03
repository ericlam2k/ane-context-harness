"""Phase 1 deterministic pipeline: index -> BM25 -> structural scores ->
token-budgeted select -> EvidencePackage. No ML, no shell, no network.

The reranker backend is pluggable via the capability profile; Phase 1 always
uses the CPU deterministic backend.
"""
from __future__ import annotations

import os
import time

from . import tokens as tokens_mod
from . import schemas
from .indexing.chunking import lex_terms
from .indexing.repository import build_chunks, scan_repository
from .indexing.storage import Storage
from .platform.calibration import mock_calibration_deterministic_only
from .platform.discovery import discover
from .platform.profiles import CapabilityProfile, derive_profile
from .privacy.redaction import Redactor
from .privacy.classifier import SecretClassifier
from .providers.markdown import render_markdown
from .retrieval.lexical import BM25, lexical_scores
from .coreml.runtime import ModelArtifact
from .retrieval.reranker import RerankerFacade
from .retrieval.structural import aggregate_scores
from .retrieval.selector import build_evidence, select_evidence
from .telemetry.metrics import Timer

POLICY_VERSION = "phase0-2-deterministic+rules"
SERVICE_VERSION = "0.2.0-phase0-2"


class Pipeline:
    def __init__(self, config: dict):
        self.config = config
        idx = config.get("index", {})
        self.max_file_bytes = idx.get("max_file_bytes", 1000000)
        self.chunk_target = idx.get("chunk_target_tokens", 350)
        self.chunk_overlap = idx.get("chunk_overlap_tokens", 40)
        self.retrieval = config.get("retrieval", {})
        self.limits = config.get("limits", {})
        self.never_read = config.get("privacy", {}).get("never_read", [])
        self._model_path = (config.get("coreml", {}) or {}).get("model_path")
        self._coreml_cfg = config.get("coreml", {}) or {}
        self._calibration_report = (self._coreml_cfg or {}).get("calibration_report")
        self._profile_cache = None
        self._facade = None
        from .coreml.lifecycle import LifecycleMetrics
        self._lifecycle = LifecycleMetrics()
        self._reranker_cache = None
        self.storage_base = os.path.expanduser(config.get("index", {}).get("storage_path", "~/.ane_context_harness"))
        os.makedirs(self.storage_base, exist_ok=True)
        self.storage = None

    def lifecycle_metrics(self) -> dict:
        """Model-lifecycle telemetry snapshot (counts only — no source text)."""
        return self._lifecycle.snapshot()

    def close(self) -> None:
        """Clean shutdown: release the cached reranker model, if any."""
        if self._reranker_cache is not None:
            self._reranker_cache.close()

    def _storage_for(self, repo_id, repo_root=None) -> Storage:
        repo_id_safe = repo_id.replace("/", "_").replace(":", "_")
        db_path = os.path.join(self.storage_base, f"{repo_id_safe}.db")
        st = Storage(db_path, repo_id)
        if self.storage is None:
            self.storage = st
        return st

    def _calibration_measurements(self) -> dict:
        """Load Phase 3 calibration measurements, if a report path is configured.

        The report JSON maps feature names to measurement dicts, e.g.
        {"reranker": {"backend": "coreml_cpu_gpu", "enabled": true, ...}}.
        """
        if not self._calibration_report:
            return {}
        path = os.path.expanduser(self._calibration_report)
        if not os.path.exists(path):
            return {}
        import json as _json
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
            return data.get("measurements", data) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _profile(self) -> dict:
        """Capability profile (cached). Drives backend selection; never claims ANE.

        Optionally merged with on-disk Phase 3 calibration measurements when
        ``coreml.calibration_report`` is configured.
        """
        if self._profile_cache is None:
            disc = discover()
            measurements = self._calibration_measurements()
            self._profile_cache = derive_profile(disc, measurements=measurements).to_dict()
        return self._profile_cache

    def _classifier_artifact_path(self) -> str | None:
        p = (self.config.get("privacy", {}) or {}).get("classifier_model_path")
        if p:
            return os.path.expanduser(p)
        return os.path.join(self.storage_base, "secret_classifier.model")

    def _reranker_artifact(self) -> ModelArtifact | None:
        """Resolve a compiled Core ML reranker artifact, if configured/available.

        Looks up ``coreml.artifact_path`` or scans ``storage_base/artifacts``
        for a compiled ``.mlmodelc``/``.mlpackage`` directory carrying
        metadata + checksums. Returns None when absent (pipeline uses the
        deterministic reranker).
        """
        configured = self._coreml_cfg.get("artifact_path")
        if configured:
            candidate = os.path.expanduser(configured)
        else:
            art_dir = os.path.join(self.storage_base, "artifacts")
            candidate = None
            if os.path.isdir(art_dir):
                for name in sorted(os.listdir(art_dir), reverse=True):
                    d = os.path.join(art_dir, name)
                    if name.endswith((".mlmodelc", ".mlpackage")) and os.path.isdir(d):
                        candidate = d
                        break
        if not candidate or not os.path.isdir(candidate):
            return None
        meta_path = os.path.join(candidate, "metadata.json")
        vocab_path = os.path.join(candidate, "tokenizer", "vocab.txt")
        tok_cfg = os.path.join(candidate, "tokenizer", "tokenizer_config.json")
        model_path = self._find_model_file(candidate)
        if not model_path or not os.path.exists(vocab_path):
            return None
        import json as _json
        meta = {}
        if os.path.exists(meta_path):
            try:
                meta = _json.load(open(meta_path))
            except Exception:
                meta = {}
        checksums = {}
        ck = os.path.join(candidate, "checksums.sha256")
        if os.path.exists(ck):
            for line in open(ck):
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        checksums[parts[1]] = parts[0]
        return ModelArtifact(
            model_id=meta.get("model", ""), revision=meta.get("revision", ""),
            seq_len=int(meta.get("seq_len", 256)),
            model_version=meta.get("artifact_version", "none"),
            model_path=model_path, vocab_path=vocab_path,
            tokenizer_config_path=tok_cfg, checksums=checksums,
            numeric_validation=meta.get("numeric_validation", {}),
            manifest_entry=meta.get("entry_key", ""),
        )

    @staticmethod
    def _find_model_file(candidate: str) -> str | None:
        for name in ("model.mlmodelc", "model.mlpackage"):
            p = os.path.join(candidate, name)
            if os.path.isdir(p):
                return p
        for name in ("model.mlmodelc", "model.mlpackage"):
            p = os.path.join(candidate, name)
            if os.path.isdir(p):
                return p
        return None

    def register_repository(self, repo_path: str, repo_id: str | None = None,
                            force_rebuild: bool = False) -> schemas.IndexResponse:
        t0 = time.perf_counter()
        root = os.path.abspath(repo_path)
        if repo_id is None:
            import hashlib
            repo_id = hashlib.sha256(root.encode()).hexdigest()[:12]
        storage = self._storage_for(repo_id)
        storage.set_index_version("1")
        if force_rebuild:
            # wipe chunks/files for this repo
            storage._conn.execute("DELETE FROM chunks WHERE repo_id=?", (repo_id,))
            storage._conn.execute("DELETE FROM files WHERE repo_id=?", (repo_id,))
            storage._conn.execute("DELETE FROM symbols WHERE repo_id=?", (repo_id,))
            res = storage.incremental_rebuild(root, self.max_file_bytes, self.chunk_target, self.chunk_overlap, self.never_read)
        else:
            # incremental
            plan = scan_repository(root, self.max_file_bytes, self.never_read)
            stored = storage.stored_file_hashes()
            new_paths = {fi.rel_path for fi in plan.files}
            stale = set(stored.keys()) - new_paths
            with storage._lock:
                for sp in stale:
                    storage._conn.execute("DELETE FROM chunks WHERE repo_id=? AND rel_path=?", (repo_id, sp))
                    storage._conn.execute("DELETE FROM files WHERE repo_id=? AND rel_path=?", (repo_id, sp))
                    storage._conn.execute("DELETE FROM symbols WHERE repo_id=? AND rel_path=?", (repo_id, sp))
            # build chunks for changed files
            res = {"files_indexed": 0, "files_skipped": 0, "stale_removed": len(stale), "symbols_extracted": 0}
            for fi in plan.files:
                cur = stored.get(fi.rel_path)
                if cur and cur[0] == fi.content_hash and cur[1] == fi.mtime_ns:
                    res["files_skipped"] += 1
                    continue
                res["files_indexed"] += 1
                storage.upsert_file(fi.rel_path, fi.language, fi.size_bytes, fi.content_hash, fi.mtime_ns)
                spans = []
                from .indexing.symbols import extract_symbols as _es
                spans = _es(fi.language, fi.content)
                for name, s, e in spans:
                    storage.upsert_symbol(fi.rel_path, name, s, e)
                    res["symbols_extracted"] += 1
                from .indexing.chunking import chunk_file, lex_terms as _lt
                import hashlib as _hl
                pieces = chunk_file(fi.content, self.chunk_target, self.chunk_overlap)
                chunk_objs = []
                for pc in pieces:
                    chunk_objs.append({
                        "chunk_id": _hl.sha256(f"{repo_id}:{fi.rel_path}:{pc.start_line}".encode()).hexdigest()[:16],
                        "path": fi.rel_path,
                        "language": fi.language,
                        "start_line": pc.start_line,
                        "end_line": pc.end_line,
                        "symbol": _nearest_symbol(pc.start_line, spans),
                        "content_hash": fi.content_hash,
                        "estimated_tokens": pc.tokens,
                        "lexical_terms": tuple(_lt(pc.content)),
                        "content": pc.content,
                    })
                storage.replace_chunks(fi.rel_path, chunk_objs)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        return schemas.IndexResponse(
            repository_id=repo_id,
            files_indexed=res["files_indexed"],
            chunks_indexed=_chunk_count(storage, repo_id),
            files_skipped=res["files_skipped"],
            duration_ms=round(duration_ms, 2),
            incremental=not force_rebuild,
            index_version="1",
        )

    def select_context(self, request: schemas.SelectRequest) -> schemas.EvidencePackage:
        t_total = time.perf_counter()
        storage = self._storage_for(request.repository_id)
        stage_ms = {}

        with Timer("candidate_generation") as t_cand:
            chunks = storage.load_chunks()
        stage_ms["candidate_generation_ms"] = round(t_cand.elapsed_ms, 2)

        # deterministic candidate generation: BM25 + symbol + path scored
        with Timer("reranking") as t_rank:
            bm25 = BM25(chunks)
            lex = lexical_scores(bm25, request.task)
            scores = aggregate_scores(chunks, request.task, request.explicit_paths,
                                      self.retrieval, lex)
            # Phase 3 reranker (profile-driven). No bundled model => cpu_deterministic.
            # The keyed cache guarantees ONE runtime/model load per stable
            # (artifact, calibration, profile, runtime, config) state; every
            # request still runs predictions through the cached facade.
            if self._reranker_cache is None:
                from .retrieval.model_cache import RerankerCache
                self._reranker_cache = RerankerCache(
                    profile_provider=self._profile,
                    artifact_provider=self._reranker_artifact,
                    config_provider=lambda: self.config,
                    metrics=self._lifecycle,
                )
            facade, decision = self._reranker_cache.get()
            ml_scores = None
            use_ml = False
            reranker_ms = 0.0
            if decision.ml_used:
                top_k = min(self.retrieval.get("max_rerank_candidates", 120), len(chunks))
                order = sorted(range(len(chunks)), key=lambda i: -scores[i].final_score)
                top_idx = order[:top_k]
                top_chunks = [chunks[i] for i in top_idx]
                t_rr = time.perf_counter()
                top_scores = facade.rerank(request.task, top_chunks, top_k)
                reranker_ms = round((time.perf_counter() - t_rr) * 1000.0, 2)
                ml_scores = [None] * len(chunks)
                for j, i in enumerate(top_idx):
                    ml_scores[i] = top_scores[j] if j < len(top_scores) else None
                use_ml = True
        stage_ms["reranking_ms"] = round(t_rank.elapsed_ms, 2)
        stage_ms["reranker_ms"] = reranker_ms

        with Timer("packing") as t_pack:
            max_budget = min(request.token_budget, self.limits.get("max_output_token_budget", 30000))
            selected, diag = select_evidence(
                chunks, scores, request.task, max_budget, request.explicit_paths,
                use_ml=use_ml, ml_scores=ml_scores, weights=self.retrieval,
            )
        stage_ms["packing_ms"] = round(t_pack.elapsed_ms, 2)

        cand_tokens = sum(c.estimated_tokens for c in chunks)

        # Phase 2 redaction (rule-based, CPU). Opt-in per-request or via privacy config.
        redact = bool(request.options.get(
            "redact_secrets", self.config.get("privacy", {}).get("redact_secrets", False)))
        fail_closed = bool(self.config.get("privacy", {}).get("fail_closed_for_cloud", False))
        redaction_summary = {"count": 0, "types": []}

        request_id = _new_request_id()
        pkg = build_evidence(
            selected, scores, request.task, request_id, request.repository_id,
            POLICY_VERSION, storage.index_version(), SERVICE_VERSION, {},
            redaction_summary, stage_ms,
        )
        pkg.execution = {
            "reranker": decision.backend,
            "coreml_compute_units_requested": decision.backend if decision.backend.startswith("coreml_") else None,
            "fallback_used": decision.fallback,
            "fallback_reason": decision.reason,
            "model_version": decision.model_version,
            "redaction": "rule_based_cpu" if redact else "disabled",
            "fail_closed": fail_closed,
            "model_lifecycle": self.lifecycle_metrics(),
        }

        with Timer("redaction") as t_red:
            cleared = False
            classifier = None
            sc_state = self._profile().get("features", {}).get("secret_classifier", {})
            sc_backend = sc_state.get("backend", "cpu_deterministic")
            sc_enabled = sc_state.get("enabled", False)
            if redact and sc_enabled and sc_backend == "cpu_deterministic":
                classifier = SecretClassifier(model_path=self._classifier_artifact_path())
            if redact:
                rd = Redactor(redact_secrets=True, classifier=classifier)
                for ev in pkg.evidence:
                    ev["content"] = rd.redact(ev["content"])
                redaction_summary = rd.summary()
                pkg.redaction_summary = redaction_summary
            # fail-closed: in cloud-ready mode, never return unredacted evidence
            if fail_closed and redact and _any_secret_leak(pkg.evidence):
                pkg.evidence = []
                pkg.execution["redaction_failed"] = True
                cleared = True
            stage_ms["redaction_ms"] = round(t_red.elapsed_ms, 2)
        pkg.execution["secret_classifier"] = {
            "backend": sc_backend if classifier else "disabled",
            "enabled": bool(classifier),
            "fallback": classifier is None and sc_enabled and redact,
            "fallback_reason": "no_classifier_built" if (classifier is None and sc_enabled and redact) else (None if classifier else "redaction_disabled"),
            "model_version": classifier.model_version if classifier else "none",
        }

        sel_tokens = sum(tokens_mod.count(e["content"]) for e in pkg.evidence)
        reduction = ((cand_tokens - sel_tokens) / cand_tokens * 100.0) if cand_tokens else 0.0
        # Required-coverage floor: mandatory (required-evidence) chunks are
        # always retained; the token budget governs discretionary chunks only.
        # Users never manage this split — the footer reports it as consequence.
        req_tokens = sum(
            tokens_mod.count(e["content"]) for e in pkg.evidence
            if "mandatory" in (e.get("selection_reasons") or []))

        metrics = {
            "candidate_tokens": cand_tokens,
            "selected_tokens": sel_tokens,
            "tokens_removed": cand_tokens - sel_tokens,
            "reduction_percent": round(reduction, 2),
            "required_tokens": req_tokens,
            "discretionary_tokens": sel_tokens - req_tokens,
            "total_latency_ms": round((time.perf_counter() - t_total) * 1000.0, 2),
            "candidate_generation_ms": stage_ms["candidate_generation_ms"],
            "reranking_ms": stage_ms["reranking_ms"],
            "reranker_ms": stage_ms["reranker_ms"],
            "redaction_ms": stage_ms["redaction_ms"],
            "packing_ms": stage_ms["packing_ms"],
            "stage_ms": stage_ms,
            "diagnostics": diag,
        }
        pkg.metrics = metrics
        pkg.markdown = "" if cleared else render_markdown(pkg)
        return pkg

    def health(self) -> schemas.HealthResponse:
        from .platform.discovery import discover
        disc = discover()
        prof = derive_profile(disc)
        return schemas.HealthResponse(
            status="ok",
            platform="apple-silicon" if disc["hardware"]["is_apple_silicon"] else "non-apple-silicon",
            coreml_model_loaded=False,
            compute_mode="deterministic_only",
            index_version="1",
            service_version=SERVICE_VERSION,
            behavioral_profile=prof.behavioral_profile,
            coreml_compute_units_requested=None,
            fallback_used=False,
            secret_classifier=prof.features.get("secret_classifier", {}).get("backend", "cpu_deterministic"),
            capabilities=disc,
        )


def _chunk_count(storage, repo_id) -> int:
    with storage._lock:
        row = storage._conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE repo_id=?", (repo_id,)).fetchone()
    return row["n"]


def _nearest_symbol(start_line, symbols):
    best = None
    for name, s, e in symbols:
        if s <= start_line <= e:
            best = name
    return best


def _new_request_id() -> str:
    import secrets
    return "ctx_" + secrets.token_hex(8)


def _any_secret_leak(evidence: list) -> bool:
    """Sanity check: any unredacted secret remaining in evidence content."""
    from .privacy.secrets import scan
    for ev in evidence:
        if ev.get("content") and scan(ev["content"]):
            return True
    return False


def default_profile():
    from .platform.discovery import discover
    return derive_profile(discover())
