"""Conversation-to-state compaction: structure, verbatim recency, adapters."""
import pytest

from ane_context_harness.conversation import (
    compact_turns,
    render_conversation_state,
    section_for,
)


def _turns():
    return [
        {"role": "user", "content": "Fix the discount bug in checkout"},
        {"role": "assistant", "content": "Looking at src/discounts/apply.ts now."},
        {"role": "user", "content": "Also check the VAT profile while you are there, "
                                    "it has been wrong since Tuesday deploy"},
        {"role": "assistant", "content": "VAT profile fixed in this patch."},
    ]


def test_objective_is_first_user_turn():
    c = compact_turns(_turns())
    assert c["objective"] == "Fix the discount bug in checkout"
    assert c["turns"] == 4


def test_recent_verbatim_earlier_excerpted():
    c = compact_turns(_turns(), keep_recent=2, excerpt_chars=20)
    assert [m["content"] for m in c["recent"]] == [
        "Also check the VAT profile while you are there, "
        "it has been wrong since Tuesday deploy",
        "VAT profile fixed in this patch."]
    assert [e["n"] for e in c["earlier"]] == [1, 2]
    assert all(len(e["excerpt"]) <= 21 for e in c["earlier"])
    assert c["earlier"][0]["excerpt"].endswith("…")


def test_strings_coerced_to_user_turns():
    c = compact_turns(["hello", {"role": "assistant", "content": "hi"}])
    assert c["objective"] == "hello"
    assert c["turns"] == 2


def test_garbage_turns_rejected():
    with pytest.raises(ValueError):
        compact_turns([{"nope": 1}])
    with pytest.raises(ValueError):
        compact_turns([None])
    with pytest.raises(ValueError):
        compact_turns([], keep_recent=-1)


def test_empty_turns_section_empty():
    assert section_for([]) == ""
    assert section_for(None) == ""
    c = compact_turns([])
    assert c["objective"] == "" and c["recent"] == [] and c["earlier"] == []


def test_render_stable_and_ordered():
    a = render_conversation_state(compact_turns(_turns()))
    b = render_conversation_state(compact_turns(_turns()))
    assert a == b
    assert a.index("Objective:") < a.index("Recent turns") < a.index("Earlier")


def test_adapters_include_conversation_last(tmp_path):
    from ane_context_harness.config import build_config, merge
    from ane_context_harness.pipeline import Pipeline
    from ane_context_harness import schemas
    from ane_context_harness.providers import serialize
    from ane_context_harness.providers.layout import canonical_json
    cfg = build_config(merge(
        {"index": {"storage_path": str(tmp_path / "s")}}, {}))
    pipe = Pipeline(cfg)
    pipe.register_repository("tests/fixtures/synthetic_py_project", "conv")
    req = schemas.SelectRequest(repository_id="conv",
                                task="Fix the discount calculation",
                                token_budget=2000)
    pkg = pipe.select_context(req)
    turns = _turns()
    for name in ("anthropic", "openai", "openai_compat", "markdown"):
        one = serialize(name, pkg, conversation_turns=turns)
        two = serialize(name, pkg, conversation_turns=turns)
        text = (canonical_json(one) if not isinstance(one, str) else one)
        assert text == (canonical_json(two)
                        if not isinstance(two, str) else two)
        assert "Fix the discount bug in checkout" in text
    # without turns the payload is unchanged from before this feature
    plain = serialize("anthropic", pkg)
    assert all("Conversation state" not in b.get("text", "")
               for b in plain["system"])
    assert len(plain["system"]) <= 3  # breakpoint budget intact
    conv = serialize("anthropic", pkg, conversation_turns=turns)
    assert "Conversation state" in conv["system"][-1]["text"]
    # evidence still precedes conversation in the last block
    assert conv["system"][-1]["text"].index("Fix the discount bug") > 0
