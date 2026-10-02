"""Regression: secret-detection recall over fixtures + symlink path guard.

Locks the recall improvements (signal-key redaction, URL handling) and the
traversal/symlink guard introduced in the security pass. Not a statistical
benchmark; it asserts concrete coverage over the committed sensitivity fixtures.
"""
from __future__ import annotations

import pathlib

from src.ane_context_harness.privacy.secrets import scan
from src.ane_context_harness.indexing.repository import scan_repository

FIXTURES = pathlib.Path("tests/fixtures")
SENSITIVE_NAMES = {".env", ".EnvLocal", "secrets.json", "runtime.secrets.json"}


def _sensitive_files():
    out = []
    for f in FIXTURES.rglob("*"):
        if f.is_file() and f.name in SENSITIVE_NAMES:
            out.append(f)
    return out


def test_every_committed_secret_file_is_detected():
    files = _sensitive_files()
    assert files, "no sensitive fixtures found"
    for f in files:
        count = len(scan(f.read_text()))
        assert count >= 1, f"{f.relative_to(FIXTURES)} has no detected secrets"


def test_previously_bypassed_secrets_are_now_flagged():
    samples = [
        "STOREFRONT_BENCH_API_KEY=hard_fixture_example_value_not_real",
        '"signing_secret": "whsec_example_not_a_real_secret"',
        "SECRET_TOKEN=ts_local_secret_value_12345",
    ]
    for s in samples:
        assert scan(s), f"missed: {s}"


def test_url_credentials_still_detected_as_database_url():
    matches = scan("postgres://user:password@db.internal:5432/synth")
    assert any(m["kind"] == "database_url" for m in matches)


def test_no_false_positives_on_benign_code():
    for code in [
        "def calculate_discount(price, rate):",
        "return price - price * rate",
        "const config = { a: 1 }",
    ]:
        assert scan(code) == [], f"false positive on: {code}"


def test_symlink_escape_is_rejected_by_indexing():
    # synthetic_hard_project contains `secret_link -> /etc/passwd` (absolute escape).
    plan = scan_repository(
        FIXTURES / "synthetic_hard_project", 1_000_000, never_read=[])
    indexed = {f.rel_path for f in plan.files}
    assert "secret_link" not in indexed
    skipped = [s for s in plan.skipped if "secret_link" in s["path"]]
    assert skipped and skipped[0]["reason"] == "unsafe_path"
