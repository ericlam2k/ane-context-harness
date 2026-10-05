"""Compact evidence formatter (AXI borrow #2, opt-in only).

TOON-subset rendering: scalars as ``k: v`` lines, uniform evidence rows as
one ``{path,start,end,symbol,reasons}`` header plus CSV rows, code content
verbatim under its row. No braces, no repeated key names, no quotes except
where a cell needs them.

Formatting only — no retrieval logic, no network (same contract as every
adapter; the providers AST test enforces it). This renderer is NOT adopted
as a default: the revalidation showed format savings are payload-shape-bound
(~58% on uniform schema rows, unverified on multiline code), so it ships
opt-in via ``serialize("compact", ...)`` and earns default status only if
the live bench proves billed-token savings when funds return.
"""
from __future__ import annotations


def _cell(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    text = str(value)
    if "," in text or '"' in text or "\n" in text:
        return '"' + text.replace('"', '""') + '"'
    return text


def _multiline_cell(value) -> list:
    """Code content rides as verbatim lines under its row (never CSV-folded:
    folding multiline code into one cell is where naive ports overstate
    savings — see the revalidation report's content_heavy caveat)."""
    return str(value).splitlines() or [""]


def render_compact(package, *, task=None) -> str:
    """Render an evidence package in compact TOON-subset form."""
    task_text = package.task if task is None else task
    metrics = package.metrics if isinstance(package.metrics, dict) else {}
    lines = [f"task: {_cell(task_text)}",
             f"repo: {_cell(package.repository_id)}",
             f"selected_tokens: {metrics.get('selected_tokens', 0)}",
             f"reduction_pct: {metrics.get('reduction_percent', 0)}"]
    rows = []
    for e in package.evidence or []:
        reasons = "|".join(e.get("selection_reasons") or [])
        rows.append((_cell(e.get("path")),
                     str(e.get("start_line")), str(e.get("end_line")),
                     _cell(e.get("symbol")), _cell(reasons),
                     e.get("content", "")))
    lines.append(f"evidence[{len(rows)}]{{path,start,end,symbol,reasons}}:")
    for path, start, end, symbol, reasons, content in rows:
        lines.append(f"  {path},{start},{end},{symbol},{reasons}:")
        for cl in _multiline_cell(content):
            lines.append(f"    {cl}")
    return "\n".join(lines).rstrip() + "\n"
