"""Secret detection: known credential patterns + high-entropy token detection.

Rule-based (CPU). Returns matches with a category and the matched span/value.
Does not emit the raw value to logs; callers receive a structured match only
for redaction, with the raw value handled inside the Redactor (which never
logs it).

Structured files (.env, .json) are scanned key-by-key: a value is scanned
with the rule+entropy detectors, and additionally, when the KEY NAME signals
a secret (e.g. `SECRET_TOKEN`, `AWS_ACCESS_KEY_ID`, `signing_secret`), the
entire value is treated as a secret. This catches secret-named values that
would otherwise escape pattern/entropy checks (high-underscore keys).
"""
from __future__ import annotations

import math
import re


# (label, compiled_regex, group)  — group 0 = whole match, >0 = capturing group with secret
PATTERNS = [
    # AWS access key id
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), 0),
    # AWS secret (40-char base64-ish)
    ("aws_secret", re.compile(r"(?<![A-Za-z0-9/+])(AWS|aws_)[a-z_]+_?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})"), 2),
    # Generic api key/token/password bearer assignments
    ("api_key", re.compile(r"(?i)\b(api[_-]?key|apikey|api-key)\s*[:=]\s*['\"]?([A-Za-z0-9._\-]{8,})"), 2),
    ("api_token", re.compile(r"(?i)\b(api[_-]?token|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9._\-]{8,})"), 2),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{4,})"), 2),
    ("bearer_token", re.compile(r"Bearer\s+([A-Za-z0-9._\-]{8,})"), 1),
    # Private key blocks
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.DOTALL), 0),
    # Database URLs with credentials
    ("database_url", re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@[^\s'\"]+"), 0),
    # Emails (PII)
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0),
]

# A key whose name signals its value is secret, e.g. SECRET_TOKEN, AWS_SECRET_*.
_KEY_SECRET_SIGNAL = re.compile(
    r"(?i)(api[_-]?key|apikey|api-key|secret|token|password|passwd|pwd|bearer|"
    r"credential|credentials|private|access[_-]?key|client[_-]?secret)")

# Scalars that are clearly not secrets even when assigned to a sensitive key.
_SAFE_SCALARS = {"true", "false", "null", "localhost"}


def _is_safe_scalar(value: str) -> bool:
    v = value.strip().strip("\"'").lower()
    return v in _SAFE_SCALARS or v.lstrip("-").isdigit()


def _scan_structured(text: str) -> list:
    """Scan key=value / JSON key:value pairs, by KEY signal and/or VALUE matches.

    The full line is never scanned as a secret (so benign key names are not
    false positives); only the VALUE is inspected, with signal-keys treated as
    authoritative.
    """
    matches = []
    pair_re = re.compile(
        r'(?m)^\s*(?:"([^"]+)"|([^=:{}\s]+))\s*[:=]\s*["\']?([^"\n#]+?)\s*["\']?\s*$'
    )
    for m in pair_re.finditer(text):
        key = (m.group(1) or m.group(2) or "")
        value = m.group(3)
        if not key or not value:
            continue
        if value.startswith("//"):
            # e.g. `postgres://user:pw@host` — left to the URL pattern, not a
            # KEY: value assignment.
            continue
        if _is_safe_scalar(value):
            continue
        base = m.start(3)
        if _KEY_SECRET_SIGNAL.search(key):
            # Key declares intent: redact the whole value regardless of content.
            matches.append({"kind": "api_key", "value": value,
                            "start": base, "end": base + len(value)})
        for found in scan(value):
            matches.append({"kind": found["kind"], "value": found["value"],
                            "start": base + found["start"], "end": base + found["end"]})
    return matches


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    from collections import Counter
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _candidate_tokens(text: str, min_len: int = 16) -> list:
    """Find long base64/hex/alnum tokens for entropy screening."""
    return re.findall(r"[A-Za-z0-9._\-/+=]{16,}", text)


def scan(text: str) -> list:
    """Return list of matches: {kind, value, start, end}.

    Order: key-signal structured scan (.env/.json), then pattern matching over
    the whole text, then high-entropy token screening. Later passes skip spans
    already covered by an earlier match (deduplicated)."""
    matches = list(_scan_structured(text))
    covered: list[tuple[int, int]] = [(m["start"], m["end"]) for m in matches]

    def _overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1]

    for label, regex, group in PATTERNS:
        for m in regex.finditer(text):
            s, e = m.start(group or 0), m.end(group or 0)
            if any(_overlaps((s, e), c) for c in covered):
                continue
            val = m.group(group) if group else m.group(0)
            matches.append({"kind": label, "value": val, "start": s, "end": e})
            covered.append((s, e))

    # high-entropy token detection (deduplicated; never overlaps a prior match)
    for tok_m in re.finditer(r"[A-Za-z0-9+/_\-]{16,}", text):
        s, e = tok_m.start(), tok_m.end()
        if any(_overlaps((s, e), c) for c in covered):
            continue
        ent = shannon_entropy(tok_m.group())
        if ent >= 3.5 and (tok_m.group().count("-") + tok_m.group().count("_")) <= 2:
            matches.append({"kind": "high_entropy_token", "value": tok_m.group(), "start": s, "end": e})
            covered.append((s, e))

    matches.sort(key=lambda m: (m["start"], m["end"]))
    return matches


def scan_and_count(text: str) -> dict:
    matches = scan(text)
    types = {}
    for m in matches:
        types[m["kind"]] = types.get(m["kind"], 0) + 1
    return {"count": len(matches), "types": types}
