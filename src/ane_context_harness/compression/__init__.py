"""Phase 4: local tool-output compression (FR-7). No network, no model."""
from __future__ import annotations

from .tool_output import ALLOWED_KINDS, compress_tool_output

__all__ = ["compress_tool_output", "ALLOWED_KINDS"]
