"""Secret detection: known credential patterns + high-entropy token detection.

Rule-based (CPU). Returns matches with a category and the matched span/value.
Does not emit the raw value to logs; callers receive a structured match only
for redaction, with the raw value handled inside the Redactor (which never
logs it).
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
    """Return list of matches: {kind, value, start, end}."""
    matches = []
    for label, regex, group in PATTERNS:
        for m in regex.finditer(text):
            val = m.group(group) if group else m.group(0)
            matches.append({"kind": label, "value": val, "start": m.start(group or 0), "end": m.end(group or 0)})
    # high-entropy token detection (deduplicated; never overlaps a rule match)
    seen_spans = [(mm["start"], mm["end"]) for mm in matches]

    def _overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1]

    for tok_m in re.finditer(r"[A-Za-z0-9+/_\-]{16,}", text):
        s, e = tok_m.start(), tok_m.end()
        if any(_overlaps((s, e), (a, b)) for a, b in seen_spans):
            continue
        ent = shannon_entropy(tok_m.group())
        if ent >= 3.5 and (tok_m.group().count("-") + tok_m.group().count("_")) <= 2:
            matches.append({"kind": "high_entropy_token", "value": tok_m.group(), "start": s, "end": e})
    return matches


def scan_and_count(text: str) -> dict:
    matches = scan(text)
    types = {}
    for m in matches:
        types[m["kind"]] = types.get(m["kind"], 0) + 1
    return {"count": len(matches), "types": types}
