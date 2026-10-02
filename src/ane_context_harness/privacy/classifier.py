"""Secret classification model (Phase 2).

Pure-stdlib, deterministic, CPU-only. A small multinomial logistic-regression
classifier over character n-gram + secret-shape features, trained on synthetic
labeled spans. It augments the rule-based ``scan()`` so that high-confidence
secrets the regex set may miss (opaque bearer tokens, base64 blobs, JWTs,
high-entropy tokens written in config form) are still redacted.

The model artifact is a pickle of (classes, weights, bias, vocab, meta). Training
is deterministic (fixed seed); the artifact is trained+cached on first use if
absent.
"""
from __future__ import annotations

import math
import os
import pickle
import random
import re
from collections import Counter

from .secrets import _candidate_tokens


_CLASSES = [
    "benign", "aws_access_key", "aws_secret", "api_key", "api_token",
    "bearer_token", "private_key", "database_url", "email", "high_entropy_token",
]
_DEFAULT_THRESHOLD = 0.90
_MODEL_VERSION = "phase2-logreg-v1"


# In-process trained-model cache (training is pure-stdlib and fast enough to
# keep once per process, then reuse for every request).
_TRAINED_CACHE: dict | None = None


def _trained_once():
    global _TRAINED_CACHE
    if _TRAINED_CACHE is None:
        _TRAINED_CACHE = _train()
    return _TRAINED_CACHE


# ---------------------------------------------------------------------------
# Synthetic training data (deterministic)
# ---------------------------------------------------------------------------
_IDENTIFIERS = """
calculate_discount price rate total apply_coupon coupon_code
symbol amount inventory analytics reporting calculator
src/discount tests/test_discount __pycache__ .env config
settings.json runtime.secrets.json README.md design.md
""".split()


def _rnd_seed():
    return random.Random(20260102)


def _rand_token(rng, length, alphabet):
    return "".join(rng.choice(alphabet) for _ in range(length))


