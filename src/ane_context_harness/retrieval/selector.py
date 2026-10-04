"""Token-budgeted evidence packing with mandatory inclusion, diversity, and
stable ordering. Deterministic CPU backend only in Phase 1.

Selection order (stable):
  1 explicitly_requested -> 2 interface/type -> 3 implementation -> 4 test
  -> 5 supporting.
Mandatory chunks are always retained and passed through (redaction is Phase 2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schemas import ChunkScore, EvidenceItem
from .. import tokens as tokens_mod
from ..authority import match_authority


CATEGORY_ORDER = {
    "explicit": 0,
    "interface": 1,
    "implementation": 2,
    "test": 3,
    "supporting": 4,
}

_PER_FILE_FRACTION = 0.25  # per-file maximum allocation of budget


def _terms(text: str) -> set:
    from ..indexing.chunking import lex_terms
    return set(lex_terms(text))


def _jaccard(a: tuple, b: tuple) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    if inter == 0:
        return 0.0
    return inter / len(sa | sb)


def categorize(chunk) -> str:
    path = chunk.path.lower()
    fname = path.split("/")[-1]
    is_test = fname.startswith("test_") or fname.endswith(".test.ts") or fname.endswith(".spec.ts") or path.startswith("tests/")
    if is_test:
        return "test"
    if chunk.symbol and (chunk.language == "python" and not fname.startswith("test_")):
        # functions/classes are implementation; pure type defs are interface
        return "implementation"
    return "supporting"


def _nearest_test_for_source(chunks: list, src_idx: int, task_terms: set) -> list:
    """Indices of test chunks whose path is the peer test of src chunk, if any."""
    src = chunks[src_idx]
    src_path = src.path
    base = src_path.rsplit("/", 1)[-1].replace(".py", "").replace(".ts", "").replace(".js", "").replace(".tsx", "").replace(".jsx", "")
    candidates = []
    for i, c in enumerate(chunks):
        if i == src_idx:
            continue
        fname = c.path.split("/")[-1].lower()
        if fname.startswith("test_") and base in c.path.lower():
            candidates.append(i)
    return candidates


def compute_final_scores(scores: list, weights: dict, use_ml: bool, ml_scores: list | None) -> None:
    """In-place: set final_score. Phase 1 (use_ml=False): final = initial_score.
    Phase 3 (use_ml=True): final = det_w*initial + ml_w*ml_score."""
    det_w = weights.get("deterministic_final_weight", 0.45)
    ml_w = weights.get("ml_final_weight", 0.55)
    for i, s in enumerate(scores):
        if use_ml and ml_scores and i < len(ml_scores) and ml_scores[i] is not None:
            s.ml_relevance_score = ml_scores[i]
            s.final_score = det_w * s.initial_score + ml_w * s.ml_relevance_score
        else:
            s.final_score = s.initial_score
    # normalize final scores to 0..1 for reporting
    mx = max((s.final_score for s in scores), default=0.0)
    if mx > 0:
        for s in scores:
            s.final_score = s.final_score / mx


def select_evidence(chunks: list, scores: list, task: str, token_budget: int,
                    explicit_paths: list, use_ml: bool = False,
                    ml_scores: list | None = None, weights: dict | None = None,
                    per_file_fraction: float = _PER_FILE_FRACTION,
                    authority_paths: list | None = None) -> tuple[list, dict]:
    """Return (selected_chunks_in_order, diagnostics)."""
    weights = weights or {}
    task_terms = _terms(task)
    # index scores by chunk_id
    score_by_id = {s.chunk_id: s for s in scores}
    # ensure every chunk has a score
    for i, c in enumerate(chunks):
        if c.chunk_id not in score_by_id:
            scores.append(ChunkScore(chunk_id=c.chunk_id))
            score_by_id[c.chunk_id] = scores[-1]

    compute_final_scores(scores, weights, use_ml, ml_scores)

    # sort chunks by final score desc for candidate ordering
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i].final_score, i))

    # mandatory flags
    explicit_set = set(p.replace("\\", "/") for p in explicit_paths)
    mandatory_idx = set()
    authority_fired: set = set()
    for i, c in enumerate(chunks):
        norm = c.path.replace("\\", "/")
        if norm in explicit_set or norm.endswith(tuple(explicit_set)):
            mandatory_idx.add(i)
            score_by_id[c.chunk_id].mandatory = True
            score_by_id[c.chunk_id].selection_reasons.append("explicit_path")
        # developer-crowned authority: flagged sources pin like explicit
        # paths (no scoring change — retrieval finds, this file declares)
        for pat in match_authority(c.path, authority_paths):
            authority_fired.add(pat)
            mandatory_idx.add(i)
            score_by_id[c.chunk_id].mandatory = True
            if "authority" not in score_by_id[c.chunk_id].selection_reasons:
                score_by_id[c.chunk_id].selection_reasons.append("authority")
        # symbol directly named in task — own symbol for symbol-scoped chunks,
        # full file symbol list for file-level chunks (metadata.file_symbols);
        # micro/generic terms (to/is/for/test) never trigger retention
        from .structural import matched_symbol_terms
        if matched_symbol_terms(c, task_terms):
            mandatory_idx.add(i)
            score_by_id[c.chunk_id].mandatory = True
            if "named_symbol" not in score_by_id[c.chunk_id].selection_reasons:
                score_by_id[c.chunk_id].selection_reasons.append("named_symbol")

    # pair tests for mandatory sources
    src_mandatory = [i for i in mandatory_idx if categorize(chunks[i]) != "test"]
    for si in src_mandatory:
        for ti in _nearest_test_for_source(chunks, si, task_terms):
            mandatory_idx.add(ti)
            score_by_id[chunks[ti].chunk_id].mandatory = True
            if "test_pair" not in score_by_id[chunks[ti].chunk_id].selection_reasons:
                score_by_id[chunks[ti].chunk_id].selection_reasons.append("test_pair")

    selected = []  # list of (chunk_idx, category)
    used_tokens = 0
    per_file_tokens = {}

    # Score-first admission with mandatory retention. Candidates are visited
    # in final-score order, so high-ranked evidence (including required
    # documents) claims budget BEFORE lower-scored mandatory chunks; a
    # mandatory chunk is always retained (budget is a soft target) even when
    # it arrives late in score order. Non-mandatory chunks respect the token
    # budget, the per-file cap, and the MMR diversity window.
    lam = weights.get("diversity_lambda", 0.25)
    top_k = weights.get("top_k_for_diversity", 60)
    selected_terms = []
    non_mand_seen = 0
    for i in order:
        c = chunks[i]
        is_mandatory = i in mandatory_idx
        if not is_mandatory:
            non_mand_seen += 1
            if non_mand_seen > max(1, top_k):
                # beyond the diversity window — but keep scanning so a
                # lower-scored mandatory chunk is still admitted
                continue
        tokens = c.estimated_tokens
        pf = per_file_tokens.get(c.path, 0)
        if not is_mandatory:
            per_file_cap = max(tokens, int(per_file_fraction * token_budget))
            if pf + tokens > per_file_cap:
                continue
            if used_tokens + tokens > token_budget:
                continue  # does not fit; later chunks may be smaller
        reason = ("ml_reranker_high_score"
                  if score_by_id[c.chunk_id].ml_relevance_score is not None
                  else "lexical_rerank")
        if not is_mandatory:
            sims = [_jaccard(c.lexical_terms, st) for st in selected_terms]
            max_sim = max(sims) if sims else 0.0
            if scores[i].final_score - lam * max_sim < 0:
                continue
        if reason not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append(reason)
        if is_mandatory and "mandatory" not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append("mandatory")
        selected.append((i, categorize(c)))
        used_tokens += tokens
        per_file_tokens[c.path] = pf + tokens
        selected_terms.append(c.lexical_terms)

    # stable final order by category then score
    selected_sorted = sorted(selected, key=lambda x: (CATEGORY_ORDER.get(x[1], 9), -scores[x[0]].final_score, x[0]))
    final_chunks = [chunks[i] for i, _ in selected_sorted]
    diagnostics = {
        "mandatory_count": len(mandatory_idx),
        "selected_count": len(selected_sorted),
        "used_tokens": used_tokens,
        "budget": token_budget,
        "budget_exceeded": used_tokens > token_budget,
        "per_file_tokens": per_file_tokens,
        "authority_flags": sorted(authority_fired),
    }
    return final_chunks, diagnostics


def build_evidence(package_chunks: list, scores: list, task: str, request_id: str,
                   repo_id: str, policy_version: str, index_version: str,
                   model_version: str, metrics: dict, redaction_summary: dict,
                   stage_ms: dict) -> object:
    """Assemble the EvidencePackage dataclass with provenance-rich evidence."""
    from ..schemas import EvidencePackage
    score_by_id = {s.chunk_id: s for s in scores}
    evidence = []
    for c in package_chunks:
        sc = score_by_id.get(c.chunk_id)
        evidence.append({
            "path": c.path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "content_hash": c.content_hash,
            "symbol": c.symbol,
            "score": round(sc.final_score if sc else 0.0, 4),
            "selection_reasons": (sc.selection_reasons if sc else []),
            "category": categorize(c),
            "redacted": False,
            "content": c.content,
        })
    pkg = EvidencePackage(
        request_id=request_id,
        repository_id=repo_id,
        task=task,
        policy_version=policy_version,
        index_version=index_version,
        model_version=model_version,
        metrics={**metrics, "stage_ms": stage_ms},
        redaction_summary=redaction_summary,
        evidence=evidence,
        markdown="",
        execution={"reranker": "cpu_deterministic", "fallback_used": False},
    )
    return pkg
