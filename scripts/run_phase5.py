"""Phase 5 end-to-end A/B evaluation runner (frozen eval split).

Runs labelled benchmark tasks through the baseline (full context) and harness
arms, writes JSON + Markdown reports to benchmarks/reports/, and prints the
summary and recommendation. Arm C (Core ML) runs when a qualified calibration
report + built artifact are available (P3.6 passed); otherwise it is reported
as not run. No external calls; local fixtures only.
"""
from __future__ import annotations

from ane_context_harness.evaluation import main

if __name__ == "__main__":
    main()
