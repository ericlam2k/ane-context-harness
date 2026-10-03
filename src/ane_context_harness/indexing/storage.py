"""SQLite-backed local index storage with safe incremental updates.

Stores content hashes, sizes, file metadata, symbols, and chunk metadata.
Chunk content is stored for in-memory ranking only (never logs source text).
Path policy (traversal/symlink) already enforced by repository.scanner.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path

from .. import tokens as tokens_mod
from ..indexing.chunking import chunk_symbols, lex_terms
from ..indexing.symbols import extract_symbols


class Storage:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | os.PathLike, repo_id: str):
        self.db_path = Path(db_path).expanduser()
        self.repo_id = repo_id
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # Restrict permissions to user only (security requirement) after the DB file exists.
        try:
            self._conn.execute("SELECT 1")
            os.chmod(self.db_path, 0o600)
        except (OSError, sqlite3.Error):
            pass
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
                CREATE TABLE IF NOT EXISTS files (
                    repo_id TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    language TEXT,
                    size_bytes INTEGER,
                    content_hash TEXT NOT NULL,
                    mtime_ns INTEGER,
                    PRIMARY KEY (repo_id, rel_path)
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    repo_id TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    start_line INTEGER,
                    end_line INTEGER,
                    PRIMARY KEY (repo_id, rel_path, name)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    repo_id TEXT NOT NULL,
                    chunk_id TEXT PRIMARY KEY,
                    rel_path TEXT NOT NULL,
                    language TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    symbol TEXT,
                    content_hash TEXT NOT NULL,
                    estimated_tokens INTEGER,
                    lexical_terms TEXT,
                    content TEXT
                );
                """
            )
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)",
                    ("schema_version", str(self.SCHEMA_VERSION)),
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)",
                    ("repo_id", self.repo_id),
                )
            except sqlite3.OperationalError:
                pass

    def set_index_version(self, version: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)",
                ("index_version", version),
            )

    def index_version(self) -> str:
        with self._lock:
            row = self._conn.execute("SELECT v FROM meta WHERE k='index_version'").fetchone()
        return row["v"] if row else "0"

    def stored_file_hashes(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT rel_path, content_hash, mtime_ns FROM files WHERE repo_id=?",
                (self.repo_id,),
            ).fetchall()
        return {r["rel_path"]: (r["content_hash"], r["mtime_ns"]) for r in rows}

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def upsert_file(self, rel_path, language, size_bytes, content_hash, mtime_ns):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO files(repo_id,rel_path,language,size_bytes,content_hash,mtime_ns) "
                "VALUES (?,?,?,?,?,?)",
                (self.repo_id, rel_path, language, size_bytes, content_hash, mtime_ns),
            )

    def upsert_symbol(self, rel_path, name, start_line, end_line):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO symbols(repo_id,rel_path,name,start_line,end_line) "
                "VALUES (?,?,?,?,?)",
                (self.repo_id, rel_path, name, start_line, end_line),
            )

    def replace_chunks(self, rel_path, chunks: list):
        def g(c, k, default=None):
            return c[k] if isinstance(c, dict) else getattr(c, k, default)
        with self._lock:
            self._conn.execute("DELETE FROM chunks WHERE repo_id=? AND rel_path=?", (self.repo_id, rel_path))
            for c in chunks:
                self._conn.execute(
                    "INSERT OR REPLACE INTO chunks(repo_id,chunk_id,rel_path,language,start_line,end_line,"
                    "symbol,content_hash,estimated_tokens,lexical_terms,content) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        self.repo_id, g(c, "chunk_id"), g(c, "path"), g(c, "language"),
                        g(c, "start_line"), g(c, "end_line"),
                        g(c, "symbol"), g(c, "content_hash"), g(c, "estimated_tokens"),
                        json.dumps(list(g(c, "lexical_terms", []))), g(c, "content"),
                    ),
                )

    def incremental_rebuild(self, repo_root, max_file_bytes, chunk_target_tokens, chunk_overlap_tokens, never_read=None):
        """Rebuild only files whose hash changed; delete chunks for removed files."""
        from .repository import scan_repository, detect_language
        plan = scan_repository(repo_root, max_file_bytes, never_read or [])
        stored = self.stored_file_hashes()
        indexed = 0
        skipped = 0
        symbols_extracted = 0
        # remove chunks for files no longer present
        new_paths = {fi.rel_path for fi in plan.files}
        stale = set(stored.keys()) - new_paths
        with self._lock:
            for sp in stale:
                self._conn.execute("DELETE FROM chunks WHERE repo_id=? AND rel_path=?", (self.repo_id, sp))
                self._conn.execute("DELETE FROM files WHERE repo_id=? AND rel_path=?", (self.repo_id, sp))
                self._conn.execute("DELETE FROM symbols WHERE repo_id=? AND rel_path=?", (self.repo_id, sp))
        for fi in plan.files:
            cur = stored.get(fi.rel_path)
            if cur and cur[0] == fi.content_hash and cur[1] == fi.mtime_ns:
                skipped += 1
                continue
            indexed += 1
            self.upsert_file(fi.rel_path, fi.language, fi.size_bytes, fi.content_hash, fi.mtime_ns)
            # symbols
            spans = extract_symbols(fi.language, fi.content)
            for name, s, e in spans:
                self.upsert_symbol(fi.rel_path, name, s, e)
                symbols_extracted += 1
            # chunks (symbol-aligned greedy packing; blind windows only as fallback)
            pieces = chunk_symbols(fi.content, fi.language, chunk_target_tokens, chunk_overlap_tokens)
            chunk_objs = []
            for pc in pieces:
                chunk_objs.append({
                    "chunk_id": hashlib.sha256(f"{self.repo_id}:{fi.rel_path}:{pc.start_line}".encode()).hexdigest()[:16],
                    "path": fi.rel_path,
                    "language": fi.language,
                    "start_line": pc.start_line,
                    "end_line": pc.end_line,
                    "symbol": _nearest_symbol(pc.start_line, spans),
                    "content_hash": fi.content_hash,
                    "estimated_tokens": pc.tokens,
                    "lexical_terms": tuple(lex_terms(pc.content)),
                    "content": pc.content,
                })
            self.replace_chunks(fi.rel_path, chunk_objs)
        return {
            "files_indexed": indexed,
            "files_skipped": skipped,
            "stale_removed": len(stale),
            "symbols_extracted": symbols_extracted,
        }

    def load_chunks(self) -> list:
        """Load all chunks for this repo as dicts (content included for CPU ranking).

        Each chunk's metadata carries ``file_symbols`` (all extractable symbol
        names of its file) so file-level chunks — the norm for small files,
        which start at line 1 and therefore have ``symbol=None`` — still expose
        a symbol signal to scoring/packing.
        """
        from ..schemas import RepositoryChunk
        with self._lock:
            rows = self._conn.execute(
                "SELECT chunk_id, rel_path AS path, language, start_line, end_line, symbol, "
                "content_hash, estimated_tokens, lexical_terms, content FROM chunks WHERE repo_id=?",
                (self.repo_id,),
            ).fetchall()
            sym_rows = self._conn.execute(
                "SELECT rel_path, name FROM symbols WHERE repo_id=? ORDER BY rel_path, name",
                (self.repo_id,),
            ).fetchall()
        file_syms: dict = {}
        for sr in sym_rows:
            file_syms.setdefault(sr["rel_path"], [])
            if sr["name"] not in file_syms[sr["rel_path"]]:
                file_syms[sr["rel_path"]].append(sr["name"])
        chunks = []
        for r in rows:
            chunks.append(RepositoryChunk(
                chunk_id=r["chunk_id"],
                repository_id=self.repo_id,
                path=r["path"],
                language=r["language"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                symbol=r["symbol"],
                content_hash=r["content_hash"],
                estimated_tokens=r["estimated_tokens"],
                lexical_terms=tuple(json.loads(r["lexical_terms"])),
                content=r["content"],
                metadata={"file_symbols": file_syms.get(r["path"], [])},
            ))
        return chunks

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def _nearest_symbol(start_line, symbols):
    best = None
    for name, s, e in symbols:
        if s <= start_line <= e:
            best = name
    return best
