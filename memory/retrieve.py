"""Retrieval API for Milton memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
import re

from .backends import get_backend
from .schema import MemoryItem


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
