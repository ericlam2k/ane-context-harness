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
                                                as-is; no model-based
                                                compression)

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
