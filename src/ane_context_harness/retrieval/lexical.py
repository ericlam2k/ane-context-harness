"""BM25 lexical retrieval (deterministic, CPU).

Operates over in-memory RepositoryChunk objects. No embeddings, no ML.
"""
from __future__ import annotations

import math
import re

_K1 = 1.2
_B = 0.75


def tokenize_query(query: str) -> list:
    """Query terms, split/folded identically to indexing (lex_terms)."""
    from ..indexing.chunking import split_identifier, _fold_plural
    out = []
    for tok in re.findall(r"[A-Za-z0-9_]+", query):
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


class BM25:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.doc_len = [len(c.lexical_terms) for c in chunks]
        self.avgdl = sum(self.doc_len) / max(1, len(chunks))
        self.doc_count = max(1, len(chunks))
        self.tf = []  # tf per doc per term -> list of dict
        self.df = {}
        self._index()

    def _index(self):
        for c in self.chunks:
            tf = {}
            for t in c.lexical_terms:
                tf[t] = tf.get(t, 0) + 1
            self.tf.append(tf)
            for t in set(tf.keys()):
                self.df[t] = self.df.get(t, 0) + 1

    def idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.doc_count - n + 0.5) / max(0.5, n + 0.5))

    def score(self, query: str, doc_idx: int) -> float:
        terms = tokenize_query(query)
        if not terms:
            return 0.0
        score = 0.0
        tf = self.tf[doc_idx]
        dl = max(1, self.doc_len[doc_idx])
        norm = 1 - self._B + self._B * dl / max(1, self.avgdl)
        for t in terms:
            f = tf.get(t, 0)
            if f == 0:
                continue
            idf = self.idf(t)
            score += idf * (f * (self._K1 + 1)) / (f + self._K1 * norm)
        return score

    _K1 = _K1
    _B = _B

    def scores(self, query: str) -> list:
        """Return list of (doc_idx, score) sorted desc."""
        rows = [(i, self.score(query, i)) for i in range(len(self.chunks))]
        rows.sort(key=lambda x: (-x[1], x[0]))
        return rows


def lexical_scores(bm25: BM25, query: str) -> list:
    """Normalized 0..1 lexical score per chunk aligned with bm25.chunks."""
    raw = [bm25.score(query, i) for i in range(len(bm25.chunks))]
    top = max(raw) if raw else 0.0
    if top <= 0:
        return [0.0] * len(raw)
    return [r / top for r in raw]
