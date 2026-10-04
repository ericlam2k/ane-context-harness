"""Anthropic Messages adapter (FR-8). Formatting only — no retrieval logic.

Cache-aware prefix layout: system blocks follow the stable thesis order, and
every system block carries an ephemeral ``cache_control`` breakpoint so the
longest stable prefix that repeats between requests stays warm (instructions
first, then evidence; volatile tool output sits in the last block, and the
task is the user message). Anthropic allows up to 4 breakpoints; this uses at
most 3.
"""
from __future__ import annotations

from .layout import build_prompt_sections, system_text

DEFAULT_MODEL = "claude-sonnet-4-5"

_GROUPS = (("instructions",), ("explicit", "interface", "implementation", "test"),
           ("tool_output", "supporting"))


def _system_blocks(sections):
    blocks = []
    for names in _GROUPS:
        text = system_text([s for s in sections if s.name in names])
        if text.strip():
            blocks.append({"type": "text", "text": text,
                           "cache_control": {"type": "ephemeral"}})
    return blocks


def render_anthropic_messages(package, *, model: str = DEFAULT_MODEL,
                              instructions: str = "", tool_outputs=(),
                              task=None, max_tokens: int = 4096) -> dict:
    """Render an Anthropic Messages API request body for this package."""
    sections = build_prompt_sections(
        package, instructions=instructions, tool_outputs=tool_outputs)
    blocks = _system_blocks(sections)
    if len(blocks) > 4:
        raise ValueError("prompt-cache breakpoint budget exceeded (4 max)")
    task_text = package.task if task is None else task
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": blocks,
        "messages": [{"role": "user",
                      "content": [{"type": "text", "text": task_text}]}],
    }
