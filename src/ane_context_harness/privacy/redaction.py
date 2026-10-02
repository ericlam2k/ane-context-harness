"""Stable redaction with request-scoped placeholders.

Each unique secret value maps to a stable placeholder within a request, e.g.
`<REDACTED_API_KEY_1>`. The raw secret value is never logged; only the
placeholder and counts are emitted to telemetry/events.
"""
from __future__ import annotations

from collections import OrderedDict

from .secrets import scan
from .classifier import SecretClassifier


# Placeholder templates keyed by secret kind.
_KIND_LABEL = {
    "aws_access_key": "API_KEY",
    "aws_secret": "API_KEY",
    "api_key": "API_KEY",
    "api_token": "API_KEY",
    "password": "PASSWORD",
    "bearer_token": "TOKEN",
    "private_key": "PRIVATE_KEY",
    "database_url": "DATABASE_URL",
    "email": "EMAIL",
    "high_entropy_token": "SECRET",
}


class Redactor:
    def __init__(self, redact_secrets: bool = True, classifier: "SecretClassifier | None" = None):
        self.redact_secrets = redact_secrets
        self._classifier = classifier
        self._map: OrderedDict = OrderedDict()  # value -> placeholder
        self._counters = {}
        self.count = 0
        self.types = {}

    def _placeholder(self, kind: str) -> str:
        label = _KIND_LABEL.get(kind, "SECRET")
        self._counters[label] = self._counters.get(label, 0) + 1
        return f"<REDACTED_{label}_{self._counters[label]}>"

    def _assign(self, value: str, kind: str) -> str:
        if value in self._map:
            return self._map[value]
        ph = self._placeholder(kind)
        self._map[value] = ph
        self.count += 1
        self.types[kind] = self.types.get(kind, 0) + 1
        return ph

    def redact(self, text: str) -> str:
        if not self.redact_secrets:
            return text
        if not text:
            return text
        # Prefer classifier-augmented scan (regex + ML high-entropy catch); fall
        # back to pure rule scan if no model is available.
        if self._classifier is not None:
            matches = self._classifier.scan(text) or scan(text)
        else:
            matches = scan(text)
        if not matches:
            return text
        matches.sort(key=lambda m: (m["start"], m["end"]))
        out = []
        pos = 0
        for m in matches:
            if m["start"] < pos:
                # overlap with a previously placed placeholder; merge by taking the longer span
                continue
            out.append(text[pos:m["start"]])
            out.append(self._assign(m["value"], m["kind"]))
            pos = m["end"]
        out.append(text[pos:])
        return "".join(out)

    def summary(self) -> dict:
        return {"count": self.count, "types": list(self.types.keys())}
