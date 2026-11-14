"""Frozen release-evidence bundle: checksum verification (portable line).

Verifies ``manifest.json`` checksums + required metadata fields of a frozen
bundle. Bundle construction is not part of this repository.
"""
from .bundle import (BUNDLE_NAME, BUNDLE_SCHEMA_VERSION, EvidenceError,
                     verify_bundle)

__all__ = ["BUNDLE_NAME", "BUNDLE_SCHEMA_VERSION", "EvidenceError",
           "verify_bundle"]
