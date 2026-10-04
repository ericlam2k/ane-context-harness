"""Conversation-to-state compaction: deterministic, no model involved.

Long agent histories are truncated WITH structure instead of summarised by
an LLM (which would need a model, latency budget, and faithfulness proofs
none of which exist here):

- objective: first user turn, excerpted (the standing goal);
- recent: last ``keep_recent`` turns VERBATIM (immediate intent untouched);
- earlier: everything between, as indexed excerpts (role + first chars).

This is truncation-with-structure, documented as such — not semantic
summarization. Same turns always render byte-identically (provider prefix
caches keep hitting). Callers pass raw turns to ``serialize(...,
conversation_turns=[...])``; the section renders last, below all evidence.

Portable: stdlib only.
"""
from __future__ import annotations

DEFAULT_KEEP_RECENT = 2
DEFAULT_EXCERPT_CHARS = 300


def _excerpt(text: str, limit: int) -> str:
    text = text or ""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def compact_turns(turns, keep_recent: int = DEFAULT_KEEP_RECENT,
                  excerpt_chars: int = DEFAULT_EXCERPT_CHARS) -> dict:
    """Structure raw conversation turns deterministically."""
    if keep_recent < 0 or excerpt_chars < 0:
        raise ValueError("keep_recent and excerpt_chars must be >= 0")
    norm = []
    for t in turns or []:
        if isinstance(t, str):
            norm.append({"role": "user", "content": t})
        elif isinstance(t, dict) and isinstance(t.get("content"), str):
            norm.append({"role": str(t.get("role") or "user"),
                         "content": t["content"]})
        else:
            raise ValueError(
                "turns must be strings or {role, content} dicts, "
                f"got {type(t).__name__}")
    first_user = next((m["content"] for m in norm
                       if m["role"] == "user"), "")
    if keep_recent:
        recent, earlier = norm[-keep_recent:], norm[:-keep_recent]
    else:
        recent, earlier = [], list(norm)
    return {
        "objective": _excerpt(first_user, excerpt_chars),
        "recent": [{"role": m["role"], "content": m["content"]}
                   for m in recent],
        "earlier": [{"n": i + 1, "role": m["role"],
                     "excerpt": _excerpt(m["content"], excerpt_chars)}
                    for i, m in enumerate(earlier)],
        "turns": len(norm),
    }


def render_conversation_state(compacted: dict) -> str:
    """Render compacted turns as a stable prompt section body."""
    lines = [f"Objective: {compacted.get('objective') or '(none)'}"]
    recent = compacted.get("recent") or []
    if recent:
        lines.append("")
        lines.append("Recent turns (verbatim):")
        for m in recent:
            lines.append(f"[{m['role']}] {m['content']}".rstrip())
    earlier = compacted.get("earlier") or []
    if earlier:
        lines.append("")
        lines.append(f"Earlier ({len(earlier)} turns, excerpts):")
        for e in earlier:
            lines.append(f"#{e['n']} [{e['role']}] {e['excerpt']}".rstrip())
    return "\n".join(lines).strip()


def section_for(turns) -> str:
    """Prompt-section body for raw turns ("" when there are none)."""
    turns = list(turns or [])
    if not turns:
        return ""
    return render_conversation_state(compact_turns(turns))
