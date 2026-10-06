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


def main():
    rep = json.loads(DATA.read_text(encoding="utf-8"))
    sel = rep["selection"]
    fmt = rep["format_median_tokens"]

    fig = plt.figure(figsize=(13, 6.4), facecolor=PAPER)
    # Generous outer margins: y-tick labels live left of the axes and value
    # annotations live right of the bars — both must clear the figure edge.
    # Header row is 20 units so the band (24 units tall) fully contains the
    # title and the two-line brief fits under it without touching anything.
    gs = fig.add_gridspec(2, 2, height_ratios=[20, 80], hspace=0.05,
                          wspace=0.30, left=0.20, right=0.74, top=0.93,
                          bottom=0.10)

    axh = fig.add_subplot(gs[0, :])
    axh.set_xlim(0, 100)
    axh.set_ylim(0, 100)
    axh.axis("off")
    axh.add_patch(Rectangle((0, 76), 100, 24, facecolor=BAND,
                            edgecolor="none", zorder=1))
    axh.add_patch(Rectangle((2, 79), 9, 18, facecolor="white",
                            edgecolor="none", zorder=2))
    axh.text(6.5, 88, "C", ha="center", va="center", fontsize=10,
             fontweight="bold", color=BAND, zorder=3)
    axh.text(14, 88, "Same 18 jobs, same measuring stick",
             ha="left", va="center", fontsize=11, fontweight="bold",
             color="white", zorder=3)
    axh.text(98, 88, "outside tools run here, no accounts",
             ha="right", va="center", fontsize=8, color="white", zorder=3)
    # Caption: how the two panels relate, in plain words.
    axh.text(2, 58, "Left: how much each tool sends for the same 18 jobs. "
                    "Right: our pick from the left, written four ways.",
             ha="left", va="center", fontsize=9, color=MUTED, zorder=3)
    axh.text(2, 42, "Same files in, same answer out — the wrapping never "
                    "changes the pick. We kept every needed file 18/18.",
             ha="left", va="center", fontsize=9, color=MUTED, zorder=3)

    # Panel A: selection medians.
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(PAPER)
    ax.text(0.02, 0.98, "How much each tool sends", transform=ax.transAxes,
            ha="left", va="top", fontsize=9.5, fontweight="bold", color=BAND)
    names = ["send everything", "ane-harness", "headroom"]
    vals = [sel["median_baseline"], sel["median_ours"],
            sel["median_headroom"]]
    bars = ax.barh(names, vals, height=0.5, color=[MUTED, GREEN, RED])
    ax.set_xlabel("middle job, in tokens", fontsize=9)
    ax.set_xlim(0, max(vals) * 2.0)  # room for value + gate notes
    # Headroom above the tallest bar so the in-panel title never touches it.
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + 0.05 * (hi - lo))
    ax.tick_params(axis="y", labelsize=9)
    notes = ["everything, uncut",
             "needed files kept every time",
             "lost a needed file once"]
    for bar, v, note in zip(bars, vals, notes):
        mid = bar.get_y() + bar.get_height() / 2
        ax.text(v + max(vals) * 0.02, mid + 0.11, f"{v:.0f}", va="center",
                fontsize=10, fontweight="bold", color=BAND)
        ax.text(v + max(vals) * 0.02, mid - 0.14, note, va="center",
                fontsize=7, color=MUTED)

    # Panel B: format medians on the identical pack.
    bx = fig.add_subplot(gs[1, 1])
    bx.set_facecolor(PAPER)
    bx.text(0.02, 0.98, "Our files, four wrappings", transform=bx.transAxes,
            ha="left", va="top", fontsize=9.5, fontweight="bold", color=BAND)
    fnames = ["full detail", "readable", "TOON", "short"]
    fvals = [fmt["evidence_json"], fmt["markdown"], fmt["toon_real"],
             fmt["compact_ours"]]
    fbars = bx.barh(fnames, fvals, height=0.5,
                    color=[MUTED, BLUE, "#6a1b9a", ORANGE])
    bx.set_xlabel("middle job, in tokens", fontsize=9)
    bx.set_xlim(0, max(fvals) * 1.6)  # room for "1134 (−16%)"
    lo, hi = bx.get_ylim()
    bx.set_ylim(lo, hi + 0.05 * (hi - lo))
    bx.tick_params(axis="y", labelsize=9)
    base = fvals[0]
    for bar, v in zip(fbars, fvals):
        pct = (base - v) / base * 100 if base else 0
        label = f"{v:.0f}  (−{pct:.0f}%)" if pct else f"{v:.0f}"
        bx.text(v + max(fvals) * 0.02,
                bar.get_y() + bar.get_height() / 2, label,
                va="center", fontsize=8.5, color=BAND)

    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return fig


if __name__ == "__main__":
    main()
