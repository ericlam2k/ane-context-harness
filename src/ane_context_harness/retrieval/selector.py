"""Token-budgeted evidence packing with pin priority, diversity, and stable
ordering. Deterministic CPU backend only in Phase 1.

Selection order (stable):
  1 explicitly_requested -> 2 interface/type -> 3 implementation -> 4 test
  -> 5 supporting.

Budget contract: explicit paths and authority pins are the caller's own
request and are admitted even past the budget (the overrun is reported).
Inferred claims (named symbol, test pair) are preferred over discretionary
evidence but must fit the budget; claims that do not fit are dropped and
counted. A test path claims only on a task that asks about tests. After
claims, one best chunk per remaining path fills the budget (breadth), then
extra chunks of covered paths (depth), then a small tail for chunks that
were crowded out. The request is never exceeded by inferred evidence.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field

from ..schemas import ChunkScore, EvidenceItem
from .. import tokens as tokens_mod
from ..authority import match_authority
from .structural import (
    SPECIFICITY_MAX_FILE_FREQ_FRACTION, SPECIFICITY_MIN_FILE_FREQ_ABS,
    is_specific_symbol_term, matched_path_terms, matched_symbol_terms,
    path_term_file_frequency, symbol_term_file_frequency,
)


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
    if getattr(chunk, "symbol", None):
        # Any symbol-scoped chunk is implementation. (The old python-only
        # rule predates symbol extraction for other languages.)
        return "implementation"
    file_syms = list((getattr(chunk, "metadata", None) or {}).get("file_symbols") or [])
    if file_syms:
        # File-level chunk (the norm for small files, symbol None) from a
        # file that declares symbols: a file of function/type definitions
        # is implementation in any language. Without this, such files
        # fall into "supporting" and eat the supporting cap ahead of docs.
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


_TEST_INTENT = frozenset({
    "test", "tests", "testing", "spec", "specs", "verify", "verification",
    "regression", "green", "coverage", "unit", "integration",
})


def _ascii_words(text: str) -> set:
    folded = "".join(
        ch for ch in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(ch) != "Mn")
    return set(re.findall(r"[a-z0-9_]+", folded.lower()))


def _task_asks_about_tests(task: str, chunks: list) -> bool:
    """Whether the TASK asks about tests (language-neutral, task-driven).

    Two signals, both read from the task text only:

    - the conventional test vocabulary (``test``, ``spec``, ``coverage`` …),
      which is code-conventional and therefore usable across languages;
    - the task naming a test artifact explicitly (the file stem, e.g.
      ``test_discount_es``), which covers languages whose prose vocabulary
      we do not carry.

    Test intent is never inferred from which chunks matched. Inferring it
    from the matched set is circular: a coincidental path match on a test
    file then licenses every test chunk as a claim, and test evidence
    crowds out the implementation evidence the task asked for.
    """
    tokens = _ascii_words(task)
    if tokens & _TEST_INTENT:
        return True
    for c in chunks:
        if categorize(c) != "test":
            continue
        stem = (c.path or "").replace("\\", "/").rsplit("/", 1)[-1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        if stem and stem.lower() in tokens:
            return True
    return False


def identify_claim_candidates(chunks: list, task: str, explicit_paths: list,
                              authority_paths: list | None = None,
                              weights: dict | None = None,
                              symbol_specificity: dict | None = None,
                              disable_symbol_pins: bool = False
                              ) -> tuple[set, dict, set]:
    """Identify claim candidates BEFORE the per-file and budget caps.

    Returns ``(mandatory_idx, reasons_by_idx, authority_fired)``. The set is
    the union of explicit paths, authority matches, named symbol/path
    matches, and paired tests. ``select_evidence`` applies the per-file and
    budget caps after this pass; the reranker shortlist uses the same
    pre-cap set so a claim outside the deterministic top-K is still scored
    by the model.

    Keeping this pass in one place prevents the shortlist and the selector
    from drifting apart: both callers see identical claim rules.
    """
    weights = weights or {}
    task_terms = _terms(task)

    mandatory_idx = set()
    reasons_by_idx: dict = {}
    authority_fired = set()

    def _add(i: int, reason: str) -> None:
        mandatory_idx.add(i)
        reasons = reasons_by_idx.setdefault(i, [])
        if reason not in reasons:
            reasons.append(reason)

    def _note(i: int, reason: str) -> None:
        reasons = reasons_by_idx.setdefault(i, [])
        if reason not in reasons:
            reasons.append(reason)

    explicit_set = set(p.replace("\\", "/") for p in explicit_paths)
    spec_cfg = symbol_specificity
    if spec_cfg is None:
        spec_cfg = weights.get("mandatory_symbol_specificity")
    if spec_cfg is None:
        spec_cfg = {"enabled": True}
    spec_enabled = bool(spec_cfg.get("enabled", True))
    sym_freq, n_files = (symbol_term_file_frequency(chunks)
                         if spec_enabled else ({}, 0))
    path_freq, _ = (path_term_file_frequency(chunks)
                    if spec_enabled else ({}, 0))
    spec_min_abs = int(spec_cfg.get("max_file_frequency_abs",
                                    SPECIFICITY_MIN_FILE_FREQ_ABS))
    spec_fraction = float(spec_cfg.get("max_file_frequency_fraction",
                                       SPECIFICITY_MAX_FILE_FREQ_FRACTION))

    for i, c in enumerate(chunks):
        norm = c.path.replace("\\", "/")
        if norm in explicit_set or norm.endswith(tuple(explicit_set)):
            _add(i, "explicit_path")
        for pat in match_authority(c.path, authority_paths or []):
            authority_fired.add(pat)
            _add(i, "authority")
        if disable_symbol_pins:
            matched = set()
        else:
            matched = matched_symbol_terms(c, task_terms)
        if (not disable_symbol_pins) and matched:
            specific = (not spec_enabled) or any(
                is_specific_symbol_term(t, sym_freq, n_files,
                                        spec_min_abs, spec_fraction)
                for t in matched)
            if not specific:
                _note(i, "named_symbol_low_specificity")
            else:
                _add(i, "named_symbol")

        path_matched = matched_path_terms(c, task_terms)
        if path_matched:
            # Path terms are file names the task text names — user-named file
            # evidence. Path claims keep the same specificity gate as symbol
            # claims: a common word in a path name doesn't pin every file
            # sharing it.
            specific = (not spec_enabled) or any(
                is_specific_symbol_term(t, path_freq, n_files,
                                        spec_min_abs, spec_fraction)
                for t in path_matched)
            if specific:
                _add(i, "named_path")
            else:
                _note(i, "named_path_low_specificity")

    src_mandatory = [i for i in mandatory_idx if categorize(chunks[i]) != "test"]
    for si in src_mandatory:
        for ti in _nearest_test_for_source(chunks, si, task_terms):
            _add(ti, "test_pair")
    return mandatory_idx, reasons_by_idx, authority_fired


def claim_candidates(chunks: list, task: str, explicit_paths: list,
                     authority_paths: list | None = None,
                     weights: dict | None = None,
                     symbol_specificity: dict | None = None,
                     disable_symbol_pins: bool = False) -> set:
    """Pre-cap claim indices for a reranker shortlist (see above)."""
    mandatory_idx, _, _ = identify_claim_candidates(
        chunks, task, explicit_paths, authority_paths=authority_paths,
        weights=weights, symbol_specificity=symbol_specificity,
        disable_symbol_pins=disable_symbol_pins)
    return mandatory_idx


def build_rerank_shortlist(order: list, claim_idx: set, max_candidates: int
                           ) -> tuple[list, int]:
    """Union the deterministic top-K with every claim candidate.

    ``order`` is chunk indices in descending deterministic score. The result
    keeps that order (the pointwise reranker only uses set membership), and
    reports how many claims the top-K would have missed.
    """
    top_n = max(0, int(max_candidates))
    top = set(order[:top_n])
    shortlist = [i for i in order if i in top or i in claim_idx]
    claims_outside = sum(1 for i in claim_idx if i not in top)
    return shortlist, claims_outside


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


_RECOVERY_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{0,63}")
# Cap on listed missed items; the coverage counts always stay exact, only
# the itemized listing is bounded.
_RECOVERY_LIST_LIMIT = 5
_MISS_REASON_MARKERS = frozenset({
    "claim_dropped_budget",
    "mandatory_demoted_per_file_cap",
    "mandatory_demoted_budget_cap",
})


def _shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def _recovery_symbols(chunk) -> list:
    """Declared identifier names on this chunk, index order (spans, label, file)."""
    names = []

    def _add(name):
        if (isinstance(name, str) and _RECOVERY_IDENT.fullmatch(name)
                and name not in names):
            names.append(name)

    for name, _line in (chunk.metadata or {}).get("symbol_spans") or []:
        _add(name)
    _add(chunk.symbol)
    for name in (chunk.metadata or {}).get("file_symbols") or []:
        _add(name)
    return names


def _recovery_terms(chunk) -> list:
    """Identifier terms for a recovery command: declared symbols first, then
    the longest identifier-ish content terms stored in the chunk's index
    metadata. Empty when the chunk offers nothing usable."""
    symbols = _recovery_symbols(chunk)[:3]
    if symbols:
        return symbols
    terms = {t for t in (chunk.lexical_terms or ())
             if _RECOVERY_IDENT.fullmatch(t)
             and any(ch.isalpha() for ch in t) and len(t) >= 4}
    return sorted(terms, key=lambda t: (-len(t), t))[:3]


def _detect_search_tools() -> dict:
    """Resolve search tools on PATH at selection time. Presence via PATH is
    the contract — the harness never runs the binary to probe it. Values
    are the resolved paths, or None when absent."""
    return {"rg": shutil.which("rg"), "grep": shutil.which("grep")}


def _recovery_command(chunk, tools: dict) -> str:
    terms = _recovery_terms(chunk)
    if not terms:
        return ""
    pattern = "|".join(re.escape(s) for s in terms)
    if tools.get("rg"):
        return f"rg -n {_shell_quote(pattern)} -- {_shell_quote(chunk.path)}"
    if tools.get("grep"):
        # Same alternation and ERE escaping the rg form uses.
        return f"grep -nE {_shell_quote(pattern)} -- {_shell_quote(chunk.path)}"
    return ""


def select_evidence(chunks: list, scores: list, task: str, token_budget: int,
                    explicit_paths: list, use_ml: bool = False,
                    ml_scores: list | None = None, weights: dict | None = None,
                    per_file_fraction: float = _PER_FILE_FRACTION,
                    authority_paths: list | None = None,
                    required_paths: list[str] | None = None) -> tuple[list, dict]:
    """Return (selected_chunks_in_order, diagnostics).

    ``required_paths`` (optional) names the evidence the task requires; those
    paths' claims lead the admission order while both fit the budget, and are
    never admitted past it."""
    weights = weights or {}
    task_terms = _terms(task)
    # index scores by chunk_id
    score_by_id = {s.chunk_id: s for s in scores}
    # ensure every chunk has a score
    for i, c in enumerate(chunks):
        if c.chunk_id not in score_by_id:
            scores.append(ChunkScore(chunk_id=c.chunk_id))
            score_by_id[c.chunk_id] = scores[-1]

    # Drop duplicate index rows (same chunk_id): duplicates would be admitted
    # as separate claims and double-bill the token budget. Keep the first
    # occurrence.
    seen_ids: set = set()
    keep: list[int] = []
    for i, c in enumerate(chunks):
        if c.chunk_id in seen_ids:
            continue
        seen_ids.add(c.chunk_id)
        keep.append(i)
    chunks = [chunks[i] for i in keep]
    scores = [scores[i] for i in keep]

    compute_final_scores(scores, weights, use_ml, ml_scores)

    # sort chunks by final score desc for candidate ordering
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i].final_score, i))

    # Claim candidates before caps. The reranker shortlist (pipeline) calls
    # the same helper, so both callers see identical claim rules.
    mandatory_idx, claim_reasons, authority_fired = (
        identify_claim_candidates(
            chunks, task, explicit_paths, authority_paths=authority_paths,
            weights=weights,
            symbol_specificity=weights.get("mandatory_symbol_specificity")))
    # Named-claim candidates, snapshotted before any cap demotes a chunk;
    # used after packing to report how the task's named evidence fared.
    named_claim_idx = {
        i for i, reasons in claim_reasons.items()
        if any(r in ("named_symbol", "named_path", "test_pair")
               for r in reasons)
    }
    if not _task_asks_about_tests(task, chunks):
        named_claim_idx = {i for i in named_claim_idx
                           if categorize(chunks[i]) != "test"}
    for i, reasons in claim_reasons.items():
        sc = score_by_id[chunks[i].chunk_id]
        if i in mandatory_idx:
            sc.mandatory = True
        for reason in reasons:
            if reason not in sc.selection_reasons:
                sc.selection_reasons.append(reason)

    # Per-file mandatory cap: a single implementation file that declares
    # many task-matching symbols must not drag every one of its chunks
    # into the pack as mandatory. Keep only the top `mandatory_per_file_cap`
    # mandatory chunks per path (by final score); demote the rest.
    # Explicit/authority pins are exempt.
    mandatory_per_file_cap = weights.get("mandatory_per_file_cap", 2)
    if isinstance(mandatory_per_file_cap, int) and mandatory_per_file_cap > 0:
        by_path: dict = {}
        for i in mandatory_idx:
            sc = score_by_id[chunks[i].chunk_id]
            reasons = sc.selection_reasons or []
            if "explicit_path" in reasons or "authority" in reasons:
                continue
            by_path.setdefault(chunks[i].path, []).append(i)
        for path, idxs in by_path.items():
            if len(idxs) <= mandatory_per_file_cap:
                continue
            idxs.sort(key=lambda i: (-scores[i].final_score, i))
            for i in idxs[mandatory_per_file_cap:]:
                mandatory_idx.discard(i)
                sc = score_by_id[chunks[i].chunk_id]
                sc.mandatory = False
                if "mandatory" in (sc.selection_reasons or []):
                    sc.selection_reasons = [r for r in sc.selection_reasons
                                            if r != "mandatory"]
                if "mandatory_demoted_per_file_cap" not in sc.selection_reasons:
                    sc.selection_reasons.append("mandatory_demoted_per_file_cap")

    # Mandatory budget cap: symbol-pin expansion can mark many chunks
    # mandatory and blow past the budget. Keep the most score-relevant
    # score-relevant mandatory chunks inside `mandatory_budget_cap` of the
    # budget; demote the rest to ordinary (score/budget-gated) candidates so
    # they still compete, but no longer ride for free. Explicit/authority
    # pins are never demoted.
    mandatory_budget_cap = weights.get("mandatory_budget_cap", None)
    if isinstance(mandatory_budget_cap, (int, float)) and 0 < mandatory_budget_cap <= 1:
        pinned = [i for i in mandatory_idx if "explicit_path" in
                  (score_by_id[chunks[i].chunk_id].selection_reasons or [])
                  or "authority" in
                  (score_by_id[chunks[i].chunk_id].selection_reasons or [])]
        droppable = [i for i in mandatory_idx if i not in pinned]
        droppable.sort(key=lambda i: (-scores[i].final_score, i))
        kept_tokens = sum(chunks[i].estimated_tokens for i in pinned)
        kept = set(pinned)
        for i in droppable:
            if kept_tokens + chunks[i].estimated_tokens <= mandatory_budget_cap * token_budget:
                kept.add(i)
                kept_tokens += chunks[i].estimated_tokens
            else:
                mandatory_idx.discard(i)
                sc = score_by_id[chunks[i].chunk_id]
                sc.mandatory = False
                if "mandatory" in (sc.selection_reasons or []):
                    sc.selection_reasons = [r for r in sc.selection_reasons
                                            if r != "mandatory"]
                if "mandatory_demoted_budget_cap" not in sc.selection_reasons:
                    sc.selection_reasons.append("mandatory_demoted_budget_cap")

    # Budget-honest, coverage-first admission.
    # A. explicit_paths / authority pins are the caller's own request and
    #    are admitted unconditionally; if they alone exceed the budget the
    #    overrun is reported (budget_feasible=False), never hidden.
    # B. claims: the best chunk of each claimed path (a named symbol or a
    #    test pair) is admitted in score order while it fits. Claims are
    #    capped so a noisy task cannot flood the pack, and every dropped
    #    claim is counted. This is the required-evidence guarantee on tasks
    #    whose evidence is named.
    # C. breadth: the best chunk of each remaining distinct path, in score
    #    order, while the budget lasts. Breadth is the coverage objective, so
    #    it is not subject to the score cutoff or MMR; there is no point
    #    spending a second chunk on a file before another file gets its
    #    first.
    # D. depth: further chunks in score order under the per-file, cutoff and
    #    MMR rules.
    # E. tail: the reserved tail spends on small high-value chunks that were
    #    crowded out of the core budget; never overrun. Inferred evidence
    #    never pushes the pack past the requested budget; only the caller's
    #    own pins can.
    lam = weights.get("diversity_lambda", 0.25)
    top_k = weights.get("top_k_for_diversity", 60)
    score_cutoff = weights.get("score_cutoff", None)
    unconditional = set()
    for i in mandatory_idx:
        reasons = score_by_id[chunks[i].chunk_id].selection_reasons or []
        if "explicit_path" in reasons or "authority" in reasons:
            unconditional.add(i)
    selected = []
    selected_idx = set()
    selected_terms = []
    used_tokens = 0
    mandatory_tokens = 0
    unconditional_tokens = 0
    pin_candidates_selected = 0
    skipped_by_cutoff = 0
    breadth_paths = set()
    breadth_chunks = 0
    depth_chunks = 0
    claims_admitted = 0
    claims_dropped = 0
    claims_capped = 0
    claim_capped_idx: list = []
    tail_fill = 0
    tail_reserve = int(token_budget * weights.get("tail_reserve_fraction", 0.05))
    core_budget = max(0, token_budget - tail_reserve)
    per_file_tokens = {}
    per_category_tokens = {}

    def _admit(i: int, cat: str, is_pin: bool) -> None:
        nonlocal used_tokens, mandatory_tokens, pin_candidates_selected
        c = chunks[i]
        tokens = c.estimated_tokens
        if is_pin:
            reasons = score_by_id[c.chunk_id].selection_reasons
            if "mandatory" not in reasons:
                reasons.append("mandatory")
        selected.append((i, cat))
        selected_idx.add(i)
        used_tokens += tokens
        if is_pin:
            mandatory_tokens += tokens
        if i in mandatory_idx:
            pin_candidates_selected += 1
        per_file_tokens[c.path] = per_file_tokens.get(c.path, 0) + tokens
        per_category_tokens[cat] = per_category_tokens.get(cat, 0) + tokens
        selected_terms.append(c.lexical_terms)

    # A. unconditional pins (explicit / authority) — may overrun, by design.
    for i in order:
        if i not in unconditional:
            continue
        c = chunks[i]
        unconditional_tokens += c.estimated_tokens
        _admit(i, categorize(c), True)

    # B. claims — every named-symbol/test-pair chunk, score order,
    #    budget-bound.
    claim_cap = weights.get("claim_budget_fraction", 1.0)
    claim_chunk_cap = weights.get("max_claim_chunks", 24)
    # Test intent is TASK-driven, never derived from which chunks matched.
    test_intent = _task_asks_about_tests(task, chunks)
    strong_paths = set()
    for i in order:
        if i not in mandatory_idx or i in unconditional or i in selected_idx:
            continue
        reasons = score_by_id[chunks[i].chunk_id].selection_reasons or []
        if "named_symbol" in reasons or "test_pair" in reasons:
            strong_paths.add(chunks[i].path)
    claim_idx = []
    path_only_claimed = set()
    claim_paths = set()
    path_claimed_symbols: dict = {}
    for i in order:
        if i not in mandatory_idx or i in unconditional or i in selected_idx:
            continue
        c = chunks[i]
        reasons = score_by_id[c.chunk_id].selection_reasons or []
        if categorize(c) == "test" and not test_intent:
            continue
        if "named_symbol" in reasons or "test_pair" in reasons:
            if c.path in claim_paths:
                # One best claim chunk per path, unless the chunk brings new
                # evidence: a task can need two symbols from one file.
                syms = matched_symbol_terms(c, task_terms)
                named_path = "named_path" in reasons
                fresh_symbols = syms - path_claimed_symbols.get(c.path, set())
                if not (named_path or fresh_symbols):
                    continue
                path_claimed_symbols.setdefault(c.path, set()).update(syms)
                claim_idx.append(i)
                continue
            path_claimed_symbols.setdefault(c.path, set()).update(
                matched_symbol_terms(c, task_terms))
            claim_paths.add(c.path)
            claim_idx.append(i)
        elif c.path not in strong_paths and c.path not in path_only_claimed:
            # A filename match claims its best chunk, not every chunk of the
            # file, and not a file that already has a symbol-scoped claim.
            path_only_claimed.add(c.path)
            claim_paths.add(c.path)
            claim_idx.append(i)

    # Claim admission order: task-relevance first. A claim's relevance is the
    # strength of the task terms it accounts for (a shared rare term accounts
    # for more of the task than a shared common one); when claims compete for
    # the last fitting slot, the claim whose evidence the task text actually
    # asks about wins. The overlap class survives only as a tie-break under
    # equal relevance, then score. What does not fit is dropped and counted
    # (claims_dropped_budget).
    from .lexical import BM25

    def _path_overlaps(i: int) -> bool:
        return bool(set(_terms(chunks[i].path)) & task_terms)

    def _overlap_class(i: int) -> int:
        reasons = score_by_id[chunks[i].chunk_id].selection_reasons or []
        has_symbol = "named_symbol" in reasons or "test_pair" in reasons
        overlap = _path_overlaps(i)
        if has_symbol and overlap:
            return 0
        if ("test_pair" in reasons) or ("named_path" in reasons and overlap):
            return 1
        if has_symbol:
            return 2
        return 3

    if claim_idx:
        bm = BM25(chunks)

        def _relevance(i: int) -> float:
            matched = (matched_symbol_terms(chunks[i], task_terms)
                       | matched_path_terms(chunks[i], task_terms))
            return sum(bm.idf(t) for t in matched)

        relevance = {i: _relevance(i) for i in claim_idx}
        claim_idx = sorted(
            claim_idx,
            key=lambda i: (-relevance[i], _overlap_class(i),
                           -scores[i].final_score, i))

    # Twin-collision: two candidates can claim the same matched symbol (an
    # import site and a re-export of the same name). Demote any remaining
    # twin whose sibling shares its symbol and names the path, so the twin
    # claims only if budget allows.
    claim_sym_terms: dict[int, set] = {}
    for i in claim_idx:
        reasons = score_by_id[chunks[i].chunk_id].selection_reasons or []
        if "named_symbol" in reasons or "test_pair" in reasons:
            claim_sym_terms[i] = matched_symbol_terms(chunks[i], task_terms)
    claim_path_terms: dict[int, set] = {}
    for i in claim_idx:
        claim_path_terms[i] = _terms(chunks[i].path)

    def _twin_demoted(i: int) -> bool:
        s = claim_sym_terms.get(i)
        if not s:
            return False
        p_i = claim_path_terms.get(i) or set()
        for j, sj in claim_sym_terms.items():
            if j == i:
                continue
            if sj & s and (claim_path_terms.get(j) or set()) & task_terms \
                    and not (p_i & task_terms):
                return True
        return False

    keep_order = [i for i in claim_idx if not _twin_demoted(i)]
    demoted = [i for i in claim_idx if _twin_demoted(i)]
    claim_idx = keep_order + [i for i in demoted
                              if i not in keep_order]

    # Required-evidence claims first: paths named as required evidence by the
    # task are admitted before discretionary claims while both fit the
    # budget. Callers that know the labels (benchmarks) pass required_paths;
    # everyone else gets the default order.
    if required_paths:
        required_set = set(required_paths)
        required_claims = [i for i in claim_idx
                           if chunks[i].path in required_set]
        claim_idx = required_claims + [
            i for i in claim_idx if i not in required_claims]

    for n_claim, i in enumerate(claim_idx):
        c = chunks[i]
        path = c.path
        if n_claim >= max(1, claim_chunk_cap):
            claims_capped += len(claim_idx) - n_claim
            claim_capped_idx.extend(claim_idx[n_claim:])
            break
        if (used_tokens + c.estimated_tokens > token_budget
                or used_tokens + c.estimated_tokens > claim_cap * token_budget):
            claims_dropped += 1
            sc = score_by_id[c.chunk_id]
            sc.mandatory = False
            if "claim_dropped_budget" not in sc.selection_reasons:
                sc.selection_reasons.append("claim_dropped_budget")
            continue
        reason = ("ml_reranker_high_score"
                  if score_by_id[c.chunk_id].ml_relevance_score is not None
                  else "lexical_rerank")
        if reason not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append(reason)
        if "claim" not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append("claim")
        _admit(i, categorize(c), True)
        breadth_paths.add(path)
        claims_admitted += 1

    # C. breadth — one chunk per remaining distinct path, score order. When
    # the task does not ask about tests, test paths come after code and
    # docs, so a test file cannot spend a non-test task's budget first.
    breadth_order = order
    if not test_intent:
        breadth_order = ([i for i in order if categorize(chunks[i]) != "test"]
                         + [i for i in order if categorize(chunks[i]) == "test"])
    for i in breadth_order:
        if i in selected_idx:
            continue
        c = chunks[i]
        if c.path in breadth_paths:
            continue
        if len(breadth_paths) >= max(1, top_k):
            break
        if used_tokens + c.estimated_tokens > core_budget:
            continue
        cat = categorize(c)
        reason = ("ml_reranker_high_score"
                  if score_by_id[c.chunk_id].ml_relevance_score is not None
                  else "lexical_rerank")
        if reason not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append(reason)
        if "path_breadth" not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append("path_breadth")
        _admit(i, cat, False)
        breadth_paths.add(c.path)
        breadth_chunks += 1

    # D. depth — further chunks under the per-file, cutoff and MMR rules.
    non_mand_seen = 0
    for i in order:
        if i in selected_idx:
            continue
        c = chunks[i]
        non_mand_seen += 1
        if score_cutoff is not None and scores[i].final_score < score_cutoff:
            skipped_by_cutoff += 1
            continue
        if non_mand_seen > max(1, top_k):
            continue
        tokens = c.estimated_tokens
        pf = per_file_tokens.get(c.path, 0)
        per_file_cap = max(tokens, int(per_file_fraction * token_budget))
        if pf + tokens > per_file_cap:
            continue
        if used_tokens + tokens > core_budget:
            continue
        cat = categorize(c)
        sims = [_jaccard(c.lexical_terms, st) for st in selected_terms]
        max_sim = max(sims) if sims else 0.0
        if scores[i].final_score - lam * max_sim < 0:
            continue
        reason = ("ml_reranker_high_score"
                  if score_by_id[c.chunk_id].ml_relevance_score is not None
                  else "lexical_rerank")
        if reason not in score_by_id[c.chunk_id].selection_reasons:
            score_by_id[c.chunk_id].selection_reasons.append(reason)
        _admit(i, cat, False)
        depth_chunks += 1

    # E. tail fill — chunks crowded out of the core budget can still fit the
    # reserved tail. Spend it on the best remaining chunks that fit; never
    # overrun.
    if tail_reserve > 0:
        for i in order:
            if i in selected_idx:
                continue
            c = chunks[i]
            if c.path in breadth_paths:
                continue
            if used_tokens + c.estimated_tokens > token_budget:
                continue
            cat = categorize(c)
            reason = ("ml_reranker_high_score"
                      if score_by_id[c.chunk_id].ml_relevance_score is not None
                      else "lexical_rerank")
            if reason not in score_by_id[c.chunk_id].selection_reasons:
                score_by_id[c.chunk_id].selection_reasons.append(reason)
            if "tail_fill" not in score_by_id[c.chunk_id].selection_reasons:
                score_by_id[c.chunk_id].selection_reasons.append("tail_fill")
            _admit(i, cat, False)
            breadth_paths.add(c.path)
            tail_fill += 1

    # Required-evidence coverage: how the task's named claims and the
    # caller-labelled required paths fared against the pack. The block is
    # emitted only when at least one required item missed; a fully covered
    # run adds no diagnostics keys at all.
    covered_claims = [i for i in named_claim_idx if i in selected_idx]
    missed_claims = [i for i in named_claim_idx if i not in selected_idx]
    required_set = {p.replace("\\", "/") for p in (required_paths or []) if p}
    required_uncovered: list = []
    required_covered = 0
    if required_set:
        packed_paths = {chunks[i].path.replace("\\", "/")
                        for i in selected_idx}
        indexed_paths = {c.path.replace("\\", "/") for c in chunks}
        required_covered = len(required_set & packed_paths)
        for p in sorted(required_set - packed_paths):
            if p not in indexed_paths:
                why = "not_indexed"
            elif used_tokens >= token_budget:
                why = "budget"
            else:
                why = "dropped"
            required_uncovered.append({"path": p, "why": why})
    recovery_block = None
    recovery_tools = None
    if missed_claims or required_uncovered:
        recovery_tools = _detect_search_tools()
        claim_capped_set = set(claim_capped_idx)

        def _why(i):
            reasons = score_by_id[chunks[i].chunk_id].selection_reasons or []
            if ("mandatory_demoted_per_file_cap" in reasons
                    or "mandatory_demoted_budget_cap" in reasons
                    or i in claim_capped_set):
                return "capped"
            if "claim_dropped_budget" in reasons or used_tokens >= token_budget:
                return "budget"
            return "dropped"

        def _entry(i):
            sc = score_by_id[chunks[i].chunk_id]
            c = chunks[i]
            reasons = sorted({r for r in (sc.selection_reasons or [])
                              if r in _MISS_REASON_MARKERS})
            if i in claim_capped_set:
                reasons = sorted(set(reasons) | {"claim_capped"})
            return {"chunk_id": c.chunk_id,
                    "path": c.path,
                    "symbol": c.symbol or None,
                    "why": _why(i),
                    "reasons": reasons,
                    "command": _recovery_command(c, recovery_tools)}

        missed_sorted = sorted(
            missed_claims,
            key=lambda i: (-score_by_id[chunks[i].chunk_id].initial_score,
                           chunks[i].path, chunks[i].start_line, i))
        # One entry per (path, identifier set): repeated misses on the
        # same material carry the same instruction; totals are unaffected.
        listed = []
        seen = set()
        for i in missed_sorted:
            terms = frozenset(_recovery_terms(chunks[i]))
            if terms:
                key = (chunks[i].path, terms)
                if key in seen:
                    continue
                seen.add(key)
            if len(listed) >= _RECOVERY_LIST_LIMIT:
                break
            listed.append(_entry(i))
        recovery_block = {
            "required_claims_total": len(named_claim_idx),
            "required_claims_covered": len(covered_claims),
            "required_evidence_recall": (
                round(len(covered_claims) / len(named_claim_idx), 4)
                if named_claim_idx else 1.0),
            "missed_claims": listed,
        }
        if required_set:
            recovery_block["required_paths_total"] = len(required_set)
            recovery_block["required_paths_covered"] = required_covered
            recovery_block["required_paths_recall"] = round(
                required_covered / len(required_set), 4)
            recovery_block["missed_required_paths"] = \
                required_uncovered[:_RECOVERY_LIST_LIMIT]

    # stable final order by category then score
    selected_sorted = sorted(selected, key=lambda x: (CATEGORY_ORDER.get(x[1], 9), -scores[x[0]].final_score, x[0]))
    final_chunks = [chunks[i] for i, _ in selected_sorted]
    diagnostics = {
        "mandatory_count": len(mandatory_idx),
        "selected_count": len(selected_sorted),
        "used_tokens": used_tokens,
        "budget": token_budget,
        "budget_exceeded": used_tokens > token_budget,
        # Only the caller's own pins (explicit path / authority) can force a
        # pack past the request; inferred claims are dropped to fit and the
        # drops are counted, never hidden.
        "mandatory_tokens": mandatory_tokens,
        "unconditional_tokens": unconditional_tokens,
        "minimum_achievable_budget": unconditional_tokens,
        "budget_feasible": unconditional_tokens <= token_budget,
        "claims_admitted": claims_admitted,
        "claims_dropped_budget": claims_dropped,
        "claims_capped": claims_capped,
        "breadth_paths": len(breadth_paths),
        "breadth_chunks": breadth_chunks,
        "depth_chunks": depth_chunks,
        "tail_fill": tail_fill,
        "pin_candidates": len(mandatory_idx),
        "pin_candidates_selected": pin_candidates_selected,
        "overflow_tokens": max(0, used_tokens - token_budget),
        "per_file_tokens": per_file_tokens,
        "per_category_tokens": per_category_tokens,
        "authority_flags": sorted(authority_fired),
        "score_cutoff_skipped": skipped_by_cutoff,
    }
    if recovery_block is not None:
        # What the pack could not admit and why, so the next turn can
        # state the need instead of guessing. Additive; absent entirely
        # when every required item made it in.
        diagnostics["recovery"] = recovery_block
        diagnostics["recovery_tool"] = recovery_tools
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
