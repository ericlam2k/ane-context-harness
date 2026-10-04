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
from .retrieval.reranker import RerankDecision
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
        self._profile_cache = None
        self._facade = None
        self.storage_base = os.path.expanduser(config.get("index", {}).get("storage_path", "~/.ane_context_harness"))
        os.makedirs(self.storage_base, exist_ok=True)
        self.storage = None

    def lifecycle_metrics(self) -> dict:
        """Portable line loads no models: static zero snapshot (shape kept)."""
        return {"artifact_resolution_count": 0, "model_load_count": 0,
                "prediction_count": 0, "fallback_count": 0}

    def close(self) -> None:
        """Clean shutdown: nothing to release on the portable line."""
        if self._facade is not None:
            self._facade.close()

    def _storage_for(self, repo_id, repo_root=None) -> Storage:
        repo_id_safe = repo_id.replace("/", "_").replace(":", "_")
        db_path = os.path.join(self.storage_base, f"{repo_id_safe}.db")
        st = Storage(db_path, repo_id)
        if self.storage is None:
            self.storage = st
        return st

    def _calibration_measurements(self) -> dict:
        """Portable line: no calibration reports; deterministic profile always."""
        return {}

    def _profile(self) -> dict:
        """Capability profile (cached). Drives backend selection; never claims ANE.

        Portable line: deterministic profile, no calibration inputs.
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

    def register_repository(self, repo_path: str, repo_id: str | None = None,
                            force_rebuild: bool = False) -> schemas.IndexResponse:
        t0 = time.perf_counter()
        root = os.path.abspath(repo_path)
        if repo_id is None:
            import hashlib
            repo_id = hashlib.sha256(root.encode()).hexdigest()[:12]
        storage = self._storage_for(repo_id)
        storage.set_index_version("2")
        storage.set_repo_root(root)
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
                res["symbols_extracted"] += self._store_scanned_file(storage, repo_id, fi)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        return schemas.IndexResponse(
            repository_id=repo_id,
            files_indexed=res["files_indexed"],
            chunks_indexed=_chunk_count(storage, repo_id),
            files_skipped=res["files_skipped"],
            duration_ms=round(duration_ms, 2),
            incremental=not force_rebuild,
            index_version="2",
        )

    def _store_scanned_file(self, storage, repo_id: str, fi) -> int:
        """Persist one scanned file: metadata, symbols, chunks. Returns
        the symbol count. Shared by index and silent pinned refresh."""
        storage.upsert_file(fi.rel_path, fi.language, fi.size_bytes, fi.content_hash, fi.mtime_ns)
        from .indexing.symbols import extract_symbols as _es
        spans = _es(fi.language, fi.content)
        for name, s, e in spans:
            storage.upsert_symbol(fi.rel_path, name, s, e)
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
        return len(spans)

    def _refresh_pinned(self, storage, repo_id: str, root: str,
                        explicit_paths: list, authority_paths: list) -> tuple[list, list]:
        """Silent refresh of pinned sources. Returns (changed, missing).

        Only pinned paths are touched — the agent's own edits elsewhere
        never trigger re-indexing or notices here.
        """
        from . import freshness as _fresh
        from .indexing.repository import detect_language
        stored = storage.stored_file_hashes()
        rels = _fresh.expand_pinned(root, explicit_paths, authority_paths,
                                    set(stored))
        if not rels:
            return [], []
        changed, missing = _fresh.find_stale(root, rels, stored)
        for rel in changed:
            abs_path = os.path.join(root, rel)
            try:
                st = os.stat(abs_path)
                if st.st_size > self.max_file_bytes:
                    continue
                with open(abs_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            import hashlib as _hl
            from .indexing.repository import FileInfo
            fi = FileInfo(
                rel_path=rel, abs_path=abs_path,
                language=detect_language(rel), size_bytes=st.st_size,
                content_hash=_hl.sha256(content.encode("utf-8")).hexdigest(),
                mtime_ns=st.st_mtime_ns, content=content,
            )
            self._store_scanned_file(storage, repo_id, fi)
        for rel in missing:
            if rel in stored:
                storage.drop_path(repo_id, rel)
        return changed, missing

    def select_context(self, request: schemas.SelectRequest) -> schemas.EvidencePackage:
        t_total = time.perf_counter()
        storage = self._storage_for(request.repository_id)
        stage_ms = {}
        # Silent pinned refresh: re-index changed pinned sources before
        # ranking, so notices below describe an already-fresh index.
        # Legacy DBs without a recorded root skip this silently.
        pinned_changed: list = []
        pinned_missing: list = []
        authority_paths = (self.config.get("authority", {}) or {}).get(
            "authoritative_paths", [])
        if request.explicit_paths or authority_paths:
            with Timer("refresh") as t_ref:
                root = storage.repo_root()
                if root and os.path.isdir(root):
                    pinned_changed, pinned_missing = self._refresh_pinned(
                        storage, request.repository_id, root,
                        request.explicit_paths, authority_paths)
            stage_ms["refresh_ms"] = round(t_ref.elapsed_ms, 2)

        with Timer("candidate_generation") as t_cand:
            chunks = storage.load_chunks()
        stage_ms["candidate_generation_ms"] = round(t_cand.elapsed_ms, 2)

        # deterministic candidate generation: BM25 + symbol + path scored
        with Timer("reranking") as t_rank:
            bm25 = BM25(chunks)
            lex = lexical_scores(bm25, request.task)
            scores = aggregate_scores(chunks, request.task, request.explicit_paths,
                                      self.retrieval, lex)
            # optional query expansion: normalize + identifier passes, fused by
            # max/sum over initial_scores only. Pinning, reasons, and budgets
            # always use the original task (recall floor untouched).
            fusion = (self.retrieval.get("query_expansion", "off") or "off")
            if fusion in ("max", "sum"):
                from .retrieval.queries import expand_queries, fuse_scores
                queries = expand_queries(request.task)
                per_query = [[s.initial_score for s in scores]]
                for q in queries[1:]:
                    lex_q = lexical_scores(bm25, q)
                    sq = aggregate_scores(chunks, q, request.explicit_paths,
                                          self.retrieval, lex_q)
                    per_query.append([s.initial_score for s in sq])
                fused = fuse_scores(per_query, fusion)
                for s, v in zip(scores, fused):
                    s.initial_score = v
            # Portable line: deterministic reranker only (no models loaded).
            decision = RerankDecision(
                backend="cpu_deterministic", ml_used=False, fallback=False,
                reason="deterministic_only_no_ml_qualified",
                model_version="none")
            ml_scores = None
            use_ml = False
            reranker_ms = 0.0
        stage_ms["reranking_ms"] = round(t_rank.elapsed_ms, 2)
        stage_ms["reranker_ms"] = reranker_ms

        with Timer("packing") as t_pack:
            max_budget = min(request.token_budget, self.limits.get("max_output_token_budget", 30000))
            profile_name = (request.options or {}).get("profile")
            profile = {}
            if profile_name:
                profiles = self.retrieval.get("budget_profiles", {}) or {}
                if profile_name not in profiles:
                    raise ValueError(
                        f"unknown budget profile {profile_name!r}; "
                        f"expected one of {sorted(profiles)}")
                profile = profiles[profile_name] or {}
            if request.options.get("full_context"):
                # Baseline mode for with/without comparison: everything, in
                # stable path order. No budget, no trimming, no ranking.
                selected = sorted(chunks, key=lambda c: (c.path, c.start_line))
                diag = {"mandatory_count": 0,
                        "selected_count": len(selected),
                        "used_tokens": sum(c.estimated_tokens for c in selected),
                        "budget": max_budget, "budget_exceeded": False,
                        "full_context": True, "per_file_tokens": {},
                        "authority_flags": [], "pinned_changed": pinned_changed,
                        "pinned_missing": pinned_missing}
            else:
                selected, diag = select_evidence(
                    chunks, scores, request.task, max_budget, request.explicit_paths,
                    use_ml=use_ml, ml_scores=ml_scores, weights=self.retrieval,
                    authority_paths=authority_paths,
                    category_order=profile.get("category_order"),
                    category_caps=profile.get("category_caps"),
                )
                diag["pinned_changed"] = pinned_changed
                diag["pinned_missing"] = pinned_missing
                if profile_name:
                    diag["profile"] = {"name": profile_name,
                                       "category_order": profile.get("category_order", {}),
                                       "category_caps": profile.get("category_caps", {})}
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

        from .routing import route_evidence
        routing_counts = route_evidence(pkg.evidence)
        diag["routing"] = {"strategies": routing_counts}

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
        from .integrity import verify_package
        diag["integrity"] = verify_package(pkg.evidence, [pkg.markdown])
        return pkg

    def health(self) -> schemas.HealthResponse:
        from .platform.discovery import discover
        disc = discover()
        prof = derive_profile(disc)
        return schemas.HealthResponse(
            status="ok",
            platform="apple-silicon" if disc["hardware"]["is_apple_silicon"] else "non-apple-silicon",
            compute_mode="deterministic_only",
            index_version="2",
            service_version=SERVICE_VERSION,
            behavioral_profile=prof.behavioral_profile,
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
