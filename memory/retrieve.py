"""Retrieval API for Milton memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any, Literal
import re
import logging

from .backends import get_backend
from .schema import MemoryItem
from .embeddings import embed, is_available as embeddings_available
from .init_db import get_client

logger = logging.getLogger(__name__)


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _score_item(
    item: MemoryItem, query_tokens: set[str], recency_bias: float, now: datetime
) -> float:
    if query_tokens:
        item_tokens = _tokenize(item.content + " " + " ".join(item.tags))
        overlap = len(query_tokens & item_tokens)
        text_score = overlap / max(len(query_tokens), 1)
    else:
        text_score = 0.0

    age_seconds = max((now - item.ts).total_seconds(), 0.0)
    age_hours = age_seconds / 3600.0
    recency_score = 1.0 / (1.0 + age_hours)

    recency_weight = max(0.0, min(recency_bias, 1.0))
    score = (text_score * (1.0 - recency_weight)) + (recency_score * recency_weight)
    score += item.importance * 0.15
    return score


def query_recent(
    hours: int,
    tags: Optional[list[str]] = None,
    limit: int = 20,
    *,
    repo_root: Optional[Path] = None,
    backend: Optional[Any] = None,
) -> list[MemoryItem]:
    """Return recent short-term memories with optional tag filtering."""
    backend = backend or get_backend(repo_root=repo_root)
    items = backend.list_short_term()
    cutoff = _now_utc() - timedelta(hours=hours)

    tag_filter = [tag.strip().lower() for tag in tags or [] if tag.strip()]

    filtered: list[MemoryItem] = []
    for item in items:
        if item.ts < cutoff:
            continue
        if tag_filter and not any(tag in item.tags for tag in tag_filter):
            continue
        filtered.append(item)

    filtered.sort(key=lambda entry: (entry.ts, entry.id), reverse=True)
    return filtered[:limit]


def query_relevant(
    text: str,
    limit: int = 10,
    recency_bias: float = 0.35,
    *,
    repo_root: Optional[Path] = None,
    backend: Optional[Any] = None,
) -> list[MemoryItem]:
    """Return relevant short-term memories ranked by relevance + recency + importance."""
    if not text.strip():
        return []

    backend = backend or get_backend(repo_root=repo_root)
    items = backend.list_short_term()
    query_tokens = _tokenize(text)
    now = _now_utc()

    scored = [
        (item, _score_item(item, query_tokens, recency_bias, now)) for item in items
    ]
    scored.sort(
        key=lambda entry: (entry[1], entry[0].importance, entry[0].ts, entry[0].id),
        reverse=True,
    )

    return [item for item, _score in scored[:limit]]


def query_relevant_hybrid(
    text: str,
    limit: int = 10,
    recency_bias: float = 0.35,
    semantic_weight: float = 0.5,
    *,
    mode: Literal["hybrid", "deterministic", "semantic"] = "hybrid",
    repo_root: Optional[Path] = None,
    backend: Optional[Any] = None,
) -> list[MemoryItem]:
    """
    Return relevant short-term memories using hybrid retrieval.

    Combines deterministic token-based scoring with semantic similarity scoring.
    Falls back to deterministic-only mode if embeddings are unavailable.

    Args:
        text: Query text
        limit: Maximum number of results to return
        recency_bias: Weight for recency in deterministic scoring (0.0-1.0)
        semantic_weight: Weight for semantic similarity in final score (0.0-1.0)
            - 0.0 = pure deterministic
            - 1.0 = pure semantic
            - 0.5 = balanced hybrid (default)
        mode: Retrieval mode ("hybrid", "deterministic", "semantic")
        repo_root: Repository root path
        backend: Backend instance (optional)

    Returns:
        List of MemoryItem objects ranked by combined score

    Example:
        # Balanced hybrid retrieval
        results = query_relevant_hybrid("machine learning projects", limit=5)

        # More weight on semantic similarity
        results = query_relevant_hybrid("AI research", semantic_weight=0.7)

        # Pure deterministic (same as query_relevant)
        results = query_relevant_hybrid("test", mode="deterministic")
    """
    if not text.strip():
        return []

    backend = backend or get_backend(repo_root=repo_root)
    items = backend.list_short_term()

    if not items:
        return []

    # Determine effective mode based on embeddings availability
    effective_mode = mode
    if mode in ("hybrid", "semantic"):
        if not embeddings_available():
            logger.warning(
                "Embeddings not available, falling back to deterministic mode. "
                "Install sentence-transformers for semantic search."
            )
            effective_mode = "deterministic"

    # Pure deterministic mode
    if effective_mode == "deterministic":
        return query_relevant(
            text,
            limit=limit,
            recency_bias=recency_bias,
            repo_root=repo_root,
            backend=backend,
        )

    # Semantic or hybrid mode - need embeddings
    query_vector = embed(text)
    if query_vector is None:
        logger.warning("Failed to generate query embedding, falling back to deterministic mode")
        return query_relevant(
            text,
            limit=limit,
            recency_bias=recency_bias,
            repo_root=repo_root,
            backend=backend,
        )

    # Query Weaviate for semantic similarity
    try:
        client = get_client()
        collection = client.collections.get("ShortTermMemory")

        # Perform vector search
        search_results = collection.query.near_vector(
            near_vector=query_vector.tolist(),
            limit=max(limit * 3, 100),  # Get more candidates for reranking
            return_metadata=["distance"]
        )

        # Build mapping from UUID to semantic similarity
        semantic_scores = {}
        for result in search_results.objects:
            # Convert cosine distance to similarity (1 - distance)
            # Weaviate returns distance in [0, 2] range for cosine
            distance = result.metadata.distance if result.metadata.distance is not None else 1.0
            similarity = max(0.0, 1.0 - (distance / 2.0))
            semantic_scores[str(result.uuid)] = similarity

        client.close()

    except Exception as e:
        logger.error(f"Semantic search failed: {e}", exc_info=True)
        logger.warning("Falling back to deterministic mode")
        return query_relevant(
            text,
            limit=limit,
            recency_bias=recency_bias,
            repo_root=repo_root,
            backend=backend,
        )

    # Pure semantic mode
    if effective_mode == "semantic":
        # Sort items by semantic similarity only
        scored = []
        for item in items:
            semantic_score = semantic_scores.get(item.id, 0.0)
            if semantic_score > 0.0:  # Only include items with semantic match
                scored.append((item, semantic_score))

        scored.sort(key=lambda entry: entry[1], reverse=True)
        return [item for item, _score in scored[:limit]]

    # Hybrid mode - combine deterministic and semantic scores
    query_tokens = _tokenize(text)
    now = _now_utc()

    # Compute deterministic scores for all items
    deterministic_scores = {}
    for item in items:
        deterministic_scores[item.id] = _score_item(item, query_tokens, recency_bias, now)

    # Normalize scores to [0, 1] range for fair combination
    max_det_score = max(deterministic_scores.values()) if deterministic_scores else 1.0
    max_sem_score = max(semantic_scores.values()) if semantic_scores else 1.0

    # Avoid division by zero
    max_det_score = max(max_det_score, 0.001)
    max_sem_score = max(max_sem_score, 0.001)

    # Combine scores
    scored = []
    for item in items:
        det_score = deterministic_scores.get(item.id, 0.0) / max_det_score
        sem_score = semantic_scores.get(item.id, 0.0) / max_sem_score

        # Weighted combination
        weight = max(0.0, min(semantic_weight, 1.0))
        combined_score = (det_score * (1.0 - weight)) + (sem_score * weight)

        scored.append((item, combined_score, det_score, sem_score))

    # Sort by combined score, then importance, then timestamp
    scored.sort(
        key=lambda entry: (entry[1], entry[0].importance, entry[0].ts, entry[0].id),
        reverse=True,
    )

    return [item for item, _combined, _det, _sem in scored[:limit]]
