#!/usr/bin/env python3
"""Freeze the release-evidence bundle (build + verify) for the current tree.

Usage (from the repo root):
    python3 scripts/freeze_evidence.py --out ane-context-harness-evidence-v0.1

Exits non-zero when the build fails or verification finds any problem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ane_context_harness.evidence import build_bundle, verify_bundle  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ane-context-harness-evidence-v0.1")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    try:
        info = build_bundle(args.out, force=args.force)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "stage": "build", "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "stage": "build", **info}, indent=2))
    result = verify_bundle(args.out)
    print(json.dumps({"stage": "verify", **result}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
