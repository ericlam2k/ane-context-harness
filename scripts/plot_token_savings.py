"""Render docs/token-savings.png from benchmarks/reports/token-savings.json.

Mass-audience chart: jobs grouped by size (small / everyday / hard),
plain words everywhere, the takeaway written ON the chart. Draws only —
all numbers come from scripts/measure_token_savings.py.

Usage:
    ~/.venvs/ane-p36/bin/python scripts/plot_token_savings.py
"""
from __future__ import annotations

import glob
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks" / "reports" / "token-savings.json"
OUT = ROOT / "docs" / "token-savings.png"

PAPER = "#f7f5ef"
BAND = "#20242b"
GREEN = "#1e7d32"
BLUE = "#1565c0"
MUTED = "#5a5a5a"
ORANGE = "#e65100"

PLAIN_NAMES = {"small": "small jobs", "typical": "everyday jobs",
               "difficult": "hard jobs"}


def main():
    rep = json.loads(DATA.read_text(encoding="utf-8"))
    diff = {}
    for f in glob.glob(str(ROOT / "benchmarks" / "tasks" / "*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        diff[d["task_id"]] = d.get("difficulty", "?")
    groups = []
    for key in ("small", "typical", "difficult"):
        ts = [t for t in rep["tasks"] if diff.get(t["task_id"]) == key]
        groups.append((key, ts))

    fig = plt.figure(figsize=(13, 6.6), facecolor=PAPER)
    # Header row is 20 units so the band (24 units tall) fully contains the
    # title and the two-line brief fits under it without touching anything.
    gs = fig.add_gridspec(2, 2, height_ratios=[20, 80], hspace=0.06,
                          wspace=0.28, left=0.08, right=0.78, top=0.93,
                          bottom=0.10)

    # Header band: the takeaway, not the methodology.
    axh = fig.add_subplot(gs[0, :])
    axh.set_xlim(0, 100)
    axh.set_ylim(0, 100)
    axh.axis("off")
    axh.add_patch(Rectangle((0, 76), 100, 24, facecolor=BAND,
                            edgecolor="none", zorder=1))
    axh.add_patch(Rectangle((2, 79), 9, 18, facecolor="white",
                            edgecolor="none", zorder=2))
    axh.text(6.5, 88, "S", ha="center", va="center", fontsize=10,
             fontweight="bold", color=BAND, zorder=3)
    axh.text(14, 88, "Less to read, nothing important lost",
             ha="left", va="center", fontsize=11, fontweight="bold",
             color="white", zorder=3)
    axh.text(98, 88, "18 jobs measured", ha="right", va="center",
             fontsize=8, color="white", zorder=3)
    # Caption: how the two panels relate, in plain words.
    axh.text(2, 58, "Left: how much less you send per job size — whole "
                    "codebase (grey) vs only the files the job needs "
                    "(green), kept every time.",
             ha="left", va="center", fontsize=9, color=MUTED, zorder=3)
    axh.text(2, 42, "Right: those same chosen files, written three ways — "
                    "a shorter wrapping never changes what gets picked.",
             ha="left", va="center", fontsize=9, color=MUTED, zorder=3)

    # Panel A: by job size — whole codebase vs needed parts.
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(PAPER)
    ax.text(0.02, 0.98, "Whole codebase vs needed parts, by job size",
            transform=ax.transAxes, ha="left", va="top", fontsize=9.5,
            fontweight="bold", color=BAND)
    names, send_all, sent, cuts = [], [], [], []
    for key, ts in groups:
        names.append(f"{PLAIN_NAMES[key]}\n({len(ts)} jobs)")
        send_all.append(round(statistics.median([t["baseline"] for t in ts]), 0))
        sent.append(round(statistics.median([t["sent"] for t in ts]), 0))
        cuts.append(round(statistics.median([t["reduction_pct"] for t in ts]), 1))
    x = range(len(names))
    w = 0.34
    ax.bar([i - w / 2 for i in x], send_all, width=w, color=MUTED,
           alpha=0.55, label="whole codebase")
    bars = ax.bar([i + w / 2 for i in x], sent, width=w, color=GREEN,
                  label="needed parts only")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("middle job, in tokens", fontsize=9)
    ax.set_xlim(-0.6, len(names) - 0.4)
    # 1.32 leaves room above the tallest bar; the extra 5% keeps the
    # in-panel title and legend clear of the value labels.
    ax.set_ylim(0, max(send_all) * 1.386)
    for i, (s, c) in enumerate(zip(sent, cuts)):
        ax.text(i + w / 2, s + max(send_all) * 0.03, f"{s:.0f}\n−{c:.0f}%",
                ha="center", fontsize=9, fontweight="bold", color=BAND)
    # Sits just under the in-panel title row so the two never touch.
    ax.legend(frameon=False, fontsize=9, loc="upper right",
              bbox_to_anchor=(1.0, 0.90))

    # Panel B: same answer, three wrappings.
    bx = fig.add_subplot(gs[1, 1])
    bx.set_facecolor(PAPER)
    bx.text(0.02, 0.98, "The same chosen files, three wrappings",
            transform=bx.transAxes, ha="left", va="top", fontsize=9.5,
            fontweight="bold", color=BAND)
    fmts = rep["median_format_tokens"]
    fnames = ["full detail", "readable", "short"]
    fvals = [fmts["json"], fmts["markdown"], fmts["compact"]]
    fbars = bx.barh(fnames, fvals, height=0.5, color=[MUTED, BLUE, ORANGE])
    bx.set_xlabel("middle job, in tokens", fontsize=9)
    bx.set_xlim(0, max(fvals) * 1.6)
    # Headroom above the tallest bar so the in-panel title never touches it.
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
