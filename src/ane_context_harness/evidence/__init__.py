"""Frozen release-evidence bundle: checksum verification (portable line).

Verifies ``manifest.json`` checksums + required metadata fields of a frozen
bundle. Bundle construction is ANE-release infrastructure and lives in the
private distribution.
"""
from .bundle import (BUNDLE_NAME, BUNDLE_SCHEMA_VERSION, EvidenceError,
                     verify_bundle)

__all__ = ["BUNDLE_NAME", "BUNDLE_SCHEMA_VERSION", "EvidenceError",
           "verify_bundle"]
