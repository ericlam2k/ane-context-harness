"""Render docs/head-to-head.png: ONE chart, all contenders, one ruler.

Hero metric — median tokens served per eval task (pinned counter):
  raw baseline ..... full indexed contents concatenated
  headroom ......... rewritten text as-is (0.39.1, local)
  ours in TOON ..... selected evidence rendered with toon-format 1.0.0
  ours compact ..... selected evidence rendered with serialize("compact")
Each bar annotated with its evidence-survival gate. Selection and format
are different dimensions, so this chart deliberately shows each contender
in its native serving form and says so — the detail panels behind it
(same-exercise-comparison.png) keep the dimensions separate.

Draws only; numbers from benchmarks/reports/same-exercise-bench.json
(scripts/bench_same_exercise.py).

Usage:
    ~/.venvs/ane-p36/bin/python scripts/plot_head_to_head.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks" / "reports" / "same-exercise-bench.json"
OUT = ROOT / "docs" / "head-to-head.png"

PAPER = "#f7f5ef"
BAND = "#20242b"
GREEN = "#1e7d32"
MUTED = "#5a5a5a"
RED = "#c62828"
PURPLE = "#6a1b9a"
ORANGE = "#e65100"


def main():
    rep = json.loads(DATA.read_text(encoding="utf-8"))
    rows = rep["tasks"]
    med = lambda k: round(statistics.median([r[k] for r in rows]), 1)
    base = med("baseline")
    hr = med("hr_tokens")
    toon = med("fmt_toon")
    comp = med("fmt_compact")

    names = ["send\neverything", "headroom\n(rewrite)",
             "ours, readable", "ours, short"]
    vals = [base, hr, toon, comp]
    colors = [MUTED, RED, PURPLE, GREEN]
    gates = ["\n(by definition)", "FAIL — config file\nlost on 1 job",
             "PASS — needed files\nkept every time",
             "PASS — needed files\nkept every time"]

    fig = plt.figure(figsize=(11, 6.0), facecolor=PAPER)
    gs = fig.add_gridspec(2, 1, height_ratios=[13, 87], hspace=0.05,
                          left=0.08, right=0.96, top=0.92, bottom=0.12)
    axh = fig.add_subplot(gs[0])
    axh.set_xlim(0, 100)
    axh.set_ylim(0, 100)
    axh.axis("off")
    axh.add_patch(Rectangle((0, 82), 100, 18, facecolor=BAND,
                            edgecolor="none", zorder=1))
    axh.add_patch(Rectangle((2, 84.5), 9, 13, facecolor="white",
                            edgecolor="none", zorder=2))
    axh.text(6.5, 91, "VS", ha="center", va="center", fontsize=11,
             fontweight="bold", color=BAND, zorder=3)
    axh.text(14, 91, "Same 18 jobs, one measuring stick",
             ha="left", va="center", fontsize=10, fontweight="bold",
             color="white", zorder=3)
    axh.text(98, 91, "median job, in tokens", ha="right", va="center",
             fontsize=8, color="white", zorder=3)

    ax = fig.add_subplot(gs[1])
    ax.set_facecolor(PAPER)
    bars = ax.bar(names, vals, width=0.55, color=colors)
    ax.set_ylabel("middle job, in tokens", fontsize=10)
    ax.set_ylim(0, max(vals) * 1.35)
    for bar, v, g in zip(bars, vals, gates):
        ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.02,
                f"{v:.0f}", ha="center", fontsize=12, fontweight="bold",
                color=BAND)
        ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.10,
                g, ha="center", fontsize=8,
                color=RED if g.startswith("FAIL") else MUTED)
    best = (base - comp) / base * 100
    ax.text(0.98, 0.96, "shortest while keeping\nneeded files every time",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            color=BAND, bbox=dict(facecolor="white", edgecolor=MUTED,
                                  boxstyle="round,pad=0.4"))
    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return fig


if __name__ == "__main__":
    main()
