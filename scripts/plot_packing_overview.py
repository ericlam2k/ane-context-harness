#!/usr/bin/env python3
"""Render docs/context-packing-overview.png: STE100-style one-page poster
explaining how ane-harness packs prompts (6 panels A-F).

Adapted from the ASD-STE100 overview sheet: same panel grammar (structure,
annotated rewrite, keep/drop table, reason dictionary, limit sliders,
history) applied to context packing instead of controlled writing.

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
ORANGE = "#e65100"
BLUE = "#1565c0"
PAPER = "#f7f5ef"
BAND = "#20242b"


def _header(ax, letter: str, title: str, right: str = "") -> None:
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(__import__("matplotlib").patches.Rectangle(
        (0, 82), 100, 18, facecolor=BAND, edgecolor="none", zorder=1))
    ax.add_patch(__import__("matplotlib").patches.Rectangle(
        (2, 84.5), 9, 13, facecolor="white", edgecolor="none", zorder=2))
    ax.text(6.5, 91, letter, ha="center", va="center", fontsize=11,
            fontweight="bold", color=BAND, zorder=3)
    ax.text(14, 91, title, ha="left", va="center", fontsize=10,
            fontweight="bold", color="white", zorder=3)
    if right:
        ax.text(98, 91, right, ha="right", va="center", fontsize=7,
                color="#bbbbbb", zorder=3)


def _panel_a(ax) -> None:
    _header(ax, "A", "Packed context structure", "what the LLM receives")
    ax.text(50, 74, "Task (your words) + repo → 710 chunks scored → 23 packed",
            ha="center", va="center", fontsize=8, color=INK,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor=MUTED))
    rows = [
        "Task: Implement … threshold gating",
        "Tokens: 7.1k of 211.2k (96.6% reduction) | 165 ms",
        "## Evidence: phase6_multiagent.py:36-52",
        "Symbol: `run_concurrent` · Score 0.06 · Hash `a91f…`",
        "Reasons: named_symbol, lexical_rerank, mandatory",
        "< the code >",
    ]
    for i, r in enumerate(rows):
        ax.text(6, 62 - i * 8.5, r, ha="left", va="center", fontsize=7.5,
                color=INK, family="monospace" if i > 1 else "sans-serif")
    ax.text(50, 6, "211.2k in → 7.1k out · 23 cards fly, ~687 stay",
            ha="center", va="center", fontsize=7.5, style="italic", color=MUTED)


def _panel_b(ax) -> None:
    _header(ax, "B", "Anatomy of a task rewrite", "real task → terms")
    dropped = {"to", "arm", "c", "ane", "b", "5", "max"}
    generic = {"test", "main"}
    terms = ["implement", "runtime", "max_concurrent_agents", "max",
             "concurrent", "agents", "agent", "threshold", "gating", "auto",
             "route", "to", "arm", "c", "ane", "reranker", "5", "b"]
    ax.text(50, 74, "Task words, not STE: anything goes in, rules decide pins",
            ha="center", va="center", fontsize=7.5, style="italic", color=MUTED)
    x, y = 4, 62
    for t in terms:
        if t in dropped:
            col, deco = RED, "strikethrough"
        elif t in generic:
            col, deco = ORANGE, "strikethrough"
        else:
            col, deco = GREEN, "none"
        w = max(len(t) * 1.55 + 3, 9.0)
        if x + w > 99:
            x, y = 4, y - 11
        ax.text(x + w / 2, y, t, ha="center", va="center", fontsize=8,
                color=col, style="normal")
        if deco == "strikethrough":
            ax.plot([x + 1, x + w - 1], [y, y], color=col, lw=1.2)
        x += w + 1.5
    notes = [
        ("red", "dropped: len<4 never pins (to, arm, c, ane, b, 5, max)"),
        ("orange", "generic never pins: test, main, run, …"),
        ("green", "usable: agents→agent fold · max_concurrent_agents splits in 3"),
    ]
    for i, (_, n) in enumerate(notes):
        ax.text(4, 26 - i * 8, n, ha="left", va="center", fontsize=7,
                color=MUTED)
    ax.text(50, 3, "1 word, 1 meaning · identifiers split · max 60 cards ranked",
            ha="center", va="center", fontsize=7, color=MUTED)


def _table(ax, columns: list, rows: list, widths: list | None = None,
           y_top: float = 78, row_h: float = 9.5, fs: int = 7) -> None:
    import matplotlib.pyplot as plt  # noqa
    n = len(columns)
    widths = widths or [1.0 / n] * n
    xs = [0.0]
    for w in widths:
        xs.append(xs[-1] + w)
    for j, c in enumerate(columns):
        ax.text((xs[j] + xs[j + 1]) / 2 * 100, y_top, c, ha="center",
                va="center", fontsize=fs, color=MUTED)
    for i, row in enumerate(rows):
        y = y_top - (i + 1) * row_h
        if i % 2 == 0:
            ax.add_patch(__import__("matplotlib").patches.Rectangle(
                (0, y - row_h / 2), 100, row_h, facecolor="#eceae2",
                edgecolor="none", zorder=0))
        for j, cell in enumerate(row):
            color = INK
            if cell.startswith("✓"):
                color = GREEN
            elif cell.startswith("✗"):
                color = RED
            ax.text((xs[j] + xs[j + 1]) / 2 * 100, y, cell, ha="center",
                    va="center", fontsize=fs, color=color)


def _panel_c(ax) -> None:
    _header(ax, "C", "Keep / drop forms", "which cards fly")
    _table(ax, ["Form", "Example", "Status"],
           [["you name it", "--explicit-path auth.py", "✓ Kept, always"],
            ["word = symbol", '"reranker" → def reranker', "✓ Kept (pinned)"],
            ["test of kept", "test_auth.py", "✓ Kept (pinned)"],
            ["scores well + fits", "0.43, room left", "✓ Kept on merit"],
            ["scores low / full", "0.02, budget full", "✗ Dropped"],
            ["file share full", "4th card, same file", "✗ Dropped"],
            ["near-duplicate", "restates kept card", "✗ Dropped"],
            ["ranked past 60", "place 61+, unpinned", "✗ Never seen"]],
           widths=[0.30, 0.38, 0.32], y_top=74, row_h=8.2, fs=6.8)


def _panel_d(ax) -> None:
    _header(ax, "D", "Reason dictionary entries", "why each card flew")
    _table(ax, ["Reason", "Status", "Meaning"],
           [["explicit_path", "✓ PINNED", "you named it"],
            ["named_symbol", "✓ PINNED", "task word = symbol"],
            ["test_pair", "✓ PINNED", "test of pinned file"],
            ["lexical_rerank", "✓ ON MERIT", "scored well, fit"],
            ["over_budget", "✗ CUT", "beyond allowance"],
            ["per_file_cap", "✗ CUT", "file share full"],
            ["mmr_similar", "✗ CUT", "near-duplicate"]],
           widths=[0.32, 0.30, 0.38], y_top=74, row_h=9.2, fs=6.8)
    ax.text(50, 4, "Every card carries its reasons: the receipt you can argue with.",
            ha="center", va="center", fontsize=7, style="italic", color=MUTED)


def _panel_e(ax) -> None:
    _header(ax, "E", "Packing rule limits", "maximum values")
    specs = [("Chunk size", 400, 400, "tokens"),
             ("Card overlap", 40, 400, "tokens"),
             ("Budget (soft)", 12000, 20000, "tokens"),
             ("Diversity window", 60, 100, "cards"),
             ("Per-file share", 25, 100, "% of budget"),
             ("MMR similarity", 0.25, 1.0, "λ")]
    for i, (name, val, vmax, unit) in enumerate(specs):
        y = 70 - i * 11
        ax.text(2, y, name, ha="left", va="center", fontsize=7.5, color=INK)
        ax.add_patch(__import__("matplotlib").patches.Rectangle(
            (30, y - 2.5), 55 * val / vmax, 5, facecolor="#9db8d2",
            edgecolor=BLUE, zorder=2))
        ax.plot([30, 85], [y - 2.5, y - 2.5], color=MUTED, lw=0.8, zorder=1)
        ax.plot([30, 85], [y + 2.5, y + 2.5], color=MUTED, lw=0.8, zorder=1)
        ax.text(88, y, f"max {val} {unit}", ha="left", va="center",
                fontsize=7, color=MUTED)
    ax.text(50, 2, "Soft budget: pinned cards exceed it · discretionary never does.",
            ha="center", va="center", fontsize=7, style="italic", color=MUTED)


def _panel_f(ax) -> None:
    _header(ax, "F", "History", "how we got here")
    miles = [("Ph0-2", "foundation\n+ profiles"), ("Ph5", "A/B: deterministic\nadopted"),
             ("Ph6", "ANE wins at\n5+ agents"), ("Now", "floor policy +\nthis sheet")]
    for i, (yr, label) in enumerate(miles):
        x = 12 + i * 25
        ax.plot([x], [58], marker="o", markersize=7, color=BAND)
        if i > 0:
            ax.plot([12 + (i - 1) * 25, x], [58, 58], color=MUTED, lw=1.2)
        ax.text(x, 66, yr, ha="center", va="center", fontsize=8,
                fontweight="bold", color=INK)
        ax.text(x, 46, label, ha="center", va="center", fontsize=6.5,
                color=MUTED)
    ax.text(50, 26, "Context packing: overview", ha="center", va="center",
            fontsize=10, fontweight="bold", color=INK)
    for i, (k, v) in enumerate([("Rulebook", "this sheet"), ("Engine", "deterministic"),
                                ("Recall (eval)", "1.0 arm B"), ("Sheet", "1 of 1")]):
        y = 18 - i * 4.5
        ax.text(20, y, k, ha="left", va="center", fontsize=7, color=MUTED)
        ax.text(80, y, v, ha="right", va="center", fontsize=7, color=INK)


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(16, 10.5), facecolor=PAPER)
    gs = fig.add_gridspec(2, 3, hspace=0.12, wspace=0.12,
                          left=0.02, right=0.98, top=0.96, bottom=0.04)
    makers = [_panel_a, _panel_b, _panel_c, _panel_d, _panel_e, _panel_f]
    for i, make in enumerate(makers):
        ax = fig.add_subplot(gs[i // 3, i % 3], facecolor="white")
        for spine in ax.spines.values():
            spine.set_edgecolor(MUTED)
        make(ax)
    fig.savefig(OUT, dpi=150, facecolor=PAPER)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
