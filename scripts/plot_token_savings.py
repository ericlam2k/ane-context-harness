"""Render docs/token-savings.png from benchmarks/reports/token-savings.json.

Two panels: (A) per-task baseline vs sent tokens with the recall gate
stated; (B) identical-pack format medians (JSON / markdown / compact).
All numbers come from scripts/measure_token_savings.py (public functions
only) — this script draws, never measures.

Usage:
    ~/.venvs/ane-p36/bin/python scripts/plot_token_savings.py
"""
from __future__ import annotations

import json
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


def _panel_header(ax, letter, title, right=""):
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 82), 100, 18, facecolor=BAND,
                           edgecolor="none", zorder=1))
    ax.add_patch(Rectangle((2, 84.5), 9, 13, facecolor="white",
                           edgecolor="none", zorder=2))
    ax.text(6.5, 91, letter, ha="center", va="center", fontsize=11,
            fontweight="bold", color=BAND, zorder=3)
    ax.text(14, 91, title, ha="left", va="center", fontsize=10,
            fontweight="bold", color="white", zorder=3)
    if right:
        ax.text(98, 91, right, ha="right", va="center", fontsize=8,
                color="white", zorder=3)


def main() -> None:
    rep = json.loads(DATA.read_text(encoding="utf-8"))
    tasks = sorted(rep["tasks"], key=lambda r: -r["baseline"])
    labels = [t["task_id"].replace("-001", "") for t in tasks]
    base = [t["baseline"] for t in tasks]
    sent = [t["sent"] for t in tasks]
    med = rep["medians"]
    fmts = rep["median_format_tokens"]

    fig = plt.figure(figsize=(12, 6.5), facecolor=PAPER)
    gs = fig.add_gridspec(2, 2, height_ratios=[12, 88], hspace=0.05,
                          left=0.06, right=0.96, top=0.93, bottom=0.08)

    # Header band
    axh = fig.add_subplot(gs[0, :])
    _panel_header(axh, "S", "Token savings, measured — eval split, one counter",
                  f"median {med['reduction_pct']}% · min recall {rep['min_recall']}")

    # Panel A: per-task baseline vs sent
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(PAPER)
    y = range(len(tasks))
    ax.barh(list(y), base, height=0.62, color=MUTED, alpha=0.55,
            label="send everything")
    ax.barh(list(y), sent, height=0.62, color=GREEN, label="harness sends")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("tokens (pinned counter)", fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.text(0.98, 0.02,
            f"median sent {med['sent']:.0f} instead of {med['baseline']:.0f}\n"
            f"min required-evidence recall {rep['min_recall']} (all {rep['n_tasks']} tasks)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            color=BAND, bbox=dict(facecolor="white", edgecolor=MUTED,
                                  boxstyle="round,pad=0.4"))

    # Panel B: format medians on the identical pack
    bx = fig.add_subplot(gs[1, 1])
    bx.set_facecolor(PAPER)
    names = ["evidence-JSON", "markdown", "compact"]
    vals = [fmts["json"], fmts["markdown"], fmts["compact"]]
    colors = [MUTED, BLUE, ORANGE]
    bars = bx.barh(names, vals, height=0.5, color=colors)
    bx.set_xlabel("median tokens, identical pack", fontsize=9)
    base_json = vals[0]
    for bar, v in zip(bars, vals):
        pct = (base_json - v) / base_json * 100
        bx.text(v + 18, bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}  (−{pct:.0f}% vs JSON)" if pct else f"{v:.0f}",
                va="center", fontsize=9, color=BAND)
    bx.text(0.02, 0.02, "same evidence, three renderings —\n"
                        "rendering never touches selection",
            transform=bx.transAxes, ha="left", va="bottom", fontsize=8,
            color=MUTED)

    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
