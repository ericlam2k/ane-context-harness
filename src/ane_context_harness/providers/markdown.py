"""Markdown + plain-text evidence formatter. Phase 4 adds a prompt-oriented
Markdown adapter over the shared thesis-ordered layout; retrieval/ranking
stays untouched (FR-8).
"""
from __future__ import annotations

from ..schemas import EvidencePackage
from ..summary import tokens_line
from ..conversation import section_for as _conversation_section
from .layout import SECTION_TITLES, build_prompt_sections


def render_prompt_markdown(package, *, instructions: str = "",
                           tool_outputs=(), task=None,
                           conversation_turns=()) -> str:
    """Plain Markdown for manual use (FR-8). Task first for human entry; the
    sections keep the stable thesis order."""
    sections = build_prompt_sections(
        package, instructions=instructions, tool_outputs=tool_outputs,
        conversation=_conversation_section(conversation_turns))
    task_text = package.task if task is None else task
    lines = [f"# {task_text}", ""]
    for s in sections:
        if not s.text.strip():
            continue
        lines.append(f"## {SECTION_TITLES[s.name]}")
        lines.append(s.text.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(package: EvidencePackage, *, conversation: str = "") -> str:
    lines = []
    lines.append(f"# Selected repository context")
    lines.append("")
    lines.append(f"**Task:** {package.task}")
    lines.append(f"**Repository:** {package.repository_id}")
    lines.append(f"**Policy:** {package.policy_version} | **Index:** {package.index_version} | **Model:** {package.model_version}")
    m = package.metrics
    if isinstance(m, dict):
        lines.append(tokens_line(m))
    lines.append("")
    lines.append("Evidence packages follow, ordered stably:")
    lines.append("")
    for ev in package.evidence:
        loc = f"{ev['path']}:{ev['start_line']}-{ev['end_line']}"
        lines.append(f"## Evidence: {loc}")
        if ev.get("symbol"):
            lines.append(f"Symbol: `{ev['symbol']}`")
        reasons = ev.get("selection_reasons", [])
        lines.append(f"Selection reasons: {', '.join(reasons) if reasons else 'n/a'}")
        lines.append(f"Score: {ev.get('score', 0)} | Hash: `{ev.get('content_hash','')[:12]}…`")
        lines.append("")
        lines.append("```")
        lines.append(ev.get("content", ""))
        lines.append("```")
        lines.append("")
    if conversation and conversation.strip():
        lines.append("## Conversation state")
        lines.append(conversation.strip())
        lines.append("")
    return "\n".join(lines)
