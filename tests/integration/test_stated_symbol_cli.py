"""Integration: `select --stated-symbol` / `--stated-need` end-to-end.

The failure mode pinned here: the agent knows which symbol or path it
needs, states it, and the harness must validate + pack it through the
existing claims-first contract — or say honestly that it could not
resolve the statement. A stated need that was silently ignored, or an
unresolved stated symbol silently packed anyway, reintroduces the silent
miss / silent guess pair this feature exists to close.

Hermetic via tmp ANE_HARNESS_CONFIG storage (same pattern as the
exclude-path tests): no pollution of the real ~/.ane_context_harness.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = str(ROOT / "tests/fixtures/synthetic_py_project")
# No content word of src/discount.py (or of calculate_discount) appears in
# this task text.
TASK = ("Customers keep getting the wrong amount at checkout; "
        "find the piece responsible and fix it.")


def _env() -> dict:
    env = dict(os.environ)
    env["ANE_HARNESS_NO_LOAD_SENSE"] = "1"
    src = str(ROOT / "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev}" if prev else src
    return env


def _run(tmp_path, monkeypatch, *args, **kw):
    storage = tmp_path / "store"
    cfg = tmp_path / "stated_cli_config.yaml"
    cfg.write_text(f"index:\n  storage_path: {storage}\n",
                   encoding="utf-8")
    monkeypatch.setenv("ANE_HARNESS_CONFIG", str(cfg))
    return subprocess.run(
        [sys.executable, "-m", "ane_context_harness.cli", *args],
        capture_output=True, text=True, timeout=180,
        env=_env(), **kw)


def _norm(obj):
    """Zero the volatile leaves; byte-compare everything else.

    Latency floats (key ends in ``_ms``), ``request_id``, ``model_lifecycle``
    and the retention cache key can never be byte-equal across runs and are
    not selection bytes.
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key == "model_lifecycle":
                out[key] = "<lifecycle>"
            elif key == "request_id":
                out[key] = "<request_id>"
            elif key == "key":
                out[key] = "<retention_key>"
            elif key.endswith("_ms"):
                out[key] = 0.0
            elif key == "ttl_remaining_s":
                out[key] = 0.0
            elif key == "markdown_length":
                # render_markdown embeds total_latency_ms, so the length
                # jitters with wall-clock; the evidence array in the JSON
                # output is compared byte-identically instead.
                out[key] = "<markdown_length>"
            else:
                out[key] = _norm(value)
        return out
    if isinstance(obj, list):
        return [_norm(v) for v in obj]
    if isinstance(obj, str):
        # The footer summary embeds wall-clock latency ("· 40 ms ·").
        # Everything else in it (pack size, cut share, chunk count) is a
        # decision byte and must stay byte-identical.
        return re.sub(r"\u00b7 \d+ ms \u00b7", "\u00b7 <ms> \u00b7", obj)
    return obj


def _index(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "index", "--repo", REPO,
             "--repo-id", "stated_cli")
    assert r.returncode == 0, r.stderr


def test_stated_symbol_packs_resolved_chunk(tmp_path, monkeypatch):
    """A stated symbol the task never names is packed when it fits.

    Caught failure: the agent states the need and the harness silently
    ignores it.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "calculate_discount")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    paths = [e["path"] for e in data["evidence"]]
    assert "src/discount.py" in paths
    block = data["metrics"]["diagnostics"]["stated_need_resolution"]
    assert block["total"] == 1
    assert block["resolved"] == 1
    assert block["unresolved"] == 0
    assert block["items"][0]["stated"] == "calculate_discount"
    assert block["items"][0]["resolved"] is True
    assert block["items"][0]["matched_symbol"] == "calculate_discount"
    assert "not inference" in block["note"]


def test_stated_path_packs_resolved_chunk(tmp_path, monkeypatch):
    """A stated repository path resolves on exact path membership."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "src/discount.py")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert "src/discount.py" in [e["path"] for e in data["evidence"]]
    item = data["metrics"]["diagnostics"]["stated_need_resolution"]["items"][0]
    assert item["resolved"] is True
    assert item["matched_path"] == "src/discount.py"


