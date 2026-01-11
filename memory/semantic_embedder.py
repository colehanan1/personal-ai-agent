"""
Semantic Embedder Module

Alias/wrapper for memory.embeddings module to match Week 1 naming convention.
This provides the same interface as embeddings.py with a more explicit name.
"""
from __future__ import annotations

# Import all public API from embeddings module
from .embeddings import (
    DEFAULT_MODEL,
    EMBEDDING_DIM,
    EMBEDDING_CACHE_DIR,
    is_available,
    embed,
    embed_batch,
    cosine_similarity,
    clear_cache,
    get_cache_stats,
)

__all__ = [
    "DEFAULT_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_CACHE_DIR",
    "is_available",
    "embed",
    "embed_batch",
    "cosine_similarity",
    "clear_cache",
    "get_cache_stats",
]
