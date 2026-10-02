"""Release-evidence bundle: build and verify a frozen, checksummed snapshot
of the measured evidence behind a release candidate.

The bundle contains reports, provenance fingerprints and version locks only —
never source code, repository secrets, raw credentials or benchmark content.
"""
from .bundle import (BUNDLE_NAME, BUNDLE_SCHEMA_VERSION, EvidenceError,
                     build_bundle, verify_bundle)

__all__ = ["BUNDLE_NAME", "BUNDLE_SCHEMA_VERSION", "EvidenceError",
           "build_bundle", "verify_bundle"]
