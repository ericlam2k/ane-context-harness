"""Content-type router: explicit policy mapping content to strategy.

The routing table (the documented policy — no hidden behavior):

    protected or explicitly pinned ............ VERBATIM (byte-exact)
    code / config / diff ...................... STRUCTURAL (already how the
                                                indexer chunks + packs: symbol
                                                units, score-first, mandatory
                                                retention)
    logs / verbose tool output ................ COMPACT (the deterministic
                                                tool-output compactor)
    prose / conversation / unknown ............ EXTRACTIVE (ranked selection
                                                as-is; neural compression is
                                                explicitly NOT offered — gated
                                                by the neural-compressor
                                                admission policy)

``route_evidence`` annotates items with their content type + strategy for
manifests (observability, not behavior change). Nothing here compresses,
rewrites, or calls a model; compressed prose would need the gated neural
path, which does not exist.

Portable: stdlib only.
"""
from __future__ import annotations

from pathlib import Path

VERBATIM = "verbatim"
STRUCTURAL = "structural"
COMPACT = "compact"
EXTRACTIVE = "extractive"

CODE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".java", ".go",
    ".rs", ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift",
    ".kt", ".scala", ".sh", ".sql",
})
CONFIG_EXTS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
})
DIFF_EXTS = frozenset({".diff", ".patch"})
PROSE_EXTS = frozenset({".md", ".rst", ".txt"})

_LOG_MARKERS = (
    "traceback (most recent call last)",
    "test session starts",
    "passed, ",
    "failed, ",
    "error:",
)


def classify_content(path: str, content: str = "") -> str:
    """Content type from extension first, log sniffing second."""
    ext = Path(path or "").suffix.lower()
    name = Path(path or "").name
    if ext in DIFF_EXTS:
        return "diff"
    if ext in CONFIG_EXTS or name.startswith(".env"):
        return "config"
    if ext in CODE_EXTS:
        return "code"
    if ext in PROSE_EXTS:
        return "prose"
    lowered = (content or "").lower()
    if any(m in lowered for m in _LOG_MARKERS):
        return "log"
    return "unknown"


def strategy_for(content_type: str, protected: bool = False) -> str:
    """Strategy name for a content type (+ protected override)."""
    if protected:
        return VERBATIM
    return {
        "code": STRUCTURAL,
        "config": STRUCTURAL,
        "diff": STRUCTURAL,
        "log": COMPACT,
        "prose": EXTRACTIVE,
        "conversation": EXTRACTIVE,
        "unknown": EXTRACTIVE,
    }.get(content_type, EXTRACTIVE)


def route_evidence(evidence: list) -> dict:
    """Annotate each item with content_type + strategy; return counts.

    Mutates the item dicts in place (adds two keys) so manifests and
    diagnostics observe the routing decision. No content is changed.
    """
    counts: dict = {}
    for ev in evidence or []:
        reasons = ev.get("selection_reasons") or []
        protected = bool({"mandatory", "authority", "explicit_path"}
                         .intersection(reasons))
        ctype = classify_content(ev.get("path"), ev.get("content"))
        strategy = strategy_for(ctype, protected)
        ev["content_type"] = ctype
        ev["strategy"] = strategy
        counts[strategy] = counts.get(strategy, 0) + 1
    return counts


def compact_evidence(evidence: list, token_budget: int = 2000) -> dict:
    """Run the COMPACT handler: collapse log evidence through the
    deterministic tool-output compactor core.

    Only items annotated with strategy ``compact`` are touched — protected
    items route as ``verbatim`` and are never rewritten. Content is replaced
    only when the compacted form is strictly smaller (header overhead must
    not grow tiny items); the original is then represented by its SHA-256
    plus a removal summary, per the FR-7 evidence rule. Deterministic:
    same input bytes always yield same output bytes.

    Returns {"compacted", "tokens_before", "tokens_after", "skipped"}.
    """
    from .compression.tool_output import compact_generic_text
    from .tokens import estimate

    stats = {"compacted": 0, "tokens_before": 0,
             "tokens_after": 0, "skipped": 0}
    for ev in evidence or []:
        if ev.get("strategy") != COMPACT:
            continue
        content = ev.get("content") or ""
        before = estimate(content)
        stats["tokens_before"] += before
        res = compact_generic_text(content, ev.get("path") or "evidence",
                                   token_budget)
        if res["compressed_tokens"] < before:
            ev["content"] = res["compressed"]
            ev["compacted"] = True
            ev["content_sha256"] = res["content_sha256"]
            ev["compaction"] = {
                "original_tokens": before,
                "compressed_tokens": res["compressed_tokens"],
                "reduction_percent": res["reduction_percent"],
            }
            stats["compacted"] += 1
            stats["tokens_after"] += res["compressed_tokens"]
        else:
            stats["skipped"] += 1
            stats["tokens_after"] += before
    return stats
