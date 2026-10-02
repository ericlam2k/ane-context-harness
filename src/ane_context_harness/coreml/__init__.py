"""Core ML package (Phase 3).

The reranker backend is pluggable: CPU deterministic, Core ML (.all / CPU+GPU /
CPU-only), or a local GPU backend. Phase 2/3 baseline ships with **no bundled
Core ML model**; the runtime loads a model only when `coremltools` is importable
and a compiled `.mlmodel` path is configured. Activation is driven by the
capability profile (measured), never by chip identity.
"""
