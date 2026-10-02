"""Pure-stdlib BERT WordPiece tokenizer for the Core ML reranker runtime.

Runtime is **PyTorch/transformers-free**: this module tokenizes
(query, chunk) pairs into fixed-length ``input_ids``, ``attention_mask`` and
``token_type_ids`` tensors (lists) whose layout matches the conversion
contract in ``coreml.convert._make_traced``.

The vocab is bundled alongside the compiled ``.mlmodelc`` at build time
(``tokenizer/vocab.txt``). The algorithm mirrors Hugging Face's
``BertTokenizerFast`` basic + WordPiece for an uncased BERT tokenizer:
lower-case, strip accents, punctuation-split, whitespace-split, then greedy
longest-match WordPiece with ``##`` continuation prefixes.
"""
from __future__ import annotations

import json
import os
import unicodedata

_PAD_ID = 0
_CLS_ID = 101
_SEP_ID = 102
_UNK_ID = 100
_MAX_INPUT_CHARS_PER_WORD = 100  # HF WordpieceTokenizer default
_MASK_ID = 103

_SPECIAL_TOKENS = {"[PAD]": _PAD_ID, "[UNK]": _UNK_ID, "[CLS]": _CLS_ID,
                   "[SEP]": _SEP_ID, "[MASK]": _MASK_ID}


def _is_punctuation(ch: str) -> bool:
    return bool((33 <= ord(ch) <= 47) or (58 <= ord(ch) <= 64)
                or (91 <= ord(ch) <= 96) or (123 <= ord(ch) <= 126)) or unicodedata.category(ch).startswith("P")


def _is_whitespace(ch: str) -> bool:
    return ch in " \t\n\r\f" or unicodedata.category(ch) == "Zs"


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


class TokenizerBundle:
    """Loads a bundled vocab and encodes (query, passage) pairs.

    Parameters
    ----------
    vocab_path:
        Path to ``vocab.txt`` (one token per line, line number = id).
    seq_len:
        Fixed sequence length; encoded pair is padded/truncated to this length.
    """
    def __init__(self, vocab_path: str, seq_len: int = 256):
        self.seq_len = seq_len
        self.vocab: dict[str, int] = {}
        self._load_vocab(vocab_path)

    def _load_vocab(self, vocab_path: str) -> None:
        if not vocab_path or not os.path.exists(vocab_path):
            raise FileNotFoundError(f"vocab.txt not found at {vocab_path}")
        with open(vocab_path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh):
                tok = line.rstrip("\n").rstrip("\r")
                if tok == "":
                    continue
                # keep last id for duplicate entries (matches HF behavior ordering)
                self.vocab[tok] = lineno

    @property
    def pad_id(self) -> int:
        return self.vocab.get("[PAD]", _PAD_ID)

    @property
    def cls_id(self) -> int:
        return self.vocab.get("[CLS]", _CLS_ID)

    @property
    def sep_id(self) -> int:
        return self.vocab.get("[SEP]", _SEP_ID)

    @property
    def unk_id(self) -> int:
        return self.vocab.get("[UNK]", _UNK_ID)

    def _basic_tokenize(self, text: str) -> list:
        tokens = []
        cur = []
        for ch in text:
            if _is_whitespace(ch):
                if cur:
                    tokens.append("".join(cur))
                    cur = []
            elif _is_punctuation(ch):
                if cur:
                    tokens.append("".join(cur))
                    cur = []
                tokens.append(ch)
            else:
                cur.append(ch)
        if cur:
            tokens.append("".join(cur))
        return tokens

    def _wordpiece(self, token: str) -> list:
        if not token:
            return []
        # HF WordpieceTokenizer: words longer than max_input_chars_per_word
        # (default 100) are never matched and map straight to [UNK].
        if len(token) > _MAX_INPUT_CHARS_PER_WORD:
            return ["[UNK]"]
        if token in self.vocab:
            return [token]
        # greedy longest-match
        pieces = []
        start = 0
        n = len(token)
        while start < n:
            end = n
            best = None
            while start < end:
                sub = token[start:end]
                if start > 0:
                    sub = "##" + sub
                if sub in self.vocab:
                    best = sub
                    break
                end -= 1
            if best is None:
                # untokenizable word -> UNK
                return ["[UNK]"]
            pieces.append(best)
            start = end
        return pieces

    def _encode_tokens(self, tokens: list) -> list:
        ids = []
        for tok in tokens:
            if tok in self.vocab:
                ids.append(tok)
            else:
                for piece in self._wordpiece(tok):
                    ids.append(piece)
        # flatten to ids (string tokens -> vocab id; [UNK] resolves to unk_id)
        out = []
        for t in ids:
            out.append(self.vocab.get(t, self.unk_id))
        return out

    def encode_pair(self, query: str, passage: str) -> tuple:
        """Return (input_ids, attention_mask, token_type_ids) padded to seq_len.

        Mirrors HuggingFace ``BertTokenizerFast.__call__`` with
        ``truncation=True, padding='max_length'``: special tokens are added and a
        ``longest_first`` right-side truncation is applied to the *raw* token-id
        lists before re-inserting [CLS]/[SEP].
        """
        query = _strip_accents(query.lower())
        passage = _strip_accents(passage.lower())
        q_ids = self._encode_tokens(self._basic_tokenize(query))
        p_ids = self._encode_tokens(self._basic_tokenize(passage))

        len_ids = len(q_ids)
        len_pair_ids = len(p_ids)
        # 3 special tokens: [CLS] (q) [SEP] (p) [SEP]
        total_len = len_ids + len_pair_ids + 3
        if total_len > self.seq_len:
            num_remove = total_len - self.seq_len
            first_remove = min(abs(len_pair_ids - len_ids), num_remove)
            second_remove = num_remove - first_remove
            if len_ids > len_pair_ids:
                q_remove = first_remove + second_remove // 2
                p_remove = second_remove - second_remove // 2
            else:
                q_remove = second_remove // 2
                p_remove = first_remove + second_remove - second_remove // 2
            q_ids = q_ids[: max(0, len_ids - q_remove)]
            p_ids = p_ids[: max(0, len_pair_ids - p_remove)]

        # Add special tokens: [CLS] q [SEP] p [SEP]
        ids = [self.cls_id] + q_ids + [self.sep_id] + p_ids + [self.sep_id]
        ids = ids[: self.seq_len]
        # BERT token_type_ids: 0 for CLS + first seq + first SEP; 1 for 2nd seq + trailing SEP.
        sep1 = ids.index(self.sep_id) if self.sep_id in ids else len(ids) - 1
        attn_len = len(ids)
        input_ids = ids + [self.pad_id] * (self.seq_len - attn_len)
        attention_mask = [1] * attn_len + [0] * (self.seq_len - attn_len)
        token_type_ids = [0] * (sep1 + 1) + [1] * (attn_len - sep1 - 1)
        token_type_ids += [0] * (self.seq_len - attn_len)
        return input_ids, attention_mask, token_type_ids

    def from_config(self, config_path: str) -> "TokenizerBundle":
        """Re-bind from a tokenizer_config.json (no-op for vocab; sets seq_len)."""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            self.seq_len = int(cfg.get("max_seq_len", self.seq_len))
        return self


def load_tokenizer(vocab_path: str, config_path: str | None = None,
                   seq_len: int = 256) -> TokenizerBundle:
    tok = TokenizerBundle(vocab_path, seq_len)
    if config_path and os.path.exists(config_path):
        tok = tok.from_config(config_path)
    return tok
