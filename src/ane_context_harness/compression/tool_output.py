"""FR-7 tool-output compression for terminal, build, lint, and test output.

Deterministic and dependency-free. Preserves the command name, exit status,
error and warning messages, stack traces near failures, referenced paths and
line numbers, test names and assertions, and a configurable amount of
surrounding context. Removes or collapses repeated progress output, duplicate
stack frames, successful test listings when not needed, repeated warnings, and
long dependency-installation logs.

The original output is never returned: it is represented only by a SHA-256
digest plus an optional caller-supplied local reference.
"""
from __future__ import annotations

import hashlib
import re

from ..tokens import estimate

ALLOWED_KINDS = ("terminal", "build", "lint", "test")

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

_SUMMARY = re.compile(
    r"^[=\-\s#]*\d+\s+(passed|failed|error|errors|warning|warnings|skipped|collected)\b"
    r"|^\s*Tests?:\s*\d+\s+(passed|failed|errors?)\b"
    r"|^\s*\d+\s+.*\bin\s+\d+(?:\.\d+)?s\s*$"
    r"|^\s*OK\s*$"
    r"|BUILD SUCCESSFUL|Build succeeded|Finished .* in \d|Tests passed:",
    re.IGNORECASE,
)
_TEST_FAIL = re.compile(
    r"^(?:FAILED|ERROR)\s+\S+::"
    r"|\.\.\.\s*(?:FAIL|ERROR)\b"
    r"|^(?:FAIL|ERROR):\s+\S+"
    r"|(?:^|\s)FAIL:\s+\S+",
)
_TEST_OK = re.compile(r"\.\.\.\s*ok\s*$|\bPASSED\b", re.IGNORECASE)
_FRAME = re.compile(
    r'^\s*File "[^"]+", line \d+'
    r"|^\s*at [\w.$<>~]+ \(.*:\d+:\d+\)"
    r"|^\s*at [\w.$<>~]+ \(.*:\d+\)"
    r"|^\s*-->\s+\S+:\d+:\d+"
    r"|^\s*at\s+\S+:\d+:\d+"
)
_ERROR = re.compile(
    r"^\s*(?:ERROR|FATAL|CRITICAL|error|Error)(?:\[[^\]]*\])?:"
    r"|^\s*E\s+\S"
    r"|^\s*Traceback \(most recent call last\):"
    r"|^\s*(?:\w+\.)?\w*(?:Error|Exception|Failure):"
    r"|:\s*(?:\w+\.)?\w*(?:Error|Exception)\s*$"
    r"|Exception in thread"
    r"|\bERROR\b|\bFATAL\b"
)
_WARNING = re.compile(
    r"^\s*(?:npm\s+)?(?:WARNING|WARN|Warning|warning)\b[:\s]"
    r"|\bWARN(?:ING)?\b"
)
_PROGRESS = re.compile(
    r"^[\s.]*[.FEsx]{4,}\s*$"
    r"|\d{1,3}%\s*[|[#>]"
    r"|\d{1,3}%\s*$"
    r"|\d+(?:\.\d+)?(?:it|s|examples?)/s\]"
    r"|^\s*[\[\(].*[|/#].*\]\s*$"
)
_INSTALL = re.compile(
    r"Requirement already satisfied|Downloading \S+-\d|Using cached "
    r"|Installing collected packages|Successfully installed|Uninstalling "
    r"|Attempting uninstall|Running setup\.py|Building wheel for|Installing backend"
    r"|^\s*Collecting \S+|^\s*Installing collected"
    r"|added \d+ packages|audited \d+ packages"
    r"|^\s*(?:Compiling|Downloaded|Downloading)\s+\S+\s+v?\d"
    r"|Downloaded crates|Updating crates|Locking \d+ packages"
    r"|^\s*(?:Compiling|Fresh)\s",
    re.IGNORECASE,
)

_BLANK, _PLAIN, _ERROR_R, _WARNING_R, _FRAME_R = "blank", "plain", "error", "warning", "frame"
_SUMMARY_R, _TEST_OK_R, _TEST_FAIL_R, _PROGRESS_R, _INSTALL_R = (
    "summary", "test_ok", "test_fail", "progress", "install")
