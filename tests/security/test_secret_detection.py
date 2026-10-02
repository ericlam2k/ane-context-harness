"""Unit tests for secret detection (rule-based + entropy)."""
from __future__ import annotations

from src.ane_context_harness.privacy.secrets import scan, scan_and_count, shannon_entropy

AWS_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"


def test_detects_aws_access_key():
    matches = scan(f"key = {AWS_EXAMPLE}")
    kinds = [m["kind"] for m in matches]
    assert "aws_access_key" in kinds


def test_detects_api_key_assignment():
    matches = scan("api_key: 'ghp_testtokenvalue123'")
    assert any(m["kind"] == "api_key" for m in matches)


def test_detects_bearer_token():
    matches = scan("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig")
    assert any(m["kind"] == "bearer_token" for m in matches)


def test_detects_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOw...\n-----END RSA PRIVATE KEY-----\n"
    matches = scan(text)
    assert any(m["kind"] == "private_key" for m in matches)


def test_detects_database_url_with_credentials():
    text = "postgres://user:password@db.internal:5432/synth"
    matches = scan(text)
    assert any(m["kind"] == "database_url" for m in matches)


def test_detects_email():
    matches = scan("contact ops@example.com please")
    assert any(m["kind"] == "email" for m in matches)


def test_counts_and_types():
    res = scan_and_count(f"api_key={AWS_EXAMPLE}\nmail ops@example.com")
    assert res["count"] >= 2
    assert "aws_access_key" in res["types"] or "api_key" in res["types"]
    assert "email" in res["types"]


def test_entropy_function_bounded():
    assert 0.0 <= shannon_entropy("aaaa") <= 2.0
    assert shannon_entropy("AKIAIOSFODNN7EXAMPLE") > 3.0


def test_no_false_positive_on_normal_code():
    text = "def calculate_discount(price, rate):\n    return price - price * rate\n"
    assert scan(text) == []


def test_scan_does_not_raise_on_long_string():
    assert scan("a" * 100) == []
