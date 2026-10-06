"""Render docs/context-packing-overview.png: one real job, traced end to end.

Karpathy-style explainer, not a spec sheet: a single top-to-bottom story
in plain words, one running example, real numbers from the real pipeline.
Everything shown is measured, not illustrated:

  task      "Fix the discount calculation bug in math.ts and verify its tests"
            (benchmark task ts-discount-001, frozen eval split)
  terms     usable_terms() -> ['discount', 'calculation', 'math', 'verify']
  scored    5 chunks in tests/fixtures/synthetic_ts_project
  packed    src/math.ts:1-20 (score 0.9298, named_symbol+mandatory, verbatim)
            tests/math.test.ts:1-20 (score 1.0, flies on merit, structural)
  sent      369 tokens of a 1,236-token repo (-70.15%, recall 1.0)

Usage:
    ~/.venvs/ane-p36/bin/python scripts/plot_packing_overview.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "context-packing-overview.png"

INK = "#1a1a1a"
MUTED = "#5a5a5a"
GREEN = "#1e7d32"
RED = "#c62828"
PAPER = "#f7f5ef"
BAND = "#20242b"
CARD = "#ffffff"
WASH = "#eceae2"


def _stage(ax, n: int, y_top: float, title: str, line: str):
    """Numbered stage header. Returns the y below it for content."""
    import matplotlib
    ax.add_patch(matplotlib.patches.Circle(
        (6, y_top), 3.2, facecolor=BAND, edgecolor="none", zorder=2))
    ax.text(6, y_top, str(n), ha="center", va="center", fontsize=13,
            fontweight="bold", color="white", zorder=3)
    ax.text(11.5, y_top + 0.6, title, ha="left", va="center", fontsize=13,
            fontweight="bold", color=INK)
    ax.text(11.5, y_top - 3.4, line, ha="left", va="center", fontsize=10,
            color=MUTED)
    return y_top - 7.5


def _arrow(ax, y_from: float, y_to: float, x: float = 50.0):
    ax.annotate("", xy=(x, y_to), xytext=(x, y_from),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.6))


def _pill(ax, x: float, y: float, text: str, kept: bool):
    import matplotlib
    w = len(text) * 1.75 + 4.5
    color = GREEN if kept else MUTED
    ax.add_patch(matplotlib.patches.FancyBboxPatch(
        (x, y - 1.8), w, 3.6, boxstyle="round,pad=0.3",
        facecolor="#e6f2e8" if kept else WASH,
        edgecolor=color, linewidth=1.2 if kept else 0.8))
    ax.text(x + w / 2, y, text, ha="center", va="center", fontsize=10.5,
            color=color, fontweight="bold" if kept else "normal")
    if not kept:
        ax.plot([x + 0.8, x + w - 0.8], [y, y], color=MUTED, lw=1.1)
    return w


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(11, 14), facecolor=PAPER)
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Header band: the whole story in two lines.
    ax.add_patch(matplotlib.patches.Rectangle(
        (0, 93.5), 100, 6.5, facecolor=BAND, edgecolor="none", zorder=1))
    ax.text(50, 97.6, "How your words become what the AI reads",
            ha="center", va="center", fontsize=15, fontweight="bold",
            color="white", zorder=2)
    ax.text(50, 94.9, "one real job, traced end to end — nothing rewritten, nothing lost",
            ha="center", va="center", fontsize=9.5, color="#bbbbbb", zorder=2)

    # All y values below are measured, not eyeballed: every content top sits
    # >=1 unit under its subtitle, and stage circles keep >=0.2 clearance
    # from the block above (boxes: pill ±2.1, card ±2.5, row ±1.9).

    # ---- 1. Your words ----
    _stage(ax, 1, 89.0, "You ask in plain words",
           "a real benchmark job, word for word")
    ax.text(50, 82.3, "\u201cFix the discount calculation bug in math.ts "
            "and verify its tests\u201d",
            ha="center", va="center", fontsize=11, style="italic", color=INK,
            bbox=dict(boxstyle="round,pad=0.6", facecolor=CARD,
                      edgecolor=MUTED))
    _arrow(ax, 79.4, 77.6)

    # ---- 2. Search terms ----
    _stage(ax, 2, 76.4, "Small words fall away, the rest go hunting",
           "under 4 letters or generic (test, fix, …) → ignored")
    x = 6.0
    for t in ["discount", "calculation", "math", "verify"]:
        x += _pill(ax, x, 68.9, t, True) + 2.0
    x = 6.0
    for t in ["Fix", "the", "bug", "in", "and", "its", "tests"]:
        x += _pill(ax, x, 63.2, t, False) + 2.0
    ax.text(98, 63.2, "ignored", ha="right", va="center", fontsize=9,
            color=MUTED)
    _arrow(ax, 60.1, 58.3)

    # ---- 3. Every file scored ----
    _stage(ax, 3, 56.9, "Every chunk of the repo gets a score",
           "5 chunks scored, ranked best-first — the top 2 earn a seat")
    rows = [("tests/math.test.ts", "1.00", True, 50.0),
            ("src/math.ts", "0.93", True, 45.8),
            ("3 more chunks", "too low", False, 41.6)]
    for name, score, flies, yy in rows:
        if flies:
            ax.add_patch(matplotlib.patches.Rectangle(
                (6, yy - 1.9), 88, 3.8, facecolor="#e6f2e8",
                edgecolor=GREEN, linewidth=1.0))
        ax.text(9, yy, name, ha="left", va="center", fontsize=10.5,
                color=INK if flies else MUTED)
        ax.text(91, yy, "flies ✓" if flies else "stays",
                ha="right", va="center", fontsize=10,
                fontweight="bold" if flies else "normal",
                color=GREEN if flies else MUTED)
        ax.text(70, yy, score, ha="right", va="center", fontsize=10.5,
                color=INK if flies else MUTED, family="monospace")
    _arrow(ax, 39.1, 37.3)

    # ---- 4. Why these two ----
    _stage(ax, 4, 36.3, "Pinned words fly first, then the best fit",
           "each card carries the reason it flew — argue with it")
    cards = [
        ("src/math.ts",
         "\u201cmath\u201d is its name → pinned, travels byte-exact", 28.8),
        ("tests/math.test.ts",
         "test of the pinned file → flies too, as written", 23.2),
    ]
    for name, why, yy in cards:
        ax.add_patch(matplotlib.patches.FancyBboxPatch(
            (6, yy - 2.2), 88, 4.4, boxstyle="round,pad=0.3",
            facecolor=CARD, edgecolor=MUTED))
        ax.text(9, yy + 0.6, name, ha="left", va="center", fontsize=10.5,
                fontweight="bold", color=INK, family="monospace")
        ax.text(9, yy - 1.2, why, ha="left", va="center", fontsize=9.5,
                color=MUTED)
    _arrow(ax, 20.1, 18.3)

    # ---- 5. What the AI reads ----
    _stage(ax, 5, 17.2, "The AI reads this — and only this",
           "checked against the answer key: nothing needed is missing")
    ax.text(50, 10.9, "369 tokens", ha="center", va="center", fontsize=24,
            fontweight="bold", color=GREEN)
    ax.text(50, 8.4, "instead of the whole 1,236  ·  70% less",
            ha="center", va="center", fontsize=11, color=INK)

    # ---- Footer: what never happens ----
    ax.add_patch(matplotlib.patches.Rectangle(
        (4, 0.5), 92, 6.8, facecolor=BAND, edgecolor="none"))
    ax.text(50, 6.0, "What never happens", ha="center", va="center",
            fontsize=10, fontweight="bold", color="white")
    nevers = [("✕  code is never rewritten — byte-exact", 6),
              ("✕  docs are never paraphrased — as written", 38),
              ("✕  only logs fold, with a note", 74)]
    for n, x in nevers:
        ax.text(x, 3.0, n, ha="left", va="center", fontsize=8,
                color="white")

    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return fig


if __name__ == "__main__":
    main()
