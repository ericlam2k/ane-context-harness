"""Unit + integration tests for stable redaction and fail-closed behavior."""
from __future__ import annotations

from src.ane_context_harness.privacy.redaction import Redactor

AWS_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"


def test_redact_replaces_with_stable_placeholder():
    rd = Redactor(redact_secrets=True)
    out = rd.redact(f"api_key = {AWS_EXAMPLE}")
    assert AWS_EXAMPLE not in out
    assert "<REDACTED_API_KEY_1>" in out
    assert rd.count == 1


def test_redact_stable_within_request():
    rd = Redactor(redact_secrets=True)
    out1 = rd.redact(f"k1={AWS_EXAMPLE}")
    out2 = rd.redact(f"k2={AWS_EXAMPLE}")
    assert "<REDACTED_API_KEY_1>" in out1
    assert "<REDACTED_API_KEY_1>" in out2
    assert rd.count == 1  # not double-counted


def test_redact_increments_per_type():
    rd = Redactor(redact_secrets=True)
    rd.redact(f"a={AWS_EXAMPLE}")
    rd.redact("contact ops@example.com")
    s = rd.summary()
    assert s["count"] == 2
    assert "email" in s["types"]


def test_redact_disabled_leaves_content():
    rd = Redactor(redact_secrets=False)
    out = rd.redact(f"api_key={AWS_EXAMPLE}")
    assert out == f"api_key={AWS_EXAMPLE}"
    assert rd.count == 0


def test_redact_no_crash_on_clean_text():
    rd = Redactor(redact_secrets=True)
    assert rd.redact("plain code without secrets") == "plain code without secrets"


def test_redacted_count_matches():
    rd = Redactor(redact_secrets=True)
    text = f"{AWS_EXAMPLE} and ops@example.com"
    out = rd.redact(text)
    assert AWS_EXAMPLE not in out
    assert "ops@example.com" not in out
    assert rd.count >= 2


def test_pipeline_redacts_selected_evidence(tmp_path, py_repo):
    from src.ane_context_harness.config import build_config
    from src.ane_context_harness.pipeline import Pipeline
    from src.ane_context_harness.schemas import SelectRequest
    cfg = build_config({
        "index": {"storage_path": str(tmp_path / "store")},
        "privacy": {"redact_secrets": True, "fail_closed_for_cloud": False,
                    "never_read": ["**/.env*", "**/.aws/**", "**/.ssh/**", "**/*.pem"]},
    })
    pipe = Pipeline(cfg)
    pipe.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="inspect runtime configuration",
        token_budget=100000,
        explicit_paths=["config/runtime.secrets.json"],
        options={"redact_secrets": True, "use_ml_reranker": False},
    )
    pkg = pipe.select_context(req)
    joined = "".join(e["content"] for e in pkg.evidence) + pkg.markdown
    assert AWS_EXAMPLE not in joined
    assert "secretpw@db.internal" not in joined
    assert pkg.redaction_summary["count"] >= 1
    assert pkg.execution["redaction"] == "rule_based_cpu"


def test_fail_closed_clears_evidence_if_leak(tmp_path, py_repo):
    from src.ane_context_harness.config import build_config
    from src.ane_context_harness.pipeline import Pipeline
    from src.ane_context_harness.schemas import SelectRequest
    cfg = build_config({
        "index": {"storage_path": str(tmp_path / "store")},
        "privacy": {"redact_secrets": True, "fail_closed_for_cloud": True,
                    "never_read": ["**/.env*", "**/.aws/**"]},
    })
    pipe = Pipeline(cfg)
    pipe.register_repository(py_repo, "synthetic_py_project", True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="inspect runtime configuration",
        token_budget=100000,
        explicit_paths=["config/runtime.secrets.json"],
        options={"redact_secrets": True},
    )
    pkg = pipe.select_context(req)
    if pkg.execution.get("redaction_failed"):
        assert pkg.evidence == []
    else:
        joined = "".join(e["content"] for e in pkg.evidence)
        assert AWS_EXAMPLE not in joined


def test_fail_closed_clears_evidence_when_secret_persists(tmp_path, py_repo, monkeypatch):
    """Simulate redaction missing a secret under fail_closed: evidence cleared."""
    import src.ane_context_harness.pipeline as P
    from src.ane_context_harness.config import build_config
    from src.ane_context_harness.pipeline import Pipeline
    from src.ane_context_harness.schemas import SelectRequest
    cfg = build_config({
        "index": {"storage_path": str(tmp_path / "store")},
        "privacy": {"redact_secrets": True, "fail_closed_for_cloud": True,
                    "never_read": ["**/.env*", "**/.aws/**"]},
    })
    pipe = Pipeline(cfg)
    pipe.register_repository(py_repo, "synthetic_py_project", True)
    # simulate an undetected secret remaining after redaction
    monkeypatch.setattr(P, "_any_secret_leak", lambda evidence: True)
    req = SelectRequest(
        repository_id="synthetic_py_project",
        task="inspect runtime configuration",
        token_budget=100000,
        explicit_paths=["config/runtime.secrets.json"],
        options={"redact_secrets": True},
    )
    pkg = pipe.select_context(req)
    assert pkg.execution.get("redaction_failed") is True
    assert pkg.evidence == []
    assert pkg.markdown == ""