def test_stated_symbol_unresolved_never_packs(tmp_path, monkeypatch):
    """An unresolved stated symbol is reported and packs nothing.

    Caught failure: a typo'd or absent symbol silently treated as real
    evidence. The pack must be identical to the unstated baseline (modulo
    the additive stated_need_resolution key).
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "zzz_absent_symbol")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    block = data["metrics"]["diagnostics"]["stated_need_resolution"]
    assert block["unresolved"] == 1
    item = block["items"][0]
    assert item["resolved"] is False
    assert item["matched_symbol"] is None
    assert item["matched_path"] is None
    # Shares no identifier subtoken with any indexed symbol: the
    # suggestion list is honestly empty rather than padded.
    assert item["nearest"] == []
    assert item["nearest_note"] == "no similar indexed symbols"
    base = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
                "--task", TASK, "--budget", "800")
    assert base.returncode == 0, base.stderr
    base_data = json.loads(base.stdout)
    assert [e["path"] for e in data["evidence"]] == [
        e["path"] for e in base_data["evidence"]]
    assert "stated_need_resolution" not in base_data["metrics"]["diagnostics"]


def test_stated_symbol_nearest_suggests_indexed_symbols(tmp_path, monkeypatch):
    """An unresolved stated symbol names its nearest indexed neighbours."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "calcluate_discount")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    item = data["metrics"]["diagnostics"]["stated_need_resolution"]["items"][0]
    assert item["resolved"] is False
    assert "calculate_discount" in item["nearest"]
    assert len(item["nearest"]) <= 3


def test_repeatable_flags_all_reported(tmp_path, monkeypatch):
    """Every --stated-symbol occurrence produces one resolution record."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "calculate_discount",
               "--stated-symbol", "zzz_absent_symbol")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    block = data["metrics"]["diagnostics"]["stated_need_resolution"]
    assert [i["stated"] for i in block["items"]] == [
        "calculate_discount", "zzz_absent_symbol"]
    assert (block["resolved"], block["unresolved"]) == (1, 1)


def test_stated_need_free_text_merges_into_claims(tmp_path, monkeypatch):
    """Stated-need free text is mined like task text and merged the same way.

    Caught failure: --stated-need parsed by a second, drifting extractor.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", "calculate_discount")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    paths = [e["path"] for e in data["evidence"]]
    assert "src/discount.py" in paths
    # The need is mined, not validated: the block is present (a need was
    # stated) but carries no per-item entry.
    block = data["metrics"]["diagnostics"]["stated_need_resolution"]
    assert block["items"] == []
    assert block["total"] == 0


def test_no_stated_flags_byte_identical(tmp_path, monkeypatch):
    """With nothing stated the select output is byte-identical to today.

    Caught failure: the stated-need machinery leaking into unstated
    requests — a new diagnostics key, a different evidence order, or a
    changed pack. Two flag-less runs must agree on every decision leaf.
    """
    _index(tmp_path, monkeypatch)
    first = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
                 "--task", TASK, "--budget", "800")
    second = _run(tmp_path, monkeypatch, "select", "--repo-id",
                  "stated_cli", "--task", TASK, "--budget", "800")
    assert first.returncode == 0 and second.returncode == 0
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    assert _norm(a) == _norm(b)
    for data in (a, b):
        assert "stated_need_resolution" not in data["metrics"]["diagnostics"]


def test_recovery_prompt_fires_on_budget_cut_unstated(tmp_path, monkeypatch):
    """The affordance ships when a stated-flag-free run had to cut named
    evidence — the agent never learns the stated-need escape otherwise.

    Caught failure: the pack cuts the evidence the task needs (here the
    discount module at a starving budget), the recovery block lists the
    cut, and the result says nothing about how to ask exactly. The line
    must carry the honest missed count from the recovery block totals,
    the missed path pointer, and the re-select instruction."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", "Fix the incorrect discount calculation",
               "--budget", "30", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    diag = data["metrics"]["diagnostics"]
    rec = diag["recovery"]
    assert rec["required_claims_total"] - rec["required_claims_covered"] >= 1
    prompt = data["recovery_prompt"]
    assert prompt == diag["recovery_prompt"]
    n = str(rec["required_claims_total"] - rec["required_claims_covered"])
    assert f"{n} required claim" in prompt
    assert "src/discount.py" in prompt
    assert "--stated-symbol" in prompt and "--stated-need" in prompt


def test_recovery_prompt_names_unresolved_and_nearest(tmp_path, monkeypatch):
    """An unresolved stated symbol is named with the nearest indexed
    symbols the resolution records already carry (or an honest zero-match
    line) — nothing is recomputed for the prompt.

    Caught failure: the agent states a need the index cannot resolve and
    the harness either goes quiet or invents proximity. `nonexistent_thing`
    shares no identifier subtoken with any indexed symbol and must say so;
    `calcluate_discount` shares subtokens with real indexed symbols and
    must surface them. Neither case involves the recovery block (a budget
    of 800 covers this fixture end-to-end for the discount claims)."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "nonexistent_thing", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert "recovery" not in data["metrics"]["diagnostics"]
    prompt = data["recovery_prompt"]
    assert "Stated symbol(s) not found in index: nonexistent_thing." in prompt
    assert "no similar indexed symbols" in prompt
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "calcluate_discount", "--quiet")
    assert out.returncode == 0, out.stderr
    prompt = json.loads(out.stdout)["recovery_prompt"]
    assert "Stated symbol(s) not found in index: calcluate_discount." in prompt
    assert "calculate_discount" in prompt


