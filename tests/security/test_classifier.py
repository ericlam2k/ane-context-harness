"""Unit tests for the Phase 2 secret classification model."""
from __future__ import annotations

from src.ane_context_harness.privacy.classifier import SecretClassifier, train_and_save

AKIA = "AKIAIOSFODNN7EXAMPLE"


def _clf():
    return SecretClassifier()


def test_model_trains_and_is_available():
    clf = _clf()
    assert clf.available
    assert clf.model_version == "phase2-logreg-v1"
    assert clf.backend == "cpu_deterministic"


def test_classifies_known_secret_kinds():
    clf = _clf()
    cases = {
        AKIA: "aws_access_key",
        "ghp_AbcDefGhiJklMnoPqrStaBcd32": "api_key",
        "sk-proj-1234567890abcdefghijklmn": "api_key",
        "postgres://user:secretpw@db.internal:5432/synth": "database_url",
        "ops@example.com": "email",
    }
    for value, kind in cases.items():
        res = clf.classify(value)
        assert res["is_secret"] is True
        assert res["kind"] == kind
        assert res["confidence"] >= 0.9


def test_no_false_positives_on_benign_code():
    clf = _clf()
    benign = [
        "calculate_discount", "calculate_total_with_discount", "format_currency",
        "apply_coupon", "coupon_code", "src/discount.py", "tests/test_discount.py",
        "runtime.secrets.json", "db.internal", "my_function_name",
        "camelCaseVar", "snake_case_thing", "config", "settings.json",
        "v1.2.3", "__init__.py", "password", "user", "1234567890",
    ]
    for value in benign:
        res = clf.classify(value)
        # High-precision gate used by redaction: never flag benign as secret.
        assert not (res["is_secret"] and res["confidence"] >= 0.9), (value, res)


def test_scan_augments_rule_matches_with_ml():
    clf = _clf()
    # An opaque high-entropy bearer token that the rule scanner cannot pattern-match.
    text = "token = ya29.a0AfH6SMBx9_tokenstufflongenough_zzz"
    rule_matches = []
    from src.ane_context_harness.privacy.secrets import scan as _scan
    rule_matches = _scan(text)
    ml_matches = [m for m in clf.scan(text) if m not in rule_matches]
    # Either the rule engine or the model must flag it.
    kinds = {m["kind"] for m in rule_matches + ml_matches}
    assert kinds & {"bearer_token", "api_token", "high_entropy_token", "api_key"}


def test_scan_does_not_duplicate_rule_matches():
    clf = _clf()
    text = f"api_key = {AKIA}"
    matches = clf.scan(text)
    # AKIA covered by the rule match; model must not add an overlapping duplicate.
    assert sum(1 for m in matches if m["value"] == AKIA) <= 1


def test_artifact_persists_and_reloads(tmp_path):
    path = str(tmp_path / "sc.model")
    meta = train_and_save(path)
    assert meta["model_version"] == "phase2-logreg-v1"
    clf = SecretClassifier(model_path=path)
    assert clf.available
    assert clf.model_version == "phase2-logreg-v1"
    res = clf.classify(AKIA)
    assert res["kind"] == "aws_access_key"
