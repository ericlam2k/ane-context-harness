"""Structured local event emission. Never includes raw source text.

Events are written to a local JSONL file (path configurable). When telemetry
is disabled, events are dropped. include_source_text is hard-ignored here.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_lock = threading.Lock()


class EventWriter:
    def __init__(self, path: str | os.PathLike | None = None, enabled: bool = True):
        self.enabled = enabled
        self.path = Path(path) if path else None
        self._lines: list[str] = []

    def emit(self, event: dict) -> None:
        if not self.enabled:
            return
        safe = {k: v for k, v in event.items() if k != "content"}
        line = json.dumps(safe, default=str, sort_keys=True)
        with _lock:
            self._lines.append(line)
            if self.path is not None:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")

    def drain(self) -> list[dict]:
        with _lock:
            lines = self._lines
            self._lines = []
        return [json.loads(l) for l in lines]
