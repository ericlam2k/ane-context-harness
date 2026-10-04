"""Phase 4 shared prompt layout (FR-8 support): stable section ordering and
canonical serialization.

The thesis fixes the prompt order (§5): 1) project instructions, 2) explicitly
requested files, 3) interfaces/types, 4) primary implementation chunks,
5) relevant tests, 6) recent errors/tool output, 7) supporting context.
Provider adapters format these sections; they never perform or alter
retrieval/ranking (FR-8).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..retrieval.selector import CATEGORY_ORDER

SECTION_ORDER = ("instructions", "explicit", "interface", "implementation",
                 "test", "tool_output", "supporting")

SECTION_TITLES = {
    "instructions": "Instructions",
    "explicit": "Explicitly requested files",
    "interface": "Interfaces and types",
    "implementation": "Primary implementation",
    "test": "Relevant tests",
    "tool_output": "Recent errors and tool output",
    "supporting": "Supporting context",
}

_EVIDENCE_ORDER = tuple(c for c in CATEGORY_ORDER)  # explicit..supporting


@dataclass(frozen=True)
class PromptSection:
    name: str
    text: str


def canonical_json(obj) -> str:
    """Deterministic JSON (sorted keys, no padding) for reproducible payloads."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _render_evidence(ev: dict) -> str:
    loc = f"{ev.get('path', '?')}:{ev.get('start_line', 0)}-{ev.get('end_line', 0)}"
    reasons = ev.get("selection_reasons") or []
    head = f"### {loc} [{ev.get('category', 'supporting')}]"
    meta = []
    if ev.get("symbol"):
        meta.append(f"symbol: `{ev['symbol']}`")
    meta.append(f"reasons: {', '.join(reasons) if reasons else 'n/a'}")
    meta.append(f"score: {ev.get('score', 0)}")
    content = (ev.get("content") or "").rstrip()
    return "\n".join([head, *meta, "", "```", content, "```"])


def _render_tool_output(entry) -> str:
    if not isinstance(entry, dict):
        raise ValueError("tool_outputs entries must be dicts from compress_tool_output")
    text = entry.get("compressed", entry.get("content", ""))
    kind = entry.get("kind", "terminal")
    command = entry.get("command", "")
    exit_code = entry.get("exit_code", 0)
    sha = entry.get("content_sha256", "")
    return f"### {kind}: {command} (exit {exit_code})\n{sha}\n{text}".rstrip()


def build_prompt_sections(package, *, instructions: str = "",
                          tool_outputs=()) -> list:
    """Assemble thesis-ordered sections from an EvidencePackage.

    Evidence keeps its stably-ordered relative order within each category;
    tool output (already compressed) is spliced between tests and supporting
    context, matching the thesis prompt order.
    """
    groups = {c: [] for c in _EVIDENCE_ORDER}
    for ev in package.evidence:
        reasons = ev.get("selection_reasons") or []
        if "explicit_path" in reasons:
            cat = "explicit"
        else:
            cat = ev.get("category", "supporting")
            if cat not in groups:
                cat = "supporting"
        groups[cat].append(_render_evidence(ev))

    header = [f"Repository: {package.repository_id}",
              f"Policy: {package.policy_version} | Index: {package.index_version} | Model: {package.model_version}",
              f"Request: {package.request_id}"]
    instr_text = "\n".join(header + (["", instructions.strip()] if instructions.strip() else []))

    sections = [PromptSection("instructions", instr_text)]
    for name in ("explicit", "interface", "implementation", "test"):
        if groups[name]:
            sections.append(PromptSection(name, "\n\n".join(groups[name])))
    if tool_outputs:
        sections.append(PromptSection(
            "tool_output", "\n\n".join(_render_tool_output(t) for t in tool_outputs)))
    if groups["supporting"]:
        sections.append(PromptSection("supporting", "\n\n".join(groups["supporting"])))

    names = [s.name for s in sections]
    order = [SECTION_ORDER.index(n) for n in names]
    if order != sorted(order):
        raise ValueError(f"section order violated: {names}")
    return sections


def system_text(sections) -> str:
    """Canonical system text: fixed headings, double-newline separated."""
    return "\n\n".join(f"## {SECTION_TITLES[s.name]}\n{s.text}".strip()
                       for s in sections if s.text.strip())
