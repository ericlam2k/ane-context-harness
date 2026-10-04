"""Integrity validation: prove the rendered bytes kept protected meaning.

For every evidence item pinned as protected (mandatory, authority, or
explicitly requested), the item's exact content (stripped) must appear
verbatim in the rendered prompt bodies. Exactness is the whole gate: any
dropped word — including a negation, operator, or threshold — fires
``content_absent``. Each span additionally carries its polarity inventory
(negation words, comparison operators, true/false-style tokens found in
the source) so manifests and monitors can weigh high-stakes spans.

Report-only v1: a failure never blocks or retries a select (deterministic
fallback ethos — the agent's workflow must not stop). The verdict lands in
``diagnostics.integrity`` for manifests and monitors; a safer-mode retry is
explicit future work, not silent behavior.

Portable: stdlib only (hashlib, re). No model, no network.
"""
from __future__ import annotations

import hashlib
import re

PROTECTED_REASONS = frozenset({"mandatory", "authority", "explicit_path"})

# Polarity-bearing tokens whose disappearance flips meaning. Word tokens
# use boundaries (so "cannot" never counts as "not"); operators are
# literal. Presence — not pairing — is checked: a dropped sentinel is the
# failure, regardless of what replaced it.
_WORD_SENTINELS = (
    "not", "no", "never", "without", "is", "are", "true", "false",
    "enabled", "disabled", "passed", "failed", "qualified", "unqualified",
    "must", "required",
)
_WORD_RE = re.compile(r"\b(" + "|".join(_WORD_SENTINELS) + r")\b",
                      re.IGNORECASE)
# Bare > / < must not match inside >=, <=, ==, !=, or <>.
_BARE_GT_RE = re.compile(r"(?<![<>=!])>(?!=)")
_BARE_LT_RE = re.compile(r"(?<![<>=!])<(?!=)")


def _sentinels_in(text: str) -> list:
    found = [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]
    text = text or ""
    for op in (">=", "<=", "==", "!="):
        if op in text:
            found.append(op)
    if _BARE_GT_RE.search(text):
        found.append(">")
    if _BARE_LT_RE.search(text):
        found.append("<")
    return sorted(set(found))


def protected_spans(evidence: list) -> list:
    """Protected items with content checksums, in evidence order."""
    spans = []
    for ev in evidence or []:
        reasons = ev.get("selection_reasons") or []
        if PROTECTED_REASONS.intersection(reasons):
            content = ev.get("content") or ""
            spans.append({
                "path": ev.get("path"),
                "symbol": ev.get("symbol"),
                "reasons": [r for r in reasons if r in PROTECTED_REASONS],
                "sha256": hashlib.sha256(
                    content.encode("utf-8")).hexdigest(),
                "content": content,
                "polarity": _sentinels_in(content),
            })
    return spans


def verify_package(evidence: list, rendered_texts) -> dict:
    """Verify protected spans against rendered prompt bodies.

    rendered_texts: one or more rendered strings (markdown, provider
    blocks). The gate is exactness: a protected span whose bytes do not
    survive verbatim (including any dropped negation, operator, or
    threshold) is reported altered. Each span also carries its polarity
    inventory so monitors can weigh high-stakes spans.

    Returns {"ok", "checked", "altered", "spans"}.
    """
    if isinstance(rendered_texts, str):
        rendered_texts = [rendered_texts]
    bodies = [t or "" for t in rendered_texts]
    altered, spans = [], []
    for span in protected_spans(evidence):
        spans.append({k: span[k] for k in ("path", "symbol", "sha256",
                                           "polarity")})
        needle = (span["content"] or "").strip()
        if not needle or not any(needle in b for b in bodies):
            altered.append({"path": span["path"], "symbol": span["symbol"],
                            "reason": "content_absent"})
    return {"ok": not altered, "checked": len(spans), "altered": altered,
            "spans": spans}