def test_recovery_prompt_absent_when_nothing_cut_and_nothing_stated(
        tmp_path, monkeypatch):
    """Empty recovery + nothing stated → no recovery_prompt key anywhere.

    Caught failure: the affordance fires with a fabricated count or a
    fabricated promise on a run where the whole fixture fits the budget.
    The key must be absent, not present-but-empty."""
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", "Fix the login bug", "--budget", "30000",
               "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert "recovery" not in data["metrics"]["diagnostics"]
    assert "recovery_prompt" not in data
    assert "recovery_prompt" not in data["metrics"]["diagnostics"]


def test_recovery_prompt_footer_clause_only_when_fired(tmp_path, monkeypatch):
    """The printed footer carries the ask clause exactly when the
    affordance fired; a covered unstated run's footer keeps the pinned
    LOCAL est. pack contract with no clause.

    Caught failure: every footer (or none) advertises the re-select
    affordance — or the clause moves ahead of the est. figures it must
    follow. The clause is appended at the end of the LOCAL est. pack
    line, only on firing runs."""
    _index(tmp_path, monkeypatch)
    fired = _run(tmp_path, monkeypatch, "select", "--repo-id",
                 "stated_cli", "--task",
                 "Fix the incorrect discount calculation", "--budget", "30")
    assert fired.returncode == 0, fired.stderr
    footer = fired.stderr.strip().splitlines()[0]
    assert footer.startswith("ane-harness: LOCAL est. pack")
    assert footer.endswith(
        "· ask: re-select with --stated-symbol if evidence misses")
    assert footer.count("ask: re-select") == 1
    fired_json = json.loads(fired.stdout)
    assert fired_json["summary"].endswith(
        "· ask: re-select with --stated-symbol if evidence misses")
    unfired = _run(tmp_path, monkeypatch, "select", "--repo-id",
                   "stated_cli", "--task", "Fix the login bug",
                   "--budget", "30000")
    assert unfired.returncode == 0, unfired.stderr
    footer = unfired.stderr.strip().splitlines()[0]
    assert footer.startswith("ane-harness: LOCAL est. pack")
    assert "ask: re-select" not in footer
    unfired_json = json.loads(unfired.stdout)
    assert "ask: re-select" not in unfired_json["summary"]


def test_stated_need_garbage_text_cannot_repack_baseline(tmp_path,
                                                         monkeypatch):
    """A garbage stated-need must not change the pack vs the no-flag run.

    Caught failure: the need text was mined unvalidated and merged into
    claim identification — a garbage fragment rode in as a claim term and
    repacked the budget through incidental claim admission. Unanchored
    mined terms must be dropped before claims are identified and
    disclosed as dropped.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", "zzz_mock_need", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    base = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
                "--task", TASK, "--budget", "800", "--quiet")
    assert base.returncode == 0, base.stderr
    base_data = json.loads(base.stdout)
    assert [e["path"] for e in data["evidence"]] == [
        e["path"] for e in base_data["evidence"]]
    stripped = _norm(data)
    stripped["metrics"]["diagnostics"].pop("stated_need_resolution_note")
    stripped["metrics"]["diagnostics"].pop("stated_need_resolution")
    assert stripped == _norm(base_data)
    note = data["metrics"]["diagnostics"]["stated_need_resolution_note"]
    assert note["kept"] == []
    assert note["dropped"] == sorted(note["dropped"])
    for term in ("zzz_mock_need", "need", "zzz", "mock"):
        assert term in note["dropped"]


def test_stated_need_index_anchors_survive(tmp_path, monkeypatch):
    """Terms that anchor to the index stay claim terms.

    Caught failure (the other direction): an anchor gate tight enough to
    drop everything — a stated need the index CAN answer must keep
    packing the evidence it names.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", "calculate_discount", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert "src/discount.py" in [e["path"] for e in data["evidence"]]
    note = data["metrics"]["diagnostics"]["stated_need_resolution_note"]
    for rec in note["kept"]:
        assert rec["matched_chunks"] == 1
    assert [rec["term"] for rec in note["kept"]] == sorted(
        rec["term"] for rec in note["kept"])
    assert "calculate_discount" in [rec["term"] for rec in note["kept"]]
    assert note["dropped"] == []
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", "discount gate", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    note = data["metrics"]["diagnostics"]["stated_need_resolution_note"]
    assert note == {"kept": [{"term": "discount", "matched_chunks": 1}],
                    "dropped": ["gate"]}


