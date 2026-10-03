"""Capability-profile schema and derivation from measurements.

Profiles are derived from measurements, never from chip names. Phase 1 has no
qualified Core ML backend, so the default profile is DETERMINISTIC_ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import BehavioralProfile


@dataclass
class CapabilityProfile:
    profile_version: int
    machine_id: str
    hardware: dict
    software: dict
    devices: dict
    behavioral_profile: str
    features: dict
    calibration_fingerprint: str

    def to_dict(self) -> dict:
        return {
            "profile_version": self.profile_version,
            "machine_id": self.machine_id,
            "hardware": self.hardware,
            "software": self.software,
            "devices": self.devices,
            "behavioral_profile": self.behavioral_profile,
            "features": self.features,
            "calibration_fingerprint": self.calibration_fingerprint,
        }


def derive_profile(discovery: dict, measurements: dict | None = None) -> CapabilityProfile:
    """Derive a behavioral profile from discovery + optional measurements.

    Portable line: measurements never enable ML backends; the profile is
    always deterministic-only.
    """
    measurements = measurements or {}
    machine_id = discovery.get("machine_id", "")
    devices = discovery.get("devices", {})
    hw = discovery.get("hardware", {})
    sw = discovery.get("software", {})

    features = {
        "reranker": _feature_state(measurements.get("reranker", {})),
        "embedding": _feature_state(measurements.get("embedding", {})),
        "secret_classifier": _feature_state(measurements.get("secret_classifier", {})),
    }

    # Portable line: deterministic CPU backend only (always available).
    behavioral = BehavioralProfile.DETERMINISTIC_ONLY

    fp = (
        f"{machine_id}-{sw.get('macos_version', 'na')}-"
        f"{sw.get('python_version', 'na')}-phase01"
    )

    return CapabilityProfile(
        profile_version=1,
        machine_id=machine_id,
        hardware=hw,
        software=sw,
        devices=devices,
        behavioral_profile=behavioral.value,
        features=features,
        calibration_fingerprint=fp,
    )


def _feature_state(meas: dict) -> dict:
    """Compute a feature's final state.

    Portable line: deterministic-only, always. Measurement-gated ML
    backends live in the private distribution.
    """
    return {
        "enabled": True,
        "backend": "cpu_deterministic",
        "reason": "deterministic_only_portable_line",
    }
