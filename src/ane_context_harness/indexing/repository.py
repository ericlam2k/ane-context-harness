"""Repository registration + safe incremental indexing.

Excludes .git internals, build artifacts, binaries, and never executes shell.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from . import chunking as chunking_mod
from . import symbols as symbols_mod
from .paths import normalize_repo_path, safe_relpath


LANGUAGE_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "jsx",
    ".ts": "typescript", ".tsx": "tsx",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".m": "objective-c", ".mm": "objective-cpp",
    ".rs": "rust", ".go": "go", ".java": "java", ".rb": "ruby", ".sh": "bash",
    ".md": "markdown", ".txt": "text",
}

IGNORED_DIR_NAMES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", ".cache", "dist", "build", ".eggs",
}

IGNORED_FILE_NAMES = {".ds_store", ".localized"}


def is_ignored_dir(name: str) -> bool:
    if name == "egg-info" or name.endswith(".egg-info"):
        return True
    return name in IGNORED_DIR_NAMES


def _matches_never_read(rel: str, never_read: list) -> bool:
    rel_n = rel.replace("\\", "/")
    for pat in never_read:
        if _glob_match(rel_n, pat):
            return True
    return False


def _glob_to_regex(pat: str):
    import re
    i, n = 0, len(pat)
    out = ["^"]
    while i < n:
        c = pat[i:i + 2]
        if c == "**" and (i + 2 >= n or pat[i + 2] in "/"):
            # ** matches across path separators
            out.append(".*")
            i += 2
            if i < n and pat[i] == "/":
                i += 1
            continue
        if pat[i] == "*":
            out.append("[^/]*")
            i += 1
            continue
        if pat[i] == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(pat[i]))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def _glob_match(rel: str, pattern: str) -> bool:
    import re
    candidates = {pattern}
    if pattern.startswith("**/"):
        candidates.add(pattern[3:])  # e.g. **/.env* -> .env*
    for p in candidates:
        try:
            rx = _glob_to_regex(p)
            if rx.match(rel):
                return True
        except re.error:
            continue
    return False


def detect_language(rel: str) -> str:
    ext = Path(rel).suffix.lower()
    return LANGUAGE_BY_EXT.get(ext, "unknown")


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return True
    return False


@dataclass
class FileInfo:
    rel_path: str
    abs_path: Path
    language: str
    size_bytes: int
    content_hash: str
    mtime_ns: int
    content: str  # retained in-memory only for ranking; not persisted as source


@dataclass
class IndexPlan:
    files: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def scan_repository(repo_root: str | Path, max_file_bytes: int,
                   never_read: list | None = None) -> IndexPlan:
    root = normalize_repo_path(repo_root)
    plan = IndexPlan()
    never_read = never_read or []
    if not root.exists():
        raise FileNotFoundError(f"repository not found: {root}")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # prune ignored dirs in-place so os.walk does not descend
        dirnames[:] = [d for d in dirnames if d and not is_ignored_dir(d)]
        for fn in filenames:
            abs_path = Path(dirpath) / fn
            rel = safe_relpath(abs_path, root)
            if rel is None:
                plan.skipped.append({"path": str(abs_path), "reason": "unsafe_path"})
                continue
            if _matches_never_read(rel, never_read):
                plan.skipped.append({"path": rel, "reason": "policy_deny"})
                continue
            if fn.lower() in IGNORED_FILE_NAMES:
                plan.skipped.append({"path": rel, "reason": "hidden_system"})
                continue
            try:
                st = abs_path.stat()
            except OSError:
                plan.skipped.append({"path": rel, "reason": "stat_failed"})
                continue
            if not abs_path.is_file():
                plan.skipped.append({"path": rel, "reason": "not_regular_file"})
                continue
            if st.st_size > max_file_bytes:
                plan.skipped.append({"path": rel, "reason": "too_large"})
                continue
            try:
                raw = abs_path.read_bytes()
            except OSError:
                plan.skipped.append({"path": rel, "reason": "read_failed"})
                continue
            if _looks_binary(raw[:8192]):
                plan.skipped.append({"path": rel, "reason": "binary"})
                continue
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                plan.skipped.append({"path": rel, "reason": "not_utf8"})
                continue
            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            lang = detect_language(rel)
            plan.files.append(FileInfo(
                rel_path=rel, abs_path=abs_path, language=lang,
                size_bytes=st.st_size, content_hash=h, mtime_ns=st.st_mtime_ns,
                content=content,
            ))
    return plan


def build_chunks(repo_root: str | Path, repo_id: str, max_file_bytes: int,
                 chunk_target_tokens: int, chunk_overlap_tokens: int) -> tuple[list, IndexPlan]:
    """Scan repo and produce RepositoryChunk objects (content retained for ranking)."""
    from ..schemas import RepositoryChunk
    plan = scan_repository(repo_root, max_file_bytes)
    chunks = []
    for fi in plan.files:
        symbol_spans = symbols_mod.extract_symbols(fi.language, fi.content)
        pieces = chunking_mod.chunk_file(fi.content, chunk_target_tokens, chunk_overlap_tokens)
        for piece in pieces:
            terms = chunking_mod.lex_terms(piece.content)
            sym = _nearest_symbol(piece.start_line, symbol_spans)
            chunks.append(RepositoryChunk(
                chunk_id=_chunk_id(repo_id, fi.rel_path, piece.start_line),
                repository_id=repo_id,
                path=fi.rel_path,
                language=fi.language,
                start_line=piece.start_line,
                end_line=piece.end_line,
                symbol=sym,
                content_hash=fi.content_hash,
                estimated_tokens=piece.tokens,
                lexical_terms=tuple(terms),
                content=piece.content,
                metadata={"size_bytes": fi.size_bytes, "mtime_ns": fi.mtime_ns, "file_hash": fi.content_hash},
            ))
    return chunks, plan


def _chunk_id(repo_id: str, path: str, start_line: int) -> str:
    raw = f"{repo_id}:{path}:{start_line}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _nearest_symbol(start_line: int, symbols: list) -> str | None:
    """Return the enclosing symbol name for a line (symbols: list of (name, start, end))."""
    best = None
    for name, sline, eline in symbols:
        if sline <= start_line <= eline:
            best = name
    return best
