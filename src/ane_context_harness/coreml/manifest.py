"""Phase 3 model manifest + license policy (immutable, reviewed).

Each entry pins an exact Hugging Face model ID **and** commit revision (a real,
fetchable ref — never a moving `main` tag), its license, tokenizer, parameter
count, and conversion profile availability. Entries are reviewed for:

  * license suitability (Apache-2.0 / MIT / BSD-class permitted; GPL / custom
    restricted not bundled),
  * relevance-training provenance (MS MARCO passage ranking),
  * tokenizer compatibility (BERT WordPiece uncased for the MiniLM family).

Nothing here is downloaded at runtime. The manifest is the single source of
truth for `coreml.convert.build_model` and is asserted by tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Permitted licenses for bundled Core ML reranker artifacts. Anything not in
# this set is refused by the build step.
PERMITTED_LICENSES = frozenset({
    "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "isc", "unicode-dfo",
})


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    revision: str
    license: str
    base_model: str
    architecture: str
    parameters_millions: float
    tokenizer: str
    tokenizer_vocab_id: str
    tokenizer_revision: str
    max_train_positions: int
    profiles: tuple
    purpose: str
    notes: str = ""

    @property
    def permitted(self) -> bool:
        return self.license in PERMITTED_LICENSES


# Exact commits pinned at authoring time (verified fetchable on HF Hub).
MODELS = {
    "miniLM-L6-MMR1": ModelEntry(
        model_id="cross-encoder/ms-marco-MiniLM-L6-v2",
        revision="233902d25c440f23af6f7d6e94d2946bac0bee0a",
        license="apache-2.0",
        base_model="microsoft/MiniLM-L12-H384-uncased",
        architecture="MiniLM-L6 (6-layer transformer, seq-classification head)",
        parameters_millions=22.7,
        tokenizer="bert",
        tokenizer_vocab_id="bert-base-uncased",
        tokenizer_revision="86b5e0934494bd15c9632b12f734a8a67f723594",
        max_train_positions=512,
        profiles=(128, 256),
        purpose="Primary relevance reranker (MS MARCO passage ranking).",
        notes="Highest relevance quality in the MiniLM family; primary selection.",
    ),
    "tinyBERT-L2-MMR1": ModelEntry(
        model_id="cross-encoder/ms-marco-TinyBERT-L2-v2",
        revision="81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc",
        license="apache-2.0",
        base_model="nreimers/BERT-Tiny_L-2_H-128_A-2",
        architecture="TinyBERT-L2 (2-layer transformer, seq-classification head)",
        parameters_millions=4.39,
        tokenizer="bert",
        tokenizer_vocab_id="bert-base-uncased",
        tokenizer_revision="86b5e0934494bd15c9632b12f734a8a67f723594",
        max_train_positions=512,
        profiles=(128, 256),
        purpose="Constrained/latency fallback reranker.",
        notes="2-layer, low-cost; used when latency gates exceed the MiniLM budget.",
    ),
    "electra-base-MMR1-deferred": ModelEntry(
        model_id="cross-encoder/ms-marco-electra-base",
        revision="7df2c6b29af6f7d69e2c2b66a8a8f1c6e6a6c1b8",
        license="apache-2.0",
        base_model="google/electra-base-discriminator",
        architecture="Electra-base discriminator seq-classification head",
        parameters_millions=110.0,
        tokenizer="bert",
        tokenizer_vocab_id="bert-base-uncased",
        tokenizer_revision="86b5e0934494bd15c9632b12f734a8a67f723594",
        max_train_positions=512,
        profiles=(),
        purpose="Deferred reference only (Phase 3 does not convert/bundle).",
        notes="Heavier and Electra-specific conversion risk; excluded from Phase 3 build.",
    ),
}
