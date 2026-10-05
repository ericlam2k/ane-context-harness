"""Compact renderer: shape, determinism, verbatim content, smaller than markdown.

Portable (public-syncable): providers + schemas only, no stages/retention.
"""
from types import SimpleNamespace

from ane_context_harness import tokens as tokens_mod
from ane_context_harness.config import build_config, merge
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.providers import serialize
from ane_context_harness.providers.compact import render_compact
from ane_context_harness.providers.markdown import render_markdown

FIXTURE = "tests/fixtures/synthetic_py_project"


def _fake_pkg():
    return SimpleNamespace(
        task="Fix the discount calculation",
        repository_id="synthetic_py_project",
        metrics={"selected_tokens": 100, "reduction_percent": 50.0},
        evidence=[
            {"path": "src/discount.py", "start_line": 1, "end_line": 10,
             "symbol": "calculate_discount",
             "selection_reasons": ["named_symbol", "mandatory"],
             "content": "def calculate_discount(price, rate):\n    return price * rate\n"},
            {"path": "tests/test_discount.py", "start_line": 1,
             "end_line": 5, "symbol": None,
             "selection_reasons": ["lexical_rerank"],
             "content": "def test_x():\n    assert True\n"},
        ])


def test_compact_shape_and_verbatim():
    out = render_compact(_fake_pkg())
    assert out.startswith("task: Fix the discount calculation\n")
    assert "evidence[2]{path,start,end,symbol,reasons}:" in out
    # code content rides verbatim (indented under its row, never folded)
    assert "    def calculate_discount(price, rate):\n        return price * rate" in out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_compact_deterministic():
    assert render_compact(_fake_pkg()) == render_compact(_fake_pkg())


def test_compact_via_serialize():
    assert serialize("compact", _fake_pkg()) == render_compact(_fake_pkg())


def test_compact_smaller_than_markdown_on_real_pack(tmp_path):
    base = {"index": {"storage_path": str(tmp_path / "store")}}
    pipe = Pipeline(build_config(merge(base, {})))
    pipe.register_repository(FIXTURE, "nx-compact")
    from ane_context_harness import schemas
    req = schemas.SelectRequest(
        repository_id="nx-compact", task="Fix the discount calculation",
        token_budget=2000)
    pkg = pipe.select_context(req)
    assert pkg.evidence
    c = tokens_mod.count(render_compact(pkg))
    m = tokens_mod.count(render_markdown(pkg))
    assert c < m, f"compact {c} should beat markdown {m}"
