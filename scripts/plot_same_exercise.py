"""Render docs/same-exercise-comparison.png from
benchmarks/reports/same-exercise-bench.json.

Panel A: median tokens per selection method on identical repos, with the
evidence-survival gate stated for each. Panel B: identical-pack format
medians (JSON / markdown / real TOON / compact). Draws only — all numbers
come from scripts/bench_same_exercise.py.

Usage:
    ~/.venvs/ane-p36/bin/python scripts/plot_same_exercise.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks" / "reports" / "same-exercise-bench.json"
OUT = ROOT / "docs" / "same-exercise-comparison.png"

PAPER = "#f7f5ef"
BAND = "#20242b"
GREEN = "#1e7d32"
BLUE = "#1565c0"
MUTED = "#5a5a5a"
ORANGE = "#e65100"
RED = "#c62828"


def main() -> None:
    rep = json.loads(DATA.read_text(encoding="utf-8"))
    sel = rep["selection"]
    fmt = rep["format_median_tokens"]

    fig = plt.figure(figsize=(12, 6.2), facecolor=PAPER)
    gs = fig.add_gridspec(2, 2, height_ratios=[12, 88], hspace=0.05,
                          left=0.06, right=0.96, top=0.93, bottom=0.10)

    axh = fig.add_subplot(gs[0, :])
    axh.set_xlim(0, 100)
    axh.set_ylim(0, 100)
    axh.axis("off")
    axh.add_patch(Rectangle((0, 82), 100, 18, facecolor=BAND,
                            edgecolor="none", zorder=1))
    axh.add_patch(Rectangle((2, 84.5), 9, 13, facecolor="white",
                            edgecolor="none", zorder=2))
    axh.text(6.5, 91, "C", ha="center", va="center", fontsize=11,
             fontweight="bold", color=BAND, zorder=3)
    axh.text(14, 91, "Same exercise, one ruler — 18 eval tasks",
             ha="left", va="center", fontsize=10, fontweight="bold",
             color="white", zorder=3)
    axh.text(98, 91, "third-party tools run locally, no keys",
             ha="right", va="center", fontsize=8, color="white", zorder=3)

    # Panel A: selection medians.
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(PAPER)
    names = ["send everything", "harness select", "headroom rewrite"]
    vals = [sel["median_baseline"], sel["median_ours"],
            sel["median_headroom"]]
    bars = ax.barh(names, vals, height=0.5, color=[MUTED, GREEN, RED])
    ax.set_xlabel("median tokens per task", fontsize=9)
    notes = ["baseline (all indexed)",
             f"min recall {rep['selection']['min_ours_recall_exact_chunk']} (exact-chunk gate)",
             f"min symbols {rep['selection']['min_headroom_symbols_preserved']} (presence check)"]
    for bar, v, note in zip(bars, vals, notes):
        ax.text(v + 60, bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}\n{note}", va="center", fontsize=8, color=BAND)

    # Panel B: format medians on the identical pack.
    bx = fig.add_subplot(gs[1, 1])
    bx.set_facecolor(PAPER)
    fnames = ["evidence-JSON", "markdown", "real TOON", "compact"]
    fvals = [fmt["evidence_json"], fmt["markdown"], fmt["toon_real"],
             fmt["compact_ours"]]
    fbars = bx.barh(fnames, fvals, height=0.5,
                    color=[MUTED, BLUE, "#6a1b9a", ORANGE])
    bx.set_xlabel("median tokens, identical pack", fontsize=9)
    base = fvals[0]
    for bar, v in zip(fbars, fvals):
        pct = (base - v) / base * 100 if base else 0
        bx.text(v + 25, bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}  (−{pct:.0f}% vs JSON)" if pct else f"{v:.0f}",
                va="center", fontsize=9, color=BAND)
    bx.text(0.02, 0.02, "round-trip exact; rendering never touches selection",
            transform=bx.transAxes, ha="left", va="bottom", fontsize=8,
            color=MUTED)

    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
