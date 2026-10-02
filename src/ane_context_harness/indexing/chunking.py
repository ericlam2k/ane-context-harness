"""Deterministic chunking by token target with overlap and line provenance.

Guarantees: start_line/end_line are 1-based and strictly monotonic across
chunks of the same file (no two chunks share a start_line), so chunk
identifiers keyed on (repo, path, start_line) remain unique.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import tokens as tokens_mod


@dataclass
class ChunkPiece:
    content: str
    start_line: int
    end_line: int
    tokens: int


def _split_lines(text: str):
    return text.splitlines(keepends=True)


def _tokens_to_lines(lines: list, token_budget: int) -> int:
    """Number of whole leading lines whose cumulative tokens fit in token_budget."""
    acc = 0
    count = 0
    for ln in lines:
        t = tokens_mod.count(ln)
        if acc + t > token_budget and count > 0:
            break
        acc += t
        count += 1
    return max(1, count)


def chunk_file(text: str, target_tokens: int, overlap_tokens: int,
               max_lines_per_chunk: int = 400) -> list:
    if target_tokens < 1:
        target_tokens = 1
    lines = _split_lines(text)
    n = len(lines)
    if n == 0:
        return []
    pieces = []
    # overlap in lines: convert token budget to a line count heuristic
    overlap_lines = 0
    if overlap_tokens > 0:
        # estimate lines equivalent to overlap_tokens using first line as sample
        sample_len = max(1, n)
        sample_tokens = tokens_mod.count("".join(lines[:min(5, n)])) or 1
        overlap_lines = max(1, int(overlap_tokens * (min(5, n) / sample_tokens)))
    start_idx = 0  # 0-based index into lines
    while start_idx < n:
        width = _tokens_to_lines(lines[start_idx:], target_tokens)
        width = min(width, max_lines_per_chunk, n - start_idx)
        end_idx = start_idx + width - 1
        chunk_lines = lines[start_idx:end_idx + 1]
        content = "".join(chunk_lines)
        start_line = start_idx + 1
        end_line = end_idx + 1
        pieces.append(ChunkPiece(
            content=content,
            start_line=start_line,
            end_line=end_line,
            tokens=tokens_mod.count(content),
        ))
        if end_idx + 1 >= n:
            break
        # next start with token-based overlap, always advancing past current start
        next_start = max(start_idx + 1, end_idx + 1 - overlap_lines)
        # ensure strictly greater start_line than the previous chunk
        if next_start <= start_idx:
            next_start = start_idx + 1
        start_idx = next_start
    return pieces


def split_identifier(token: str) -> list:
    """Split an identifier into subtokens on underscore/camelCase/digit bounds.

    ``calculateDiscount`` -> ``[calculate, Discount]``; ``foo_bar`` ->
    ``[foo, bar]``; plain words come back unchanged (single element).
    Case-sensitive input; callers lowercase as needed.
    """
    import re
    parts = []
    for piece in token.split("_"):
        if not piece:
            continue
        piece = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", piece)
        piece = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", piece)
        parts.extend(p for p in piece.split("_") if p)
    return parts or ([token] if token else [])


def _fold_plural(term: str) -> str | None:
    """Naive singular form for plural query/index folding (tests -> test)."""
    if len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "us")):
        return term[:-1]
    return None


def lex_terms(text: str) -> list:
    """Lexical terms for indexing: full tokens PLUS identifier subtokens.

    Indexing the full token preserves exact-match behaviour; adding subtokens
    lets word queries match camelCase/snake_case identifiers (``priceQuote``
    matches ``quote``) — required for code retrieval in TS/Go/Java style
    sources. Plural forms additionally fold to their singular so ``tests``
    matches ``test``. The query side (retrieval.lexical.tokenize_query)
    applies the identical split/fold so document/query terms stay symmetric.
    """
    import re
    out = []
    for tok in re.findall(r"[A-Za-z0-9_]+", text):
        low = tok.lower()
        out.append(low)
        singular = _fold_plural(low)
        if singular:
            out.append(singular)
        subs = split_identifier(tok)
        if len(subs) > 1:
            for s in subs:
                low_s = s.lower()
                out.append(low_s)
                sg = _fold_plural(low_s)
                if sg:
                    out.append(sg)
    return out