_MARKER = "marker"

_KEEP_ALWAYS = {_ERROR_R, _TEST_FAIL_R, _SUMMARY_R, _WARNING_R}


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _classify(line: str) -> str:
    if not line.strip():
        return _BLANK
    if _SUMMARY.match(line):
        return _SUMMARY_R
    if _TEST_FAIL.search(line):
        return _TEST_FAIL_R
    if _TEST_OK.search(line):
        return _TEST_OK_R
    if _PROGRESS.search(line):
        return _PROGRESS_R
    if _INSTALL.search(line):
        return _INSTALL_R
    if _FRAME.match(line):
        return _FRAME_R
    if _ERROR.search(line):
        return _ERROR_R
    if _WARNING.search(line):
        return _WARNING_R
    return _PLAIN


def _norm(line: str) -> str:
    return " ".join(line.split())


def _collapse_runs(lines, roles, pattern_role, marker_fmt, removed_key, removed):
    """Replace each contiguous run of ``pattern_role`` lines with one marker."""
    out_l, out_r, out_orig = [], [], []
    i, n = 0, len(lines)
    while i < n:
        if roles[i] == pattern_role:
            j = i
            while j < n and roles[j] == pattern_role:
                j += 1
            removed[removed_key] += j - i
            out_l.append(marker_fmt.format(n=j - i))
            out_r.append(_MARKER)
            out_orig.append(i)
            i = j
        else:
            out_l.append(lines[i]); out_r.append(roles[i]); out_orig.append(i)
            i += 1
    return out_l, out_r, out_orig


def _dedupe(lines, roles, orig, role, removed_key, removed, normalize=None):
    seen = set()
    keep = []
    for idx in range(len(lines)):
        if roles[idx] != role:
            keep.append(idx)
            continue
        key = (normalize or _norm)(lines[idx])
        if key in seen:
            removed[removed_key] += 1
        else:
            seen.add(key)
            keep.append(idx)
    return [lines[i] for i in keep], [roles[i] for i in keep], [orig[i] for i in keep]


def _failure_windows(lines, roles, context):
    """Indices kept around errors/failures, extending through tracebacks."""
    windows = set()
    m = len(lines)
    for i, r in enumerate(roles):
        if r not in (_ERROR_R, _TEST_FAIL_R):
            continue
        lo, hi = max(0, i - context), min(m, i + context + 1)
        windows.update(range(lo, hi))
        j, last = i, r
        while j + 1 < m:
            nxt_r, nxt = roles[j + 1], lines[j + 1]
            if nxt_r == _FRAME_R:
                j += 1
            elif last == _FRAME_R and nxt_r in (_PLAIN, _ERROR_R) and nxt.strip():
                j += 1
            else:
                break
            windows.add(j)
            last = roles[j]
    return windows


def _tier(role):
    if role in (_MARKER, _PLAIN, _BLANK):
        return 2
    if role in (_FRAME_R, _WARNING_R):
        return 1
    return 0


def _trim_to_budget(out_lines, out_roles, header_n, budget):
    """Drop lowest-priority lines (never the header) until within budget."""
    trimmed = 0
    for tier in (2, 1, 0):
        if estimate("\n".join(out_lines)) <= budget:
            break
        i = len(out_lines) - 1
        while i >= header_n and estimate("\n".join(out_lines)) > budget:
            if _tier(out_roles[i]) == tier:
                out_lines.pop(i); out_roles.pop(i); trimmed += 1
            i -= 1
    return trimmed