def test_stated_need_all_anchorless_terms_yield_no_claims(tmp_path,
                                                          monkeypatch):
    """A need whose every term anchors nowhere packs nothing extra.

    Caught failure: the honest empty case — the note must report the
    drop (no invented matches), claim identification must receive zero
    mined terms, and the pack must be identical to the no-flag baseline.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", "q q q", "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    base = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
                "--task", TASK, "--budget", "800", "--quiet")
    assert base.returncode == 0, base.stderr
    base_data = json.loads(base.stdout)
    assert [e["path"] for e in data["evidence"]] == [
        e["path"] for e in base_data["evidence"]]
    diag = data["metrics"]["diagnostics"]
    assert diag["stated_need_resolution"]["items"] == []
    assert diag["stated_need_resolution"]["total"] == 0
    assert diag["stated_need_resolution_note"] == {
        "kept": [],
        "dropped": ["q"]}


def test_stated_symbol_without_need_emits_no_note(tmp_path, monkeypatch):
    """Resolved symbols/paths without a need stay exactly as before.

    Caught failure: the note leaking into runs that never stated a need —
    it is additive strictly when --stated-need was given. Stated symbols
    keep exactly the pre-existing diagnostics shape.
    """
    _index(tmp_path, monkeypatch)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-symbol", "calculate_discount", "--quiet")
    assert out.returncode == 0, out.stderr
    diag = json.loads(out.stdout)["metrics"]["diagnostics"]
    assert diag["stated_need_resolution"]["items"] == [
        {"stated": "calculate_discount", "resolved": True,
         "matched_symbol": "calculate_discount", "matched_path": None}]
    assert "stated_need_resolution_note" not in diag


# Fuzz guard: the index-anchor gate must not be overfit to any single
# token. Each of these high-frequency English function/stem words, as
# the SOLE free-text stated need, must leave the pack byte-identical to
# the no-flag baseline. Words the gate keeps on this fixture anchor to
# the index but cite zero packed chunks (stoplisted or below the
# usability floor), so they stay inert.
_FUZZ_NEED_WORDS = ["need", "get", "set", "run", "find", "test",
                    "do", "to", "gate", "flag", "marker", "check"]
_FUZZ_GATE = {
    "need": ([], ["need"]),
    "get": ([], ["get"]),
    "set": ([{"term": "set", "matched_chunks": 0}], []),
    "run": ([{"term": "run", "matched_chunks": 0}], []),
    "find": ([], ["find"]),
    "test": ([{"term": "test", "matched_chunks": 0}], []),
    "do": ([{"term": "do", "matched_chunks": 0}], []),
    "to": ([{"term": "to", "matched_chunks": 0}], []),
    "gate": ([], ["gate"]),
    "flag": ([], ["flag"]),
    "marker": ([], ["marker"]),
    "check": ([], ["check"]),
}


@pytest.mark.parametrize("word", _FUZZ_NEED_WORDS)
def test_stated_need_function_word_keeps_baseline_pack(
        word, tmp_path, monkeypatch):
    """One adversarial function word as the sole --stated-need must not
    flip the pack vs the no-flag baseline.

    Caught failure: the index-anchor gate overfits to a single
    high-frequency word — other everyday words slip through a hole and
    incidentally repack the budget through claim admission. Pack bytes
    and every decision leaf except the two additive stated-need
    diagnostics must equal the baseline; the note must report exactly
    what the gate kept/dropped.
    """
    _index(tmp_path, monkeypatch)
    base = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
                "--task", TASK, "--budget", "800", "--quiet")
    assert base.returncode == 0, base.stderr
    base_data = json.loads(base.stdout)
    out = _run(tmp_path, monkeypatch, "select", "--repo-id", "stated_cli",
               "--task", TASK, "--budget", "800",
               "--stated-need", word, "--quiet")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert _norm(data["evidence"]) == _norm(base_data["evidence"])
    stripped = _norm(data)
    stripped["metrics"]["diagnostics"].pop("stated_need_resolution_note")
    stripped["metrics"]["diagnostics"].pop("stated_need_resolution")
    assert stripped == _norm(base_data)
    diag = data["metrics"]["diagnostics"]
    kept, dropped = _FUZZ_GATE[word]
    assert diag["stated_need_resolution"]["items"] == []
    assert diag["stated_need_resolution_note"] == {"kept": kept,
                                                   "dropped": dropped}
