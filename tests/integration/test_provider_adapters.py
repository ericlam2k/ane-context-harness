"""Integration: Phase 4 provider adapters end-to-end.

Thesis acceptance: at least one end-to-end integration test per adapter, the
same evidence serialized equivalently for every provider, stable prompt
ordering, prompt-cache-aware prefix layout, and no provider-specific logic
inside retrieval/ranking (FR-8).
"""
from __future__ import annotations

import pytest

from src.ane_context_harness.compression import compress_tool_output
from src.ane_context_harness.providers import (
    SECTION_ORDER,
    SECTION_TITLES,
    build_prompt_sections,
    canonical_json,
    render_anthropic_messages,
    render_openai_chat,
    render_openai_responses,
    render_prompt_markdown,
    serialize,
)
from src.ane_context_harness.schemas import SelectRequest

PYTEST_FAILURE = """collected 3 items
tests/test_discount.py F                                            [ 33%]

=================================== FAILURES ===================================
_________________________________ test_bulk ____________________________________
    def test_bulk():
>       assert calc(10) == 90
E       assert 95 == 90
tests/test_discount.py:12: AssertionError
FAILED tests/test_discount.py::test_bulk - AssertionError: 95 != 90
========================= 1 failed, 2 passed in 0.11s =========================
"""


@pytest.fixture
def selection(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="Fix the incorrect discount calculation and update its tests",
        token_budget=1500,
        explicit_paths=["src/discount.py"],
    )
    return pipeline.select_context(req)


@pytest.fixture
def tool_outputs():
    return [compress_tool_output("test", "pytest -q", 1, PYTEST_FAILURE,
                                 token_budget=600)]


def _titles_in_order(text: str) -> list:
    positions = []
    for name in SECTION_ORDER:
        marker = f"## {SECTION_TITLES[name]}"
        if marker in text:
            positions.append(text.index(marker))
    return positions


def test_sections_follow_thesis_stable_order(selection, tool_outputs):
    sections = build_prompt_sections(selection, tool_outputs=tool_outputs)
    names = [s.name for s in sections]
    assert names == sorted(names, key=SECTION_ORDER.index)
    assert names[0] == "instructions"
    assert "tool_output" in names
    assert "supporting" in names
    tool_i, support_i = names.index("tool_output"), names.index("supporting")
    assert tool_i < support_i  # thesis order: errors/tool output before supporting


def test_anthropic_adapter_e2e(selection, tool_outputs):
    payload = render_anthropic_messages(selection, tool_outputs=tool_outputs)
    assert payload["model"] and isinstance(payload["max_tokens"], int)
    blocks = payload["system"]
    assert blocks and all(b["type"] == "text" for b in blocks)
    assert len(blocks) <= 4
    assert all(b.get("cache_control") == {"type": "ephemeral"} for b in blocks)
    text = "\n\n".join(b["text"] for b in blocks)
    assert "src/discount.py" in text
    assert "## Recent errors and tool output" in text
    assert "command: pytest -q" in text
    pos = _titles_in_order(text)
    assert pos == sorted(pos)
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert msg["content"][0]["text"] == selection.task


def test_openai_responses_adapter_e2e(selection, tool_outputs):
    payload = render_openai_responses(selection, tool_outputs=tool_outputs)
    assert set(payload) == {"model", "input"}
    roles = [item["role"] for item in payload["input"]]
    assert roles == ["system", "user"]
    system_text = payload["input"][0]["content"]
    assert "src/discount.py" in system_text
    assert "## Recent errors and tool output" in system_text
    pos = _titles_in_order(system_text)
    assert pos == sorted(pos)
    assert payload["input"][1]["content"] == selection.task


def test_openai_compatible_adapter_e2e(selection, tool_outputs):
    payload = render_openai_chat(selection, tool_outputs=tool_outputs)
    assert set(payload) == {"model", "messages"}
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user"]
    system_text = payload["messages"][0]["content"]
    assert "src/discount.py" in system_text
    pos = _titles_in_order(system_text)
    assert pos == sorted(pos)
    assert payload["messages"][1]["content"] == selection.task


def test_markdown_adapter_e2e(selection, tool_outputs):
    doc = render_prompt_markdown(selection, tool_outputs=tool_outputs)
    assert isinstance(doc, str)
    assert doc.startswith(f"# {selection.task}")
    assert "src/discount.py" in doc
    assert "## Recent errors and tool output" in doc
    pos = _titles_in_order(doc)
    assert pos == sorted(pos)


def test_all_adapters_serialize_equivalent_evidence(selection, tool_outputs):
    kwargs = {"tool_outputs": tool_outputs}
    anthropic = canonical_json(render_anthropic_messages(selection, **kwargs))
    openai = canonical_json(render_openai_responses(selection, **kwargs))
    compat = canonical_json(render_openai_chat(selection, **kwargs))
    markdown = render_prompt_markdown(selection, **kwargs)
    for ev in selection.evidence:
        loc = f"{ev['path']}:{ev['start_line']}-{ev['end_line']}"
        for rendered in (anthropic, openai, compat, markdown):
            assert loc in rendered, f"{loc} missing from an adapter payload"


def test_serialization_is_deterministic(selection, tool_outputs):
    kwargs = {"tool_outputs": tool_outputs}
    assert canonical_json(render_anthropic_messages(selection, **kwargs)) == \
        canonical_json(render_anthropic_messages(selection, **kwargs))
    assert render_prompt_markdown(selection, **kwargs) == \
        render_prompt_markdown(selection, **kwargs)


def test_serialize_registry(selection):
    assert isinstance(serialize("anthropic", selection), dict)
    assert isinstance(serialize("openai", selection), dict)
    assert isinstance(serialize("openai-compatible", selection), dict)
    assert isinstance(serialize("claude", selection), dict)
    assert isinstance(serialize("markdown", selection), str)
    with pytest.raises(ValueError):
        serialize("gemini", selection)


def test_retrieval_has_no_provider_logic():
    import pathlib
    retrieval = pathlib.Path("src/ane_context_harness/retrieval")
    banned = ("anthropic", "openai", "cache_control", "providers.")
    for f in retrieval.glob("*.py"):
        src = f.read_text()
        for token in banned:
            assert token not in src, f"{f.name} contains provider token {token!r}"