def compress_tool_output(kind: str, command: str, exit_code: int, content: str,
                         token_budget: int = 2000, context_lines: int = 3,
                         reference: str | None = None) -> dict:
    """Compress one tool invocation's output (FR-7). Returns a JSON-safe dict.

    Never includes the original output; only its SHA-256 and an optional
    local ``reference`` represent it.
    """
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"kind must be one of {ALLOWED_KINDS}, got {kind!r}")
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    if context_lines < 0:
        raise ValueError("context_lines must be >= 0")

    original = content if isinstance(content, str) else str(content)
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    original_tokens = estimate(original)

    lines = [_strip_ansi(l).split("\r")[-1].rstrip() for l in original.splitlines()]
    roles = [_classify(l) for l in lines]
    removed = {"progress": 0, "install": 0, "duplicate_frames": 0,
               "repeated_warnings": 0, "successful_tests": 0, "trimmed_to_budget": 0}

    lines, roles, orig = lines, roles, list(range(len(lines)))
    lines, roles, orig = _collapse_runs(
        lines, roles, _INSTALL_R, "[install] {n} dependency-install lines collapsed",
        "install", removed)
    lines, roles, orig = _collapse_runs(
        lines, roles, _PROGRESS_R, "[progress] {n} progress lines collapsed",
        "progress", removed)
    lines, roles, orig = _dedupe(
        lines, roles, orig, _FRAME_R, "duplicate_frames", removed)
    lines, roles, orig = _dedupe(
        lines, roles, orig, _WARNING_R, "repeated_warnings", removed,
        normalize=lambda l: re.sub(r"\d+", "#", _norm(l)))

    if kind == "test":
        keep = [i for i in range(len(lines)) if roles[i] != _TEST_OK_R]
        removed["successful_tests"] = len(lines) - len(keep)
        lines = [lines[i] for i in keep]
        roles = [roles[i] for i in keep]

    windowed = kind in ("test", "build")
    if windowed:
        windows = _failure_windows(lines, roles, context_lines)
        keep = [i for i in range(len(lines))
                if roles[i] in _KEEP_ALWAYS or roles[i] != _MARKER and i in windows]
        lines = [lines[i] for i in keep]
        roles = [roles[i] for i in keep]

    if not windowed:
        lines, roles = _collapse_blank_runs(lines, roles)

    kept = {"errors": sum(1 for r in roles if r == _ERROR_R),
            "failed_tests": sum(1 for r in roles if r == _TEST_FAIL_R),
            "warnings": sum(1 for r in roles if r == _WARNING_R),
            "stack_frames": sum(1 for r in roles if r == _FRAME_R)}

    def _count(n, singular, plural):
        return f"{n} {singular if n == 1 else plural}"

    summary_parts = [_count(kept["errors"], "error", "errors"),
                     _count(kept["failed_tests"], "failed test", "failed tests"),
                     _count(kept["warnings"], "warning", "warnings")] if any(
        kept[k] for k in ("errors", "failed_tests", "warnings")) else []
    collapsed = [_count(removed["progress"], "progress line", "progress lines")
                 if removed["progress"] else "",
                 _count(removed["install"], "install line", "install lines")
                 if removed["install"] else "",
                 _count(removed["duplicate_frames"], "duplicate frame", "duplicate frames")
                 if removed["duplicate_frames"] else "",
                 _count(removed["repeated_warnings"], "repeated warning", "repeated warnings")
                 if removed["repeated_warnings"] else "",
                 _count(removed["successful_tests"], "passing test line", "passing test lines")
                 if removed["successful_tests"] else ""]
    collapsed = [c for c in collapsed if c]
    summary_line = "summary: " + (
        ("; ".join(summary_parts) if summary_parts else "no errors")
        + ("; collapsed " + ", ".join(collapsed) if collapsed else ""))

    header = [f"command: {command}", f"exit_code: {exit_code}", summary_line]
    out_lines = header + lines
    out_roles = [_SUMMARY_R] * len(header) + roles
    trimmed = _trim_to_budget(out_lines, out_roles, len(header), token_budget)
    removed["trimmed_to_budget"] = trimmed

    text = "\n".join(out_lines)
    compressed_tokens = estimate(text)
    reduction = (round((1 - compressed_tokens / original_tokens) * 100, 1)
                 if original_tokens else 0.0)
    return {
        "kind": kind,
        "command": command,
        "exit_code": exit_code,
        "content_sha256": f"sha256:{digest}",
        "reference": reference,
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "reduction_percent": reduction,
        "within_budget": compressed_tokens <= token_budget,
        "compressed": text,
        "kept": kept,
        "removed": removed,
    }


def _collapse_blank_runs(lines, roles):
    out_l, out_r = [], []
    blanks = 0
    for l, r in zip(lines, roles):
        if r == _BLANK:
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        out_l.append(l); out_r.append(r)
    return out_l, out_r
