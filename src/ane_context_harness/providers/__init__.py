"""Phase 4 provider adapters (FR-8): Anthropic Messages, OpenAI Responses,
generic OpenAI-compatible chat, and Markdown. Adapters format provider-neutral
context only — they must not own retrieval or ranking logic.
"""
from __future__ import annotations

from .anthropic import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL, render_anthropic_messages
from .compact import render_compact
from .layout import SECTION_ORDER, SECTION_TITLES, PromptSection, build_prompt_sections, canonical_json, system_text
from .markdown import render_markdown, render_prompt_markdown
from .openai import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL, render_openai_responses
from .openai_compat import DEFAULT_MODEL as OPENAI_COMPAT_DEFAULT_MODEL, render_openai_chat

SERIALIZERS = {
    "anthropic": render_anthropic_messages,
    "openai": render_openai_responses,
    "openai_compat": render_openai_chat,
    "markdown": render_prompt_markdown,
    "compact": render_compact,
}

_ALIASES = {
    "claude": "anthropic",
    "openai-compatible": "openai_compat",
    "openai_compatible": "openai_compat",
    "responses": "openai",
    "md": "markdown",
    "plain": "markdown",
}


def serialize(provider: str, package, **kwargs):
    """Render ``package`` with the named adapter. Returns a dict payload for
    JSON providers and a Markdown string for ``markdown``."""
    name = _ALIASES.get(provider, provider)
    if name not in SERIALIZERS:
        raise ValueError(
            f"unknown provider {provider!r}; expected one of {sorted(SERIALIZERS)}")
    return SERIALIZERS[name](package, **kwargs)


__all__ = [
    "SERIALIZERS", "SECTION_ORDER", "SECTION_TITLES", "PromptSection",
    "build_prompt_sections", "canonical_json", "system_text",
    "render_anthropic_messages", "render_openai_responses", "render_openai_chat",
    "render_prompt_markdown", "render_markdown", "render_compact", "serialize",
]
