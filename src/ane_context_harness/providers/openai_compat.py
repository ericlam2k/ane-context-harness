"""Generic OpenAI-compatible adapter (FR-8): chat/completions payloads for
local endpoints (Ollama, vLLM, llama.cpp, LM Studio, ...). Formatting only —
no retrieval logic. Same canonical, cache-friendly prefix ordering as the
Responses adapter.
"""
from __future__ import annotations

from ..conversation import section_for as _conversation_section
from .layout import build_prompt_sections, system_text

DEFAULT_MODEL = "local-model"


def render_openai_chat(package, *, model: str = DEFAULT_MODEL,
                       instructions: str = "", tool_outputs=(),
                       task=None, conversation_turns=()) -> dict:
    """Render an OpenAI-compatible chat/completions request body."""
    sections = build_prompt_sections(
        package, instructions=instructions, tool_outputs=tool_outputs,
        conversation=_conversation_section(conversation_turns))
    task_text = package.task if task is None else task
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text(sections)},
            {"role": "user", "content": task_text},
        ],
    }
