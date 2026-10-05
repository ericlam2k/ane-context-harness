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
    gs = fig.add_gridspec(2, 2, height_ratios=[14, 86], hspace=0.06,
                          wspace=0.28, left=0.08, right=0.78, top=0.93,
                          bottom=0.10)

    # Header band: the takeaway, not the methodology.
    axh = fig.add_subplot(gs[0, :])
    axh.set_xlim(0, 100)
    axh.set_ylim(0, 100)
    axh.axis("off")
    axh.add_patch(Rectangle((0, 82), 100, 18, facecolor=BAND,
                            edgecolor="none", zorder=1))
    axh.add_patch(Rectangle((2, 84.5), 9, 13, facecolor="white",
                            edgecolor="none", zorder=2))
    axh.text(6.5, 91, "S", ha="center", va="center", fontsize=11,
             fontweight="bold", color=BAND, zorder=3)
    axh.text(14, 91, "Less to read, nothing important lost",
             ha="left", va="center", fontsize=10, fontweight="bold",
             color="white", zorder=3)
    axh.text(98, 91, "18 jobs measured", ha="right", va="center",
             fontsize=8, color="white", zorder=3)

    # Panel A: by job size — whole codebase vs needed parts.
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(PAPER)
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
    ax.set_ylim(0, max(send_all) * 1.32)
    for i, (s, c) in enumerate(zip(sent, cuts)):
        ax.text(i + w / 2, s + max(send_all) * 0.03, f"{s:.0f}\n−{c:.0f}%",
                ha="center", fontsize=9, fontweight="bold", color=BAND)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.text(0.02, 0.96,
            "Harder jobs need more sent — but the saving holds,\n"
            "and the needed files were kept every single time.",
            transform=ax.transAxes, ha="left", va="top", fontsize=8,
            color=MUTED)

    # Panel B: same answer, three wrappings.
    bx = fig.add_subplot(gs[1, 1])
    bx.set_facecolor(PAPER)
    fmts = rep["median_format_tokens"]
    fnames = ["full detail", "readable", "short"]
    fvals = [fmts["json"], fmts["markdown"], fmts["compact"]]
    fbars = bx.barh(fnames, fvals, height=0.5, color=[MUTED, BLUE, ORANGE])
    bx.set_xlabel("middle job, in tokens", fontsize=9)
    bx.set_xlim(0, max(fvals) * 1.6)
    bx.tick_params(axis="y", labelsize=9)
    base = fvals[0]
    for bar, v in zip(fbars, fvals):
        pct = (base - v) / base * 100 if base else 0
        label = f"{v:.0f}  (−{pct:.0f}%)" if pct else f"{v:.0f}"
        bx.text(v + max(fvals) * 0.02,
                bar.get_y() + bar.get_height() / 2, label,
                va="center", fontsize=8.5, color=BAND)
    bx.text(0.02, 0.96, "Shorter wrapping, same answer —\n"
                        "it never changes what gets picked.",
            transform=bx.transAxes, ha="left", va="top", fontsize=8,
            color=MUTED)

    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return fig


if __name__ == "__main__":
    main()
