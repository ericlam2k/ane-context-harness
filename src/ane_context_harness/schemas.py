"""Data schemas (dataclasses) for the harness. No external deps."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class BehavioralProfile(str, Enum):
    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"
    CONSTRAINED = "CONSTRAINED"
    BALANCED = "BALANCED"
    HIGH_CAPACITY = "HIGH_CAPACITY"


class RankBackend(str, Enum):
    """Ranker backends. Phase 1 ships CPU_DETERMINISTIC only."""
    CPU_DETERMINISTIC = "cpu_deterministic"
    COREML_ALL = "coreml_all"
    COREML_CPU_GPU = "coreml_cpu_gpu"
    LOCAL_GPU = "local_gpu"


@dataclass(frozen=True)
class RepositoryChunk:
    chunk_id: str
    repository_id: str
    path: str
    language: str
    start_line: int
    end_line: int
    symbol: Optional[str]
    content_hash: str
    estimated_tokens: int
    lexical_terms: tuple
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkScore:
    chunk_id: str
    lexical_score: float = 0.0
    symbol_score: float = 0.0
    path_score: float = 0.0
    dependency_score: float = 0.0
    test_pair_score: float = 0.0
    git_recency_score: float = 0.0
    initial_score: float = 0.0
    ml_relevance_score: Optional[float] = None
    final_score: float = 0.0
    selection_reasons: list = field(default_factory=list)
    mandatory: bool = False


@dataclass
class EvidenceItem:
    path: str
    start_line: int
    end_line: int
    content_hash: str
    symbol: Optional[str]
    score: float
    selection_reasons: list
    content: str
    category: str
    redacted: bool = False


@dataclass
class Metrics:
    candidate_tokens: int
    selected_tokens: int
    tokens_removed: int
    reduction_percent: float
    total_latency_ms: float
    candidate_generation_ms: float
    reranking_ms: float
    redaction_ms: float
    packing_ms: float


@dataclass
class SelectRequest:
    repository_id: str
    task: str
    token_budget: int = 12000
    explicit_paths: list = field(default_factory=list)
    tool_outputs: list = field(default_factory=list)
    conversation_summary: Optional[str] = None
    options: dict = field(default_factory=lambda: {
        "include_tests": True,
        "redact_secrets": False,
        "use_ml_reranker": False,
        "stable_order": True,
    })


@dataclass
class EvidencePackage:
    request_id: str
    repository_id: str
    task: str
    policy_version: str
    index_version: str
    model_version: str
    metrics: dict
    redaction_summary: dict
    evidence: list
    markdown: str
    execution: dict


@dataclass
class HealthResponse:
    status: str
    platform: str
    coreml_model_loaded: bool
    compute_mode: str
    index_version: str
    service_version: str
    behavioral_profile: str
    coreml_compute_units_requested: Optional[str] = None
    fallback_used: bool = False
    secret_classifier: str = "cpu_deterministic"
    capabilities: dict = field(default_factory=dict)


@dataclass
class IndexRequest:
    repository_path: str
    repository_id: Optional[str] = None
    force_rebuild: bool = False


@dataclass
class IndexResponse:
    repository_id: str
    files_indexed: int
    chunks_indexed: int
    files_skipped: int
    duration_ms: float
    incremental: bool = False
    index_version: str = "2"


def evidence_to_dict(item: EvidenceItem) -> dict:
    return {
        "path": item.path,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "content_hash": item.content_hash,
        "symbol": item.symbol,
        "score": round(item.score, 4),
        "selection_reasons": item.selection_reasons,
        "category": item.category,
        "redacted": item.redacted,
        "content": item.content,
    }
