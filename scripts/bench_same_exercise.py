"""Same-exercise sandbox bench: us vs AXI-format vs Headroom, identical inputs.

No more cross-table guessing: all three run HERE, on the frozen EVAL split,
measured with ONE ruler (our pinned counter) plus each tool's own counts.

Exercise A — SELECTION (same source: full eligible repo text per task):
  ours-origin : harness select -> evidence (exact-chunk recall gate)
  headroom    : headroom.compress(tool repo_dump) 0.39.1, local, no keys
                (lossy rewrite -> recall measured as required symbols/paths
                still present in output text; explicitly NOT the same gate
                as exact-chunk retention — reported side by side, never merged)

Exercise B — FORMAT (same source: our origin pack per task):
  evidence-json / markdown / compact-ours / toon-real (toon-format 1.0.0,
  the actual AXI encoder, round-trip verified). Tokens + determinism
  (every condition run twice; headroom included).

Writes benchmarks/reports/same-exercise-bench.{json,md}. Eval only by
construction: non-eval ids abort. Third-party tools are OPTIONAL runtime imports (never package
dependencies — the library stays stdlib-only): pip install headroom-ai
toon-format, or set HR_PKGS / TOON_PKGS to scratch install dirs. Without
them the script refuses with install instructions instead of failing
obscurely. No keys, no accounts, no uploads anywhere in this exercise.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import time

SCRATCH_HR = os.environ.get("HR_PKGS", "/tmp/hr-sbx-pkgs")
SCRATCH_TOON = os.environ.get("TOON_PKGS", "/tmp/toonfmt-pkgs")
for _p in (SCRATCH_HR, SCRATCH_TOON):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _need(mod: str, pkg: str):
    try:
        return __import__(mod)
    except ImportError:
        raise SystemExit(
            f"refusing: this exercise needs the public package {pkg} "
            f"(pip install {pkg}); the library itself stays stdlib-only")

from ane_context_harness import schemas
from ane_context_harness.benchmark import (
    FIXTURE_REPO_PATHS,
    baseline_full_context_tokens,
    load_task_split,
    required_chunks_covered,
)
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness import tokens as tokens_mod
from ane_context_harness.providers.compact import render_compact
from ane_context_harness.providers.markdown import render_markdown

HEADROOM_VERSION = "headroom-ai 0.39.1 (scratch install, Apache-2.0)"
TOON_VERSION = "toon-format 1.0.0 (scratch install, real AXI encoder)"


def _repo_dump(repo_path: str) -> str:
    texts = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fn in sorted(files):
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    t = f.read()
                if t and "\x00" not in t:
                    texts.append(t)
            except (OSError, UnicodeDecodeError):
                continue
    return "\n\n".join(texts)


def _hr_compress(text: str) -> tuple[str, dict]:
    headroom = _need("headroom", "headroom-ai")
    t0 = time.perf_counter()
    r = headroom.compress(
        [{"role": "tool", "name": "repo_dump", "content": text}])
    ms = round((time.perf_counter() - t0) * 1000, 2)
    m0 = r.messages[0]
    out = m0["content"] if isinstance(m0, dict) else m0.get("content", "")
    return out, {"tokens_before": r.tokens_before,
                 "tokens_after": r.tokens_after,
                 "ratio": round(r.compression_ratio, 4),
                 "transforms": list(r.transforms_applied or [])[:4],
                 "ms": ms}


def _toon_encode(evidence: list) -> tuple[str, bool]:
    toon_format = _need("toon_format", "toon-format")
    from toon_format import encode, decode
    proj = [{"path": e["path"], "start_line": e["start_line"],
             "end_line": e["end_line"], "symbol": e.get("symbol"),
             "reasons": list(e.get("selection_reasons") or []),
             "content": e.get("content", "")} for e in evidence]
    body = {"evidence": proj}
    text = encode(body)
    return text, decode(text) == body


def _symbols_preserved(output: str, required: list) -> float:
    if not required:
        return 1.0
    hits = 0
    for rc in required:
        needle = rc.get("symbol") or (rc.get("path") or "").split("/")[-1]
        if needle and needle in output:
            hits += 1
    return round(hits / len(required), 4)


def main() -> dict:
    tasks = load_task_split("eval")
    with open("benchmarks/splits.json", encoding="utf-8") as f:
        eval_ids = set(json.load(f)["eval"])
    stray = [t.task_id for t in tasks if t.task_id not in eval_ids]
    if stray:
        raise SystemExit(f"refusing: non-eval tasks: {stray}")

    storage = tempfile.mkdtemp(prefix="aneh-sameex-")
    pipeline = Pipeline(build_config({"index": {"storage_path": storage}}))
    try:
        rows = []
        for task in tasks:
            repo_path = FIXTURE_REPO_PATHS[task.repository_id]
            pipeline.register_repository(repo_path, task.repository_id,
                                         False)
            chunks = pipeline._storage_for(task.repository_id).load_chunks()
            base = baseline_full_context_tokens(chunks)
            # A: ours
            req = schemas.SelectRequest(
                repository_id=task.repository_id, task=task.task,
                token_budget=task.token_budget, explicit_paths=[])
            pkg = pipeline.select_context(req)
            ours_recall = round(required_chunks_covered(
                pkg.evidence, task.required_chunks, chunks), 4)
            ours_tok = sum(tokens_mod.count(e["content"])
                           for e in pkg.evidence)
            # A: headroom (twice — determinism)
            dump = _repo_dump(repo_path)
            hr_out1, hr_meta = _hr_compress(dump)
            hr_out2, _ = _hr_compress(dump)
            hr_tok = tokens_mod.count(hr_out1)
            hr_sym = _symbols_preserved(hr_out1, task.required_chunks)
            # B: formats on the identical pack
            j = tokens_mod.count(json.dumps(pkg.evidence, sort_keys=True,
                                            default=str))
            m = tokens_mod.count(render_markdown(pkg))
            c = tokens_mod.count(render_compact(pkg))
            t_text, t_rt = _toon_encode(pkg.evidence)
            t = tokens_mod.count(t_text)
            c2 = tokens_mod.count(render_compact(pkg))
            rows.append({
                "task_id": task.task_id,
                "baseline": base,
                "ours_tokens": ours_tok, "ours_recall": ours_recall,
                "hr_tokens": hr_tok, "hr_symbols_preserved": hr_sym,
                "hr_own_before": hr_meta["tokens_before"],
                "hr_own_after": hr_meta["tokens_after"],
                "hr_ms": hr_meta["ms"],
                "hr_deterministic": hr_out1 == hr_out2,
                "fmt_json": j, "fmt_markdown": m, "fmt_compact": c,
                "fmt_toon": t, "toon_roundtrip": t_rt,
                "compact_deterministic": c == c2,
            })
        med = lambda k: round(statistics.median([r[k] for r in rows]), 1)
        min_rec = min(r["ours_recall"] for r in rows)
        min_sym = min(r["hr_symbols_preserved"] for r in rows)
        det = all(r["hr_deterministic"] for r in rows)
        report = {
            "split": "eval", "n_tasks": len(tasks),
            "third_party": {"headroom": HEADROOM_VERSION,
                            "toon": TOON_VERSION},
            "ruler": ("one counter (pinned regex-heuristic) on all outputs; "
                      "each tool's own counts recorded alongside, never mixed"),
            "selection": {
                "median_baseline": med("baseline"),
                "median_ours": med("ours_tokens"),
                "median_headroom": med("hr_tokens"),
                "min_ours_recall_exact_chunk": min_rec,
                "min_headroom_symbols_preserved": min_sym,
                "headroom_deterministic_all": det,
            },
            "format_median_tokens": {
                "evidence_json": med("fmt_json"), "markdown": med("fmt_markdown"),
                "compact_ours": med("fmt_compact"), "toon_real": med("fmt_toon"),
            },
            "toon_roundtrip_all": all(r["toon_roundtrip"] for r in rows),
            "compact_deterministic_all": all(
                r["compact_deterministic"] for r in rows),
            "verdict": ("same exercise, same ruler — see tasks"),
            "notes": [
                "Headroom runs locally (no keys, no uploads); small inputs "
                "it protects rather than compresses, full repo dumps it "
                "rewrites (lossy).",
                "Recall gates differ by construction: ours demands the exact "
                "required chunk retained; headroom's lossy output is checked "
                "for required symbol/path presence. Both reported, never merged.",
            ],
            "tasks": rows,
        }
        with open("benchmarks/reports/same-exercise-bench.json", "w",
                   encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        md = ["# Same-exercise bench (us vs TOON vs Headroom, one ruler)", "",
              f"tasks: {len(tasks)} (frozen eval) | "
              f"headroom {HEADROOM_VERSION.split('(')[0].strip()} | "
              f"toon {TOON_VERSION.split('(')[0].strip()}", "",
              "## Selection (full repo in, tokens out)", "",
              f"median baseline {report['selection']['median_baseline']} | "
              f"ours {report['selection']['median_ours']} "
              f"(min recall {min_rec}) | headroom "
              f"{report['selection']['median_headroom']} "
              f"(min symbols {min_sym}, deterministic: {det})", "",
              "## Format (identical pack rendered)", "",
              f"json {report['format_median_tokens']['evidence_json']} | "
              f"markdown {report['format_median_tokens']['markdown']} | "
              f"compact {report['format_median_tokens']['compact_ours']} | "
              f"toon {report['format_median_tokens']['toon_real']} "
              f"(round-trip: {report['toon_roundtrip_all']})", ""]
        with open("benchmarks/reports/same-exercise-bench.md", "w",
                   encoding="utf-8") as f:
            f.write("\n".join(md))
        print("\n".join(md))
        return report
    finally:
        pipeline.close()
        shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()
