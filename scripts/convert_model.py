"""Phase 3 explicit model-build entrypoint.

Usage:
  python3 scripts/convert_model.py miniLM-L6-MMR1 --seq-len 128 --seq-len 256 [--output-dir DIR]

Requires the optional build dependencies: ``pip install -e '.[build]'``.
Downloads the manifest-pinned Hugging Face checkpoint into the build cache,
converts PyTorch -> Core ML (direct), validates numerics against the source
checkpoint, and atomically publishes a versioned .mlpackage + tokenizer bundle
to the output dir. No runtime downloads occur.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 3 Core ML reranker builder")
    p.add_argument("entry_key", choices=["miniLM-L6-MMR1", "tinyBERT-L2-MMR1"],
                   help="Manifest model key to build")
    p.add_argument("--seq-len", type=int, nargs="+", default=[128, 256],
                   help="Token sequence lengths to build (Phase 3: 128/256 only)")
    p.add_argument("--output-dir", default=None,
                   help="Where to publish artifacts (default: build cache artifacts/)")
    args = p.parse_args(argv)

    for sl in args.seq_len:
        if sl not in (128, 256):
            print(f"error: seq_len {sl} not allowed; Phase 3 supports 128 and 256 only.",
                  file=sys.stderr)
            return 2

    from src.ane_context_harness.coreml import convert as conv
    try:
        for sl in args.seq_len:
            desc = conv.build_model(args.entry_key, sl, output_dir=args.output_dir)
            print(f"built {desc['model_id']} seq={sl} -> {desc['output_path']}")
            print(f"  numeric_validation={desc['numeric_validation']}")
        return 0
    except conv.BuildDependencyMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("hint: run the build under Python 3.13 on macOS/arm64, e.g.:\n"
              "  pyenv install 3.13 && pyenv shell 3.13\n"
              "  pip install -e '.[build]'\n"
              "  python scripts/convert_model.py miniLM-L6-MMR1 --seq-len 128 --seq-len 256",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
