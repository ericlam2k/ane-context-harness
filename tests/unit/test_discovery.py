"""Tests for runtime discovery (generation-neutral, conservative)."""
from __future__ import annotations

from src.ane_context_harness.platform.discovery import discover, machine_id


def test_discover_returns_expected_keys():
    d = discover()
    assert "machine_id" in d
    assert "hardware" in d
    assert "software" in d
    assert "devices" in d
    assert "runtime" in d
    assert "architecture" in d["hardware"]
    assert "is_apple_silicon" in d["hardware"]


def test_discover_reports_no_accelerators():
    d = discover()
    # Portable line probes nothing: no accelerator keys at all.
    assert d["devices"] == {}


def test_machine_id_stable_and_non_secret():
    a = machine_id()
    b = machine_id()
    assert a == b
    assert len(a) >= 16
    # must not contain raw serial/hostname
    import platform
    assert platform.node() not in a


def test_compute_mode_conservative():
    d = discover()
    assert d["runtime"]["compute_mode"] == "deterministic_only"
