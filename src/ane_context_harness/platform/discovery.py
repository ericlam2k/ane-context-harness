"""Runtime hardware/software discovery (generation-neutral).

Reports only what is directly observable from the local system. Does NOT
attempt Core ML introspection without an optional coremltools import, and
never equates Apple Silicon with Neural Engine use.
"""
from __future__ import annotations

import hashlib
import platform
import re
import uuid


def _hw_info() -> dict:
    bits = platform.machine()
    is_apple_silicon = bool(re.match(r"arm64|aarch64", bits))
    return {
        "architecture": bits,
        "is_apple_silicon": is_apple_silicon,
        "processor": platform.processor() or "unknown",
    }


def _memory() -> dict:
    """Observable memory figures. Total physical memory via the macOS sysctl
    syscall (ctypes, no shell). Process peak RSS via stdlib resource. Memory
    pressure is not reliably measurable from stdlib alone -> 'unknown'."""
    total = _total_physical_memory_bytes()
    proc_rss = 0
    try:
        import resource  # type: ignore
        proc_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        proc_rss = 0
    return {
        "total_physical_memory_bytes": total,
        "process_peak_rss_bytes": proc_rss,
        "memory_pressure": "unknown",
    }


def _total_physical_memory_bytes() -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_size_t),
                                      ctypes.c_void_p, ctypes.c_size_t]
        libc.sysctlbyname.restype = ctypes.c_int
        res = ctypes.c_uint64(0)
        size = ctypes.c_size_t(ctypes.sizeof(res))
        rc = libc.sysctlbyname(b"hw.memsize", ctypes.byref(res), ctypes.byref(size), None, 0)
        if rc == 0 and res.value:
            return int(res.value)
    except Exception:
        pass
    return 0


def machine_id() -> str:
    """Stable local hash of non-sensitive hardware identifiers.

    Does not include serial number or hostname directly. Used for diagnostics
    only and to key capability profiles.
    """
    parts = [
        str(uuid.getnode()),
        platform.platform(),
        platform.machine(),
    ]
    h = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return h[:32]


def _macos() -> dict:
    if platform.system() == "Darwin":
        ver = platform.mac_ver()
        return {"macos_version": ver[0], "macos_build": ver[2]}
    return {"macos_version": None, "macos_build": None}


def _detect_coreml() -> dict:
    """Probe for Core ML availability without fabricating ANE claims.

    Returns coreml_available as a tri-state: True (optional coremltools import
    succeeds AND we are on a known Apple Silicon macOS runtime), False when
    absent, and 'unknown' otherwise. Neural Engine availability is 'unknown'
    unless an ANE-backed compute unit is observed during calibration
    (Phase 3). We never claim ANE from computeUnits=all.
    """
    try:
        import coremltools  # type: ignore
        has_coreml = True
    except Exception:
        has_coreml = False
    apple = _hw_info()["is_apple_silicon"]
    macos = platform.system() == "Darwin"
    available = has_coreml and apple and macos
    return {
        "coreml_available": available,
        "coreml_available_tri": "true" if available else ("false" if not has_coreml and not apple else "unknown"),
        "neural_engine_observed": False,  # only ever set True by measured calibration (Phase 3)
        "neural_engine_observed_tri": "unknown",
    }


def discover() -> dict:
    hw = _hw_info()
    mem = _memory()
    return {
        "machine_id": machine_id(),
        "hardware": {
            "architecture": hw["architecture"],
            "is_apple_silicon": hw["is_apple_silicon"],
            "processor": hw["processor"],
            "unified_memory_bytes": mem["total_physical_memory_bytes"],
            "total_physical_memory_bytes": mem["total_physical_memory_bytes"],
            "process_peak_rss_bytes": mem["process_peak_rss_bytes"],
            "memory_pressure": mem["memory_pressure"],
        },
        "software": {
            "platform": platform.platform(),
            **_macos(),
            "python_version": platform.python_version(),
        },
        "devices": _detect_coreml(),
        "runtime": {
            "compute_mode": "deterministic_only",  # no qualified Core ML backend in Phase 1
        },
    }
