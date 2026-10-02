"""OpenAI Responses API adapter (FR-8). Formatting only — no retrieval logic.

Prompt-cache-aware prefix layout: one canonical system message built from the
stable thesis-ordered sections (identical inputs serialize byte-identically),
with the volatile task as the trailing user message. OpenAI prompt caching
keys on the identical prefix; no extra parameter is required.
"""
from __future__ import annotations

from .layout import build_prompt_sections, system_text

DEFAULT_MODEL = "gpt-4o"


def render_openai_responses(package, *, model: str = DEFAULT_MODEL,
                            instructions: str = "", tool_outputs=(),
                            task=None) -> dict:
    """Render an OpenAI Responses API request body for this package."""
    sections = build_prompt_sections(
        package, instructions=instructions, tool_outputs=tool_outputs)
    task_text = package.task if task is None else task
    return {
        "model": model,
        "input": [
            {"role": "system", "content": system_text(sections)},
            {"role": "user", "content": task_text},
        ],
    }