def _build_dataset(n_per_kind: int = 90):
    rng = _rnd_seed()
    data = []  # (kind, token)

    def add(kind, token):
        data.append((kind, token))

    for _ in range(n_per_kind):
        add("aws_access_key", "AKIA" + _rand_token(rng, 16, "ABCDEF0123456789"))
        add("aws_secret", "%skey=" % _rand_token(rng, 4, "abcdefghijklmnopqrstuvwxyz_")
            + _rand_token(rng, 40, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/=+"))
        add("api_key", "ghp_" + _rand_token(rng, 32, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))
        add("api_key", "sk-" + _rand_token(rng, 32, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))
        add("api_token", "ya29." + _rand_token(rng, 48, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"))
        add("bearer_token", "Bearer eyJ" + _rand_token(rng, 12, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") +
            "." + _rand_token(rng, 12, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") +
            "." + _rand_token(rng, 12, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))
        add("bearer_token", "Bearer " + _rand_token(rng, 44, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"))
        add("high_entropy_token", _rand_token(rng, 24, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
            if rng.random() > 0.5 else _rand_token(rng, 32, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"))
        add("database_url", "%s://%s:%s@%s:%d/%s" % (
            rng.choice(["postgres", "mysql", "mongodb", "redis"]),
            rng.choice(["user", "admin", "app"]),
            _rand_token(rng, 12, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            rng.choice(["db.internal", "db.prod.local", "localhost"]),
            rng.choice([5432, 3306, 27017, 6379]),
            rng.choice(["synth", "main", "app", "analytics"]),
        ))
        add("email", "%s@%s.%s" % (
            _rand_token(rng, rng.randint(3, 10), "abcdefghijklmnopqrstuvwxyz0123456789._-"),
            _rand_token(rng, rng.randint(3, 12), "abcdefghijklmnopqrstuvwxyz0123456789-"),
            rng.choice(["com", "io", "dev", "co", "internal"]),
        ))
        add("private_key", "-----BEGIN %s PRIVATE KEY-----%s-----END %s PRIVATE KEY-----" % (
            rng.choice(["RSA", "EC", "OPENSSH"]),
            _rand_token(rng, 60, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n"),
            rng.choice(["RSA", "EC", "OPENSSH"]),
        ))

    # negatives: identifiers, paths, versions, plain words
    for _ in range(n_per_kind * 4):
        if rng.random() < 0.5:
            add("benign", "_".join(rng.choice(_IDENTIFIERS) for _ in range(rng.randint(1, 3))))
        else:
            add("benign", _rand_token(rng, rng.randint(4, 14), "abcdefghijklmnopqrstuvwxyz_-"))
    for _ in range(40):
        add("benign", "%d.%d.%d" % (rng.randint(0, 9), rng.randint(0, 9), rng.randint(0, 9)))
    for w in ("calculate_discount", "price", "rate", "apply_coupon", "config",
              "settings.json", "runtime.secrets.json", "README.md", "__pycache__"):
        for _ in range(12):
            add("benign", w)
    return data


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
_TRIGRAM = re.compile(r"(?=(...))")


def _features(token: str):
    feats = {"bias": 1.0}
    n = len(token)
    feats["len"] = n / 60.0
    # char n-grams (pad)
    padded = "#" + token + "#"
    for i in range(len(padded) - 2):
        feats["ng3_" + padded[i:i + 3]] = 1.0
    # shape features
    alnum = sum(c.isalnum() for c in token)
    seps = sum(c in "._-:/+=" for c in token)
    feats["alnum_ratio"] = alnum / n if n else 0.0
    feats["sep_count"] = seps / max(n, 1)
    feats["dash_count"] = token.count("-") / max(n, 1)
    feats["underscore_count"] = token.count("_") / max(n, 1)
    feats["digit_ratio"] = sum(c.isdigit() for c in token) / max(n, 1)
    feats["upper_ratio"] = sum(c.isupper() for c in token) / max(n, 1)
    # entropy
    if n:
        counts = Counter(token)
        feats["entropy"] = -sum((c / n) * math.log2(c / n) for c in counts.values()) / 4.0
    else:
        feats["entropy"] = 0.0
    # hex / base64 ratio
    hexchars = sum(c in "0123456789abcdefABCDEF" for c in token)
    feats["hex_ratio"] = hexchars / max(n, 1)
    b64chars = sum(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in token)
    feats["b64_ratio"] = b64chars / max(n, 1)
    # discriminative shape signals (helps distinguish the structured kinds)
    low = token.lower()
    feats["starts_akia"] = 1.0 if token.startswith("AKIA") else 0.0
    feats["starts_bearer"] = 1.0 if low.startswith("bearer ") else 0.0
    feats["starts_eyj"] = 1.0 if token.startswith("eyJ") else 0.0
    feats["has_scheme"] = 1.0 if re.match(r"^[a-z][a-z0-9+.-]*://", token) else 0.0
    feats["has_at"] = 1.0 if "@" in token else 0.0
    feats["has_begin_pk"] = 1.0 if token.startswith("-----BEGIN") else 0.0
    feats["has_sk_proj"] = 1.0 if low.startswith("sk-") else 0.0
    feats["has_ya29"] = 1.0 if low.startswith("ya29.") else 0.0
    feats["has_ghp"] = 1.0 if low.startswith("ghp_") else 0.0
    return feats


def _build_vocab(dataset):
    vocab = {}
    for _, token in dataset:
        for k in _features(token):
            if k not in vocab:
                vocab[k] = len(vocab)
    return vocab


def _sparse_pairs(token: str, vocab: dict) -> list:
    feats = _features(token)
    return [(vocab[k], v) for k, v in feats.items() if k in vocab]


# ---------------------------------------------------------------------------
# Multinomial softmax logistic regression (hand-rolled, sparse GD)
# ---------------------------------------------------------------------------
def _softmax_with(bias, weights, pairs):
    scores = list(bias)
    for idx, val in pairs:
        for c in range(len(weights)):
            scores[c] += weights[c][idx] * val
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


def _train(n_per_kind: int = 25, epochs=60, lr=0.1, l2=1e-5):
    dataset = _build_dataset(n_per_kind)
    vocab = _build_vocab(dataset)
    nv = len(vocab)
    ncls = len(_CLASSES)
    idx_of = {c: i for i, c in enumerate(_CLASSES)}
    rng = random.Random(7)
    precomputed = [(_sparse_pairs(tok, vocab), kind) for kind, tok in dataset]
    weights = [[0.0] * nv for _ in range(ncls)]
    bias = [0.0] * ncls
    n = len(precomputed)

    for _ in range(epochs):
        rng.shuffle(precomputed)
        for pairs, kind in precomputed:
            probs = _softmax_with(bias, weights, pairs)
            target = idx_of[kind]
            for c in range(ncls):
                grad = probs[c] - (1.0 if c == target else 0.0)
                if grad:
                    for idx, val in pairs:
                        weights[c][idx] -= lr * (grad * val - l2 * weights[c][idx])
                    bias[c] -= lr * grad
    return {"classes": _CLASSES, "weights": weights, "bias": bias,
            "vocab": vocab, "meta": {"model_version": _MODEL_VERSION,
                                     "feature_dim": nv, "n_classes": ncls}}


def _predict_raw(model, token):
    return _softmax_with(model["bias"], model["weights"], _sparse_pairs(token, model["vocab"]))


class SecretClassifier:
    """Profile-driven secret classifier facade.

    Mirrors ``RerankerFacade`` semantics: loads a trained artifact when
    available, otherwise trains deterministically in memory. Falls back to
    no-op detection (no extra matches) if the model cannot be built, so the
    rule-based redactor remains the safety net.
    """
    name = "secret_classifier"
    backend = "cpu_deterministic"

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self.model = None
        self.available = False
        self.model_version = "none"
        self.load_error = ""
        self._load_or_train()

    def _load_or_train(self):
        if self.model_path and os.path.exists(self.model_path):
            try:
                with open(self.model_path, "rb") as fh:
                    self.model = pickle.load(fh)
                self.available = True
                self.model_version = self.model["meta"].get("model_version", "none")
                return
            except Exception as exc:  # noqa: BLE001
                self.load_error = "%s:%s" % (type(exc).__name__, exc)
        # Train deterministically (Phase 2 ships no external artifact). Cached
        # process-wide so training cost is paid once.
        try:
            self.model = _trained_once()
            self.available = True
            self.model_version = self.model["meta"].get("model_version", "none")
            self._persist()
        except Exception as exc:  # noqa: BLE001
            self.load_error = "%s:%s" % (type(exc).__name__, exc)
            self.available = False

    def _persist(self):
        if not self.model_path:
            return
        try:
            os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
            tmp = self.model_path + ".tmp"
            with open(tmp, "wb") as fh:
                pickle.dump(self.model, fh)
            os.replace(tmp, self.model_path)
        except Exception:
            pass  # persistence is best-effort

    def classify(self, value: str) -> dict:
        if not self.available or not self.model:
            return {"kind": "benign", "confidence": 0.0, "is_secret": False}
        probs = _predict_raw(self.model, value)
        best = max(range(len(probs)), key=lambda i: probs[i])
        kind = self.model["classes"][best]
        conf = probs[best]
        return {"kind": kind, "confidence": conf, "is_secret": kind != "benign"}

    def scan(self, text: str, threshold: float = _DEFAULT_THRESHOLD) -> list:
        """Return extra matches not already covered by rule-based scan()."""
        if not self.available:
            return []
        from .secrets import scan as _regex_scan
        existing = _regex_scan(text)
        # dedupe overlapping/exact regex matches (e.g. one span matched by two
        # rule patterns); keep the first, longest wins on tie-break.
        existing.sort(key=lambda m: (m["start"], -(m["end"] - m["start"])))
        deduped = []
        for m in existing:
            if any(m["start"] < p["end"] and p["start"] < m["end"] for p in deduped):
                continue
            deduped.append(m)
        existing = deduped
        spans = [(m["start"], m["end"]) for m in existing]
        out = list(existing)

        def _overlap(a, b):
            return a[0] < b[1] and b[0] < a[1]

        for tok_m in re.finditer(r"[A-Za-z0-9+/_\-:.@]{12,}", text):
            s, e = tok_m.start(), tok_m.end()
            if any(_overlap((s, e), (a, b)) for a, b in spans):
                continue
            token = tok_m.group()
            if token.lower().startswith("begin "):  # already a regex match
                continue
            res = self.classify(token)
            if res["is_secret"] and res["confidence"] >= threshold:
                out.append({"kind": res["kind"], "value": token,
                            "start": s, "end": e, "confidence": res["confidence"]})
                spans.append((s, e))
        out.sort(key=lambda m: (m["start"], m["end"]))
        return out


def train_and_save(model_path: str, n_per_kind: int = 25) -> dict:
    model = _train(n_per_kind=n_per_kind)
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    with open(model_path, "wb") as fh:
        pickle.dump(model, fh)
    return model["meta"]
