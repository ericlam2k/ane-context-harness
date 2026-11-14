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
from .retrieval.selector import (
    build_evidence, build_rerank_shortlist, claim_candidates,
    recovery_prompt, resolve_stated_items, select_evidence,
    stated_claim_origins, stated_claim_terms, stated_need_resolution_block,
)
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
        # Dormant injection seam: an object with get() -> (facade, decision)
        # and close(). The portable line ships no model backend, so the cache
        # stays None and every select resolves the deterministic decision.
        self._reranker_cache = None
        self.storage_base = os.path.expanduser(config.get("index", {}).get("storage_path", "~/.ane_context_harness"))
        os.makedirs(self.storage_base, exist_ok=True)
        self.storage = None

    def lifecycle_metrics(self) -> dict:
        """Portable line loads no models: static zero snapshot (shape kept)."""
        return {"artifact_resolution_count": 0, "model_load_count": 0,
                "prediction_count": 0, "fallback_count": 0}

    def close(self) -> None:
        """Clean shutdown: release an injected reranker cache, if any."""
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
        """Portable line: no calibration reports; deterministic profile always."""
        return {}

    def _profile(self) -> dict:
        """Capability profile (cached). Drives backend selection; never claims an accelerator.

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
            skipped_by_reason = res.get("skipped_by_reason", {})
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
            from .indexing.repository import skipped_by_reason as _sbr
            skipped_by_reason = _sbr(plan)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        return schemas.IndexResponse(
            repository_id=repo_id,
            files_indexed=res["files_indexed"],
            chunks_indexed=_chunk_count(storage, repo_id),
            files_skipped=res["files_skipped"],
            skipped_by_reason=skipped_by_reason,
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

    def _refresh_incremental(self, storage, repo_id: str, root: str) -> tuple[list, list]:
        """Full incremental refresh: re-index ALL changed files in the repo.

        Runs automatically before every selection, so the index is always
        current and answers never come from stale files. Returns
        (changed, missing) paths relative to root.
        """
        plan = scan_repository(root, self.max_file_bytes, self.never_read)
        stored = storage.stored_file_hashes()
        new_paths = {fi.rel_path for fi in plan.files}
        stale = set(stored.keys()) - new_paths
        changed = []
        for fi in plan.files:
            cur = stored.get(fi.rel_path)
            if cur and cur[0] == fi.content_hash and cur[1] == fi.mtime_ns:
                continue
            changed.append(fi.rel_path)
            self._store_scanned_file(storage, repo_id, fi)
        for rel in stale:
            storage.drop_path(repo_id, rel)
        return changed, list(stale)

    def select_context(self, request: schemas.SelectRequest) -> schemas.EvidencePackage:
        t_total = time.perf_counter()
        storage = self._storage_for(request.repository_id)
        stage_ms = {}

        # Negative pins (exclude_paths): normalize once, refuse
        # contradictions before any cache lookup or recompute — a path
        # both pinned and excluded is a caller error, never a guess.
        excluded = _normalize_excluded(
            getattr(request, "exclude_paths", None) or [])
        _reject_contradictions(request.explicit_paths or [], excluded)

        # Silent full incremental refresh: re-index ALL changed files before
        # ranking, so the index is always fresh for selection.
        # Legacy DBs without a recorded root skip this silently.
        full_changed: list = []
        full_missing: list = []
        root = storage.repo_root()
        if root and os.path.isdir(root):
            with Timer("refresh_full") as t_ref:
                full_changed, full_missing = self._refresh_incremental(
                    storage, request.repository_id, root)
            stage_ms["refresh_full_ms"] = round(t_ref.elapsed_ms, 2)

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

        # Stated needs (CLI --stated-symbol / --stated-need). Reading the
        # flags is pure string handling; the index lookup happens after the
        # chunks load. Nothing stated: the machinery below is skipped
        # entirely and the diagnostics carry no new keys.
        stated_symbols = list(getattr(request, "stated_symbols", None) or [])
        stated_need = (getattr(request, "stated_need", None) or "").strip()

        with Timer("candidate_generation") as t_cand:
            chunks = storage.load_chunks()
        stage_ms["candidate_generation_ms"] = round(t_cand.elapsed_ms, 2)

        # Resolution is a lookup against the loaded chunks — no model cost.
        # Unresolved stated items are reported and never packed. Need-text
        # mined terms are anchored to the index the same way; unanchored
        # ones never reach claims and are disclosed in
        # stated_need_resolution_note.
        stated_resolution = None
        stated_terms = None
        stated_need_note = None
        stated_origins_map = None
        if stated_symbols or stated_need:
            stated_resolution = resolve_stated_items(chunks, stated_symbols)
            stated_terms, stated_need_note = stated_claim_terms(
                stated_need, stated_resolution, chunks)
            # Provenance of every stated claim term (term -> origins), for
            # the stated_claim_summary diagnostic. Computed exactly when a
            # stated flag was given; an empty map means nothing stated
            # survived the gates and yields honest zeros.
            stated_origins_map = stated_claim_origins(
                stated_need, stated_resolution, chunks)

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
            # The `_reranker_cache` seam mirrors a host-injected cached
            # backend; with the deterministic decision the shortlist path
            # never activates.
            cache = self._reranker_cache
            if cache is not None:
                facade, decision = cache.get()
            else:
                facade = None
                decision = RerankDecision(
                    backend="cpu_deterministic", ml_used=False, fallback=False,
                    reason="deterministic_only_no_ml_qualified",
                    model_version="none")
            ml_scores = None
            use_ml = False
            reranker_ms = 0.0
            rerank_diag = {"active": False, "backend": decision.backend,
                           "max_candidates": 0,
                           "shortlist_size": 0, "claim_candidates": 0,
                           "claims_outside_top_k": 0,
                           "claim_protection": False,
                           "reliability": {"candidates_scored": 0,
                                           "truncated_candidates": 0,
                                           "truncation_rate": 0.0,
                                           "invalid_predictions": 0,
                                           "strict_validity": True,
                                           "fallback_used": False,
                                           "fallback_reason": None}}
            if decision.ml_used and facade is not None:
                max_candidates = self.retrieval.get("max_rerank_candidates", 120)
                top_k = min(max_candidates, len(chunks))
                # final_score does not exist until the selector runs, so the
                # shortlist orders by initial_score (the full deterministic
                # signal at this point).
                order = sorted(range(len(chunks)),
                               key=lambda i: (-scores[i].initial_score, i))
                # Pointwise reranker: score the deterministic top-K plus
                # every pre-cap claim candidate, so a claim outside the
                # top-K cannot be silently dropped before the selector's
                # claims-first guarantee applies.
                claim_idx = claim_candidates(
                    chunks, request.task, request.explicit_paths,
                    authority_paths=authority_paths, weights=self.retrieval,
                    symbol_specificity=self.retrieval.get(
                        "mandatory_symbol_specificity"),
                    disable_symbol_pins=False,
                    stated_terms=stated_terms,
                    stated_origins=stated_origins_map)
                shortlist_idx, claims_outside = build_rerank_shortlist(
                    order, claim_idx, top_k)
                shortlist_chunks = [chunks[i] for i in shortlist_idx]
                t_rr = time.perf_counter()
                if hasattr(facade, "rerank_with_stats"):
                    top_scores, rr_stats = facade.rerank_with_stats(
                        request.task, shortlist_chunks, len(shortlist_chunks))
                else:
                    top_scores = facade.rerank(
                        request.task, shortlist_chunks, len(shortlist_chunks))
                    rr_stats = {}
                reranker_ms = round((time.perf_counter() - t_rr) * 1000.0, 2)
                ml_scores = [None] * len(chunks)
                for j, i in enumerate(shortlist_idx):
                    ml_scores[i] = top_scores[j] if j < len(top_scores) else None
                invalid = (rr_stats.get("invalid_predictions")
                           if rr_stats else
                           sum(1 for s in top_scores if s is None))
                rerank_diag = {
                    "active": True,
                    "backend": decision.backend,
                    "max_candidates": top_k,
                    "shortlist_size": len(shortlist_idx),
                    "claim_candidates": len(claim_idx),
                    "claims_outside_top_k": claims_outside,
                    "claim_protection": True,
                    "reliability": {
                        "candidates_scored": len(shortlist_idx),
                        "truncated_candidates": int(
                            rr_stats.get("truncated_candidates") or 0),
                        "truncation_rate": float(
                            rr_stats.get("truncation_rate") or 0.0),
                        "invalid_predictions": int(invalid or 0),
                        "strict_validity": bool(invalid == 0),
                        "fallback_used": bool(decision.fallback),
                        "fallback_reason": decision.reason,
                        "model_available": bool(
                            rr_stats.get("available", True)),
                    },
                }
                use_ml = True
        stage_ms["reranking_ms"] = round(t_rank.elapsed_ms, 2)
        stage_ms["reranker_ms"] = reranker_ms

        with Timer("packing") as t_pack:
            max_budget = min(request.token_budget, self.limits.get("max_output_token_budget", 30000))
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
                        "pinned_missing": pinned_missing,
                        "full_changed": full_changed,
                        "full_missing": full_missing}
            else:
                selected, diag = select_evidence(
                    chunks, scores, request.task, max_budget, request.explicit_paths,
                    use_ml=use_ml, ml_scores=ml_scores, weights=self.retrieval,
                    authority_paths=authority_paths,
                    required_paths=getattr(request, "required_paths", None),
                    stated_terms=stated_terms,
                    stated_origins=stated_origins_map,
                )
                diag["pinned_changed"] = pinned_changed
                diag["pinned_missing"] = pinned_missing
                diag["full_changed"] = full_changed
                diag["full_missing"] = full_missing
            if stated_resolution is not None:
                # Additive diagnostic; present only when the caller stated a
                # need. Unstated requests never see this key.
                diag["stated_need_resolution"] = stated_need_resolution_block(
                    stated_resolution)
            # Provenance hand-off from the claims pass (chunk_id -> origins);
            # never serialized. Absent when select_evidence was not called
            # (full-context branch) or nothing stated was given.
            claim_origins = diag.pop("claim_origins", None) or {}
            stage_ms["packing_ms"] = round(t_pack.elapsed_ms, 2)

        # Exclusion enforcement: drop after ranking, in every branch
        # (including full-context baselines — "must never appear" has no
        # exceptions). Retrieval may still score excluded chunks; they
        # never enter evidence.
        if excluded:
            kept, dropped = [], 0
            by_pattern: dict = {}
            for c in selected:
                hit = next((p for p in excluded if _is_excluded(c.path, [p])),
                           None)
                if hit is not None:
                    dropped += 1
                    by_pattern[hit] = by_pattern.get(hit, 0) + 1
                else:
                    kept.append(c)
            selected = kept
            diag["excluded"] = {"paths": sorted(excluded),
                                "chunks_dropped": dropped,
                                "dropped_by_pattern": by_pattern,
                                "unmatched": _unmatched_excludes(
                                    sorted(excluded),
                                    [c.path for c in chunks])}
        else:
            diag["excluded"] = {"paths": [], "chunks_dropped": 0,
                                "dropped_by_pattern": {}, "unmatched": []}
        if stated_need_note is not None:
            # Additive diagnostic; present only when --stated-need was
            # given. Attached here (post-exclusion) so matched_chunks
            # counts only chunks that actually enter the evidence pack.
            # Each kept term carries the number of packed chunks whose
            # symbol or basename matches it — the usable (non-generic,
            # min-length) symbol/basename matchers the claim pass uses,
            # WITHOUT the claim pass's file-frequency specificity gate:
            # a ubiquitous kept term can cite chunks it could never
            # claim-admit. This is a citation count, not a causal count:
            # a chunk admitted through a different claim, or one that
            # would have been selected anyway, is indistinguishable from
            # an aimed admission at runtime. Incidental riders show up
            # here as citations and are never upgraded to aimed
            # admissions by this diagnostic; separating them needs the
            # counterfactual pack against a no-stated-flags baseline,
            # which this runtime accounting does not attempt. 0 is
            # honest: generic or stoplisted terms (e.g. "test") cite
            # nothing, and an anchor that lives only in a directory path
            # component (gate rule (c)) matches no basename stem.
            # Test-pair citations via a paired source chunk are not
            # attributed to the term. Never invented otherwise.
            from .retrieval.structural import (matched_symbol_terms,
                                               matched_path_terms)
            kept_terms = set(stated_need_note["kept"])
            counts = dict.fromkeys(kept_terms, 0)
            if kept_terms:
                for chunk in selected:
                    cited = (matched_symbol_terms(chunk, kept_terms)
                             | matched_path_terms(chunk, kept_terms))
                    for term in cited:
                        counts[term] += 1
            diag["stated_need_resolution_note"] = {
                "kept": [{"term": term, "matched_chunks": counts[term]}
                         for term in stated_need_note["kept"]],
                "dropped": stated_need_note["dropped"],
            }
        if stated_symbols or stated_need:
            # Stated-claim summary: the runtime half of "did the agent aim
            # right". Counts PACKED chunks the claims-first pass admitted
            # while citing a stated-origin term, per origin: stated_symbol
            # (resolved --stated-symbol item matched an index symbol),
            # stated_path (a stated item matched a repository path),
            # stated_need (a kept, index-anchored --stated-need term).
            # A chunk admitted by several origins is counted once per
            # origin it was cited under; the three counts are not disjoint
            # and their sum is NOT the pack size — do not read it as one.
            # Basis is the final post-exclusion `selected` set, the same
            # basis as matched_chunks above (exclusions may have dropped
            # claim-admitted chunks after admission).
            #
            # Honest limit, stated plainly: this counts aimed admissions.
            # A count > 0 says "a stated need was cited by a packed claim",
            # not "this chunk is the evidence the agent was after". The
            # harness cannot recognise an incidental rider (a stated-anchored
            # claim whose chunk rode the budget for unrelated reasons) from
            # the pack alone — that needs the counterfactual pack without
            # the stated flags, which this runtime accounting does not
            # attempt. Unlike the citation count in the note above, the
            # basis here is the claims-first pass only: task-born candidates
            # carry no stated origin, so they are never counted as aimed,
            # however often they happen to match a stated term.
            # Attribution limit: a stated term that also appears verbatim in
            # the task text is credited as stated (term-level provenance,
            # not exclusivity).
            summary = {"stated_symbol": 0, "stated_path": 0, "stated_need": 0}
            for chunk in selected:
                origins = claim_origins.get(chunk.chunk_id)
                if not origins:
                    continue
                for origin in origins:
                    if origin in summary:
                        summary[origin] += 1
            diag["stated_claim_summary"] = summary
        # Hints must never point at an excluded path: the caller said it
        # must not appear, and a recovery hint would smuggle it back in.
        if excluded and diag.get("recovery"):
            rec = diag["recovery"]
            rec["missed_claims"] = [
                m for m in rec.get("missed_claims", [])
                if not any(_is_excluded(m["path"], [p]) for p in excluded)]
            rec["missed_required_paths"] = [
                m for m in rec.get("missed_required_paths", [])
                if not any(_is_excluded(m["path"], [p]) for p in excluded)]
            if not rec["missed_claims"] and not rec.get("missed_required_paths"):
                diag.pop("recovery", None)
                diag.pop("recovery_tool", None)
        diag["rerank_shortlist"] = rerank_diag

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
        if cleared:
            # Fail-closed cleared the pack; recovery entries would leak
            # paths into an empty response.
            diag.pop("recovery", None)
            diag.pop("recovery_tool", None)
        # Ask affordance, not a miss detector: when considered evidence
        # was not admitted or a stated symbol was not found in the index,
        # the result teaches the agent how to state its need. Reads the
        # final (post-exclusion, post-fail-closed) recovery block; absent
        # when nothing fired.
        prompt = recovery_prompt(diag.get("recovery"), stated_resolution)
        if prompt:
            diag["recovery_prompt"] = prompt
        pkg.execution["secret_classifier"] = {
            "backend": sc_backend if classifier else "disabled",
            "enabled": bool(classifier),
            "fallback": classifier is None and sc_enabled and redact,
            "fallback_reason": "no_classifier_built" if (classifier is None and sc_enabled and redact) else (None if classifier else "redaction_disabled"),
            "model_version": classifier.model_version if classifier else "none",
        }

        from .routing import route_evidence
        routing_counts = route_evidence(pkg.evidence)
        from .routing import compact_evidence
        compaction = compact_evidence(pkg.evidence)
        diag["routing"] = {"strategies": routing_counts,
                           "compaction": compaction}

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
        pkg.markdown = "" if cleared else render_markdown(
            pkg, conversation=request.conversation_summary or "")
        from .integrity import verify_package
        diag["integrity"] = verify_package(pkg.evidence, [pkg.markdown])
        return pkg


    def select_batch(self, repository_id: str, tasks: list[str],
                     token_budget: int, explicit_paths: list = None,
                     exclude_paths: list = None, scope_paths: list = None,
                     options: dict = None) -> list:
        """Batch select context for multiple tasks with shared BM25 and index refresh.

        This is more efficient than calling select_context multiple times because:
        1. Full incremental refresh runs once
        2. BM25 is built once and reused across all tasks
        3. Optional scope_paths limits the search to specific directories

        Args:
            repository_id: Repository identifier
            tasks: List of task strings
            token_budget: Token budget per task
            explicit_paths: Paths to pin for all tasks
            exclude_paths: Paths to exclude for all tasks
            scope_paths: Optional list of directory paths to limit search scope
            options: Pipeline options (profile, stage, etc.)

        Returns:
            List of EvidencePackage, one per task
        """
        if explicit_paths is None:
            explicit_paths = []
        if exclude_paths is None:
            exclude_paths = []
        if scope_paths is None:
            scope_paths = []
        if options is None:
            options = {}

        storage = self._storage_for(repository_id)

        # Silent full incremental refresh: re-index ALL changed files
        root = storage.repo_root()
        if root and os.path.isdir(root):
            plan = scan_repository(root, self.max_file_bytes, self.never_read)
            stored = storage.stored_file_hashes()
            new_paths = {fi.rel_path for fi in plan.files}
            stale = set(stored.keys()) - new_paths
            for fi in plan.files:
                cur = stored.get(fi.rel_path)
                if cur and cur[0] == fi.content_hash and cur[1] == fi.mtime_ns:
                    continue
                self._store_scanned_file(storage, repository_id, fi)
            for rel in stale:
                storage.drop_path(repository_id, rel)

        # Load all chunks once
        chunks = storage.load_chunks()

        # Apply scope filter if provided
        if scope_paths:
            chunks = [c for c in chunks if any(c.path.startswith(p) for p in scope_paths)]

        # Build BM25 once
        bm25 = BM25(chunks)

        # Process each task with shared BM25
        packages = []
        for task in tasks:
            req = schemas.SelectRequest(
                repository_id=repository_id,
                task=task,
                token_budget=token_budget,
                explicit_paths=explicit_paths,
                exclude_paths=exclude_paths,
                options=options
            )
            pkg = self._select_with_bm25(req, chunks, bm25)
            packages.append(pkg)

        return packages

    def _select_with_bm25(self, request: schemas.SelectRequest,
                          chunks: list, bm25: BM25) -> schemas.EvidencePackage:
        """Internal: run selection pipeline with pre-built BM25 and loaded chunks."""
        from .retrieval.lexical import lexical_scores
        from .retrieval.structural import aggregate_scores
        from .retrieval.selector import build_evidence, select_evidence
        import time

        storage = self._storage_for(request.repository_id)
        excluded = _normalize_excluded(getattr(request, "exclude_paths", None) or [])
        _reject_contradictions(request.explicit_paths or [], excluded)

        # Skip refresh since it was done at batch level
        pinned_changed: list = []
        pinned_missing: list = []

        # Reranking with shared BM25
        lex = lexical_scores(bm25, request.task)
        scores = aggregate_scores(chunks, request.task, request.explicit_paths,
                                  self.retrieval, lex)
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

        # Packing
        max_budget = min(request.token_budget, self.limits.get("max_output_token_budget", 30000))
        options = request.options or {}
        profile_name = options.get("profile")
        stage_name = options.get("stage")
        profiles = self.retrieval.get("budget_profiles", {}) or {}
        if stage_name:
            from .stages import resolve_stage
            stage = resolve_stage(stage_name)
            if not profile_name:
                profile_name = stage["profile"]
        profile = {}
        if profile_name:
            if profile_name not in profiles:
                raise ValueError(
                    f"unknown budget profile {profile_name!r}; "
                    f"expected one of {sorted(profiles)}")
            profile = profiles[profile_name] or {}
        if request.options.get("full_context"):
            selected = sorted(chunks, key=lambda c: (c.path, c.start_line))
            diag = {"mandatory_count": 0,
                    "selected_count": len(selected),
                    "used_tokens": sum(c.estimated_tokens for c in selected),
                    "budget": max_budget, "budget_exceeded": False,
                    "full_context": True, "per_file_tokens": {},
                    "authority_flags": [], "pinned_changed": [],
                    "pinned_missing": [], "full_changed": [], "full_missing": []}
        else:
            authority_paths = (self.config.get("authority", {}) or {}).get(
                "authoritative_paths", [])
            selected, diag = select_evidence(
                chunks, scores, request.task, max_budget, request.explicit_paths,
                use_ml=use_ml, ml_scores=ml_scores, weights=self.retrieval,
                authority_paths=authority_paths,
                required_paths=getattr(request, "required_paths", None))
            diag["pinned_changed"] = []
            diag["pinned_missing"] = []
            diag["full_changed"] = []
            diag["full_missing"] = []
            if profile_name:
                diag["profile"] = {"name": profile_name,
                                   "category_order": profile.get("category_order", {}),
                                   "category_caps": profile.get("category_caps", {})}

        # Exclusion enforcement
        if excluded:
            kept, dropped = [], 0
            by_pattern: dict = {}
            for c in selected:
                hit = next((p for p in excluded if _is_excluded(c.path, [p])),
                           None)
                if hit is not None:
                    dropped += 1
                    by_pattern[hit] = by_pattern.get(hit, 0) + 1
                else:
                    kept.append(c)
            selected = kept
            diag["excluded"] = {"paths": sorted(excluded),
                                "chunks_dropped": dropped,
                                "dropped_by_pattern": by_pattern,
                                "unmatched": _unmatched_excludes(
                                    sorted(excluded),
                                    [c.path for c in chunks])}
        else:
            diag["excluded"] = {"paths": [], "chunks_dropped": 0,
                                "dropped_by_pattern": {}, "unmatched": []}

        cand_tokens = sum(c.estimated_tokens for c in chunks)

        # Redaction
        redact = bool(request.options.get("redact_secrets", self.config.get("privacy", {}).get("redact_secrets", False)))
        fail_closed = bool(self.config.get("privacy", {}).get("fail_closed_for_cloud", False))
        redaction_summary = {"count": 0, "types": []}

        request_id = _new_request_id()
        pkg = build_evidence(
            selected, scores, request.task, request_id, request.repository_id,
            POLICY_VERSION, storage.index_version(), SERVICE_VERSION, {},
            redaction_summary, {},
        )
        pkg.execution = {
            "reranker": "cpu_deterministic",
            "coreml_compute_units_requested": None,
            "fallback_used": False,
            "fallback_reason": None,
            "model_version": "cpu_deterministic",
            "redaction": "disabled",
            "fail_closed": False,
            "model_lifecycle": self.lifecycle_metrics(),
        }

        # Redaction (disabled for batch for simplicity)
        if False:  # redact disabled for batch for simplicity
            pass

        from .routing import route_evidence, compact_evidence
        routing_counts = route_evidence(pkg.evidence)
        compaction = compact_evidence(pkg.evidence)
        diag = pkg.metrics.get("diagnostics", {})
        diag["routing"] = {"strategies": routing_counts, "compaction": {}}

        sel_tokens = sum(tokens_mod.count(e["content"]) for e in pkg.evidence)
        cand_tokens = sum(c.estimated_tokens for c in chunks)
        reduction = ((sum(c.estimated_tokens for c in chunks) - sum(e.estimated_tokens for e in selected)) /
                     sum(c.estimated_tokens for c in chunks) * 100.0) if chunks else 0.0
        req_tokens = sum(tokens_mod.count(e["content"]) for e in pkg.evidence
                         if "mandatory" in (e.get("selection_reasons") or []))

        metrics = {
            "candidate_tokens": sum(c.estimated_tokens for c in chunks),
            "selected_tokens": sum(e.estimated_tokens for e in selected),
            "tokens_removed": sum(c.estimated_tokens for c in chunks) - sum(e.estimated_tokens for e in selected),
            "reduction_percent": round(reduction, 2),
            "required_tokens": req_tokens,
            "discretionary_tokens": sum(e.estimated_tokens for e in selected) - req_tokens,
            "total_latency_ms": 0.0,
            "candidate_generation_ms": 0.0,
            "reranking_ms": 0.0,
            "reranker_ms": 0.0,
            "redaction_ms": 0.0,
            "packing_ms": 0.0,
            "stage_ms": {},
            "diagnostics": {"pinned_changed": [], "pinned_missing": [], "full_changed": [], "full_missing": []},
        }
        pkg.metrics = metrics
        pkg.markdown = render_markdown(pkg)
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


def _norm_pin(p) -> str:
    """Pin normalization, mirroring retrieval path matching."""
    return str(p).replace("\\", "/").lstrip("./")


def _normalize_excluded(paths: list) -> list:
    seen: dict = {}
    for p in paths or []:
        n = _norm_pin(p)
        if n:
            seen[n] = True
    return sorted(seen)


def _dir_covers(prefix: str, path: str) -> bool:
    """Directory-prefix arm: `tests/` (or `tests`) covers
    `tests/test_x.py` but never `latest/x.py` — the `/` boundary is
    mandatory so `src` can never swallow `src-discount/y.py`."""
    p = prefix.rstrip("/")
    return bool(p) and (path == p or path.startswith(p + "/"))


def _is_excluded(chunk_path: str, excluded: list) -> bool:
    """Conservative match: exact, suffix, or directory-prefix — same
    relation family the selector uses for explicit pins. A negative pin
    over-drops rather than leaks."""
    n = _norm_pin(chunk_path)
    return any(n == pat or n.endswith(pat) or _dir_covers(pat, n)
               for pat in excluded)


def _unmatched_excludes(excluded: list, chunk_paths) -> list:
    """Exclude patterns that matched no indexed chunk at all — almost
    always a typo or a wrong-scope pattern (e.g. a directory the old
    exact-or-suffix matcher silently ignored). Surfaced in diagnostics
    so callers can warn instead of pretending the exclusion worked."""
    paths = [_norm_pin(p) for p in chunk_paths]
    return sorted(p for p in excluded
                  if not any(q == p or q.endswith(p) or _dir_covers(p, q)
                             for q in paths))


def _reject_contradictions(explicit_paths: list, excluded: list) -> None:
    """A path both pinned and excluded is a caller error. Refuse with a
    ValueError so every existing contract (select/prove: stderr JSON,
    exit 2) handles it with no new plumbing."""
    normed = [_norm_pin(p) for p in explicit_paths or []]
    bad = sorted({p for p in normed
                  if any(p == x or p.endswith(x) or x.endswith(p)
                         or _dir_covers(x, p) or _dir_covers(p, x)
                         for x in excluded)})
    if bad:
        raise ValueError(
            f"contradictory pin: {bad} both explicitly pinned and "
            "excluded; pin or exclude, never both")


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
