"""Integration: compacted conversation summary stays out of evidence/scoring.

A compacted summary is dense with identifiers (files edited, symbols touched,
error strings). If a caller stuffs it into ``task``, every identifier becomes
a mandatory symbol pin and the pack explodes (ADR-005). The contract under
test: ``conversation_summary`` is rendered in the markdown report's
"Conversation state" section only, and never reaches candidate ranking,
mandatory retention, or the evidence list.
"""
from __future__ import annotations

from src.ane_context_harness.schemas import SelectRequest
from src.ane_context_harness.providers.markdown import render_markdown


def test_conversation_summary_rendered_not_scored(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    summary = ("Edited checkout.py, discount.py, tax.py and payment.credit_card. "
               "Saw NameError: undefined variable card_cvv in payment.credit_card. "
               "Fix the missing token and verify.")
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="Fix the missing token in payment.credit_card",
        token_budget=12000,
        conversation_summary=summary,
    )
    pkg = pipeline.select_context(req)
    pkg.markdown = render_markdown(pkg, conversation=req.conversation_summary or "")

    # (1) summary is present in the rendered report, in its own last section
    assert "## Conversation state" in pkg.markdown
    assert "card_cvv" in pkg.markdown
    assert pkg.markdown.rstrip().endswith(summary.strip().splitlines()[-1])

    # (2) summary identifiers do NOT pin extra mandatory chunks
    mand = {e["path"] for e in pkg.evidence
            if "mandatory" in (e.get("selection_reasons") or [])}
    assert "checkout.py" not in " ".join(mand)
    assert "tax.py" not in " ".join(e["path"] for e in pkg.evidence)
    # payment.credit_card appears because it matched the TASK symbol, not the
    # summary — prove that by dropping the summary and getting the same pins.
    req_plain = SelectRequest(
        repository_id="synthetic_py_project",
        task="Fix the missing token in payment.credit_card",
        token_budget=12000,
    )
    pkg_plain = pipeline.select_context(req_plain)
    mand_plain = {e["path"] for e in pkg_plain.evidence
                  if "mandatory" in (e.get("selection_reasons") or [])}
    assert mand == mand_plain
    # and the evidence content is unchanged
    assert pkg_plain.evidence == pkg.evidence

    # (3) summary text is not itself scored or token-budgeted as evidence
    assert not any("card_cvv" in (e.get("content") or "") for e in pkg.evidence)
    assert req.conversation_summary not in pkg.evidence[0]["content"] if pkg.evidence else True


def test_exclude_paths_drop_chunks_after_ranking(pipeline, py_repo):
    pipeline.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="Fix the incorrect discount calculation",
        token_budget=12000,
        explicit_paths=["src/discount.py"],
        exclude_paths=["tests/test_discount.py"],
    )
    pkg = pipeline.select_context(req)
    sel_paths = {e["path"] for e in pkg.evidence}
    assert "src/discount.py" in sel_paths  # explicit path survives
    assert "tests/test_discount.py" not in sel_paths  # excluded, even though ranked
    assert pkg.metrics["diagnostics"]["excluded"]["chunks_dropped"] >= 1
