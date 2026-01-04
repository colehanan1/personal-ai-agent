"""
Semantic Embeddings for Milton Memory

Local-first embedding generation using sentence-transformers.
Supports caching and graceful degradation when model unavailable.

Requirements:
    pip install sentence-transformers

Model:
    all-MiniLM-L6-v2 (80MB, 384 dimensions, fast)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, List
import hashlib
import json

import numpy as np

logger = logging.getLogger(__name__)

# Default embedding model (small and fast)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Cache directory for embeddings
STATE_DIR = Path(os.getenv("STATE_DIR", Path.home() / ".local" / "state" / "milton"))
EMBEDDING_CACHE_DIR = STATE_DIR / "embeddings_cache"

# Global model instance (loaded lazily)
_MODEL = None
_MODEL_LOADED = False


def _get_cache_path(text: str, model_name: str) -> Path:
    """Get cache file path for text embedding."""
    # Create hash of text + model for cache key
    cache_key = hashlib.sha256(f"{model_name}:{text}".encode()).hexdigest()
    return EMBEDDING_CACHE_DIR / f"{cache_key}.npy"


def _load_model(model_name: str = DEFAULT_MODEL):
    """
    Load sentence-transformers model.

    Args:
        model_name: Model name or path

    Returns:
        SentenceTransformer model instance or None if unavailable
    """
    global _MODEL, _MODEL_LOADED

    if _MODEL_LOADED:
        return _MODEL

    try:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {model_name}")
        _MODEL = SentenceTransformer(model_name)
        _MODEL_LOADED = True
        logger.info(f"Embedding model loaded successfully (dim={EMBEDDING_DIM})")
        return _MODEL

    except ImportError as e:
        logger.warning(
            f"sentence-transformers not installed: {e}. "
            "Install with: pip install sentence-transformers"
        )
        _MODEL_LOADED = True  # Don't try again
        return None

    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}", exc_info=True)
        _MODEL_LOADED = True
        return None


def is_available() -> bool:
    """
    Check if embeddings are available.

    Returns:
        True if model can be loaded, False otherwise
    """
    model = _load_model()
    return model is not None


def embed(
    text: str,
    *,
    model_name: str = DEFAULT_MODEL,
    use_cache: bool = True,
    normalize: bool = True
) -> Optional[np.ndarray]:
    """
    Generate embedding vector for text.

    Args:
        text: Input text to embed
        model_name: Embedding model to use
        use_cache: Whether to use cached embeddings
        normalize: Whether to L2-normalize the embedding

    Returns:
        Embedding vector (384-dim numpy array) or None if model unavailable

    Example:
        vector = embed("This is a test")
        print(vector.shape)  # (384,)
    """
    if not text.strip():
        logger.warning("Cannot embed empty text")
        return None

    # Check cache first
    if use_cache:
        cache_path = _get_cache_path(text, model_name)
        if cache_path.exists():
            try:
                vector = np.load(cache_path)
                logger.debug(f"Loaded embedding from cache: {cache_path.name}")
                return vector
            except Exception as e:
                logger.warning(f"Failed to load cached embedding: {e}")

    # Load model
    model = _load_model(model_name)
    if model is None:
        logger.warning("Embedding model not available, returning None")
        return None

    try:
        # Generate embedding
        vector = model.encode(
            text,
            normalize_embeddings=normalize,
            show_progress_bar=False
        )

        # Ensure correct shape
        if vector.shape != (EMBEDDING_DIM,):
            logger.error(f"Unexpected embedding shape: {vector.shape}, expected ({EMBEDDING_DIM},)")
            return None

        # Save to cache
        if use_cache:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                np.save(cache_path, vector)
                logger.debug(f"Saved embedding to cache: {cache_path.name}")
            except Exception as e:
                logger.warning(f"Failed to cache embedding: {e}")

        return vector

    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}", exc_info=True)
        return None


def embed_batch(
    texts: List[str],
    *,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
    normalize: bool = True,
    show_progress: bool = False
) -> List[Optional[np.ndarray]]:
    """
    Generate embeddings for multiple texts (batched for efficiency).

    Args:
        texts: List of input texts
        model_name: Embedding model to use
        batch_size: Batch size for processing
        normalize: Whether to L2-normalize embeddings
        show_progress: Whether to show progress bar

    Returns:
        List of embedding vectors (or None for failed embeddings)

    Example:
        texts = ["First text", "Second text", "Third text"]
        vectors = embed_batch(texts)
    """
    if not texts:
        return []

    # Load model
    model = _load_model(model_name)
    if model is None:
        logger.warning("Embedding model not available, returning None for all texts")
        return [None] * len(texts)

    try:
        # Generate embeddings in batches
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress
        )

        # Verify shapes and convert to list
        result = []
        for i, vector in enumerate(vectors):
            if vector.shape != (EMBEDDING_DIM,):
                logger.warning(f"Unexpected embedding shape for text {i}: {vector.shape}")
                result.append(None)
            else:
                result.append(vector)

        return result

    except Exception as e:
        logger.error(f"Failed to generate batch embeddings: {e}", exc_info=True)
        return [None] * len(texts)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity (0-1, where 1 is most similar)

    Note:
        If vectors are already L2-normalized, this is just the dot product.
    """
    try:
        # Normalize if needed
        vec1_norm = vec1 / (np.linalg.norm(vec1) + 1e-8)
        vec2_norm = vec2 / (np.linalg.norm(vec2) + 1e-8)

        # Compute dot product
        similarity = np.dot(vec1_norm, vec2_norm)

        # Clamp to [0, 1] range (handle numerical errors)
        similarity = max(0.0, min(1.0, float(similarity)))

        return similarity

    except Exception as e:
        logger.error(f"Failed to compute cosine similarity: {e}")
        return 0.0


def clear_cache() -> int:
    """
    Clear the embeddings cache.

    Returns:
        Number of cache files deleted
    """
    if not EMBEDDING_CACHE_DIR.exists():
        return 0

    count = 0
    for cache_file in EMBEDDING_CACHE_DIR.glob("*.npy"):
        try:
            cache_file.unlink()
            count += 1
        except Exception as e:
            logger.warning(f"Failed to delete cache file {cache_file}: {e}")

    logger.info(f"Cleared {count} cached embeddings")
    return count


def get_cache_stats() -> dict:
    """
    Get statistics about the embeddings cache.

    Returns:
        Dictionary with cache statistics
    """
    if not EMBEDDING_CACHE_DIR.exists():
        return {
            "cache_dir": str(EMBEDDING_CACHE_DIR),
            "exists": False,
            "count": 0,
            "size_mb": 0.0
        }

    cache_files = list(EMBEDDING_CACHE_DIR.glob("*.npy"))
    total_size = sum(f.stat().st_size for f in cache_files)

    return {
        "cache_dir": str(EMBEDDING_CACHE_DIR),
        "exists": True,
        "count": len(cache_files),
        "size_mb": round(total_size / (1024 * 1024), 2)
    }


if __name__ == "__main__":
    # Test the embeddings module
    print("Testing semantic embeddings...")

    # Check availability
    if is_available():
        print("✅ Embeddings available")
    else:
        print("❌ Embeddings not available (install sentence-transformers)")
        exit(1)

    # Test single embedding
    print("\nGenerating embedding for test text...")
    text = "This is a test of the semantic embedding system."
    vector = embed(text)

    if vector is not None:
        print(f"✅ Generated embedding: shape={vector.shape}, dtype={vector.dtype}")
        print(f"   First 5 values: {vector[:5]}")
    else:
        print("❌ Failed to generate embedding")

    # Test batch embeddings
    print("\nGenerating batch embeddings...")
    texts = [
        "Machine learning is fascinating",
        "I love programming in Python",
        "The weather is nice today"
    ]
    vectors = embed_batch(texts, show_progress=True)

    print(f"✅ Generated {len([v for v in vectors if v is not None])}/{len(texts)} embeddings")

    # Test similarity
    if vectors[0] is not None and vectors[1] is not None:
        sim = cosine_similarity(vectors[0], vectors[1])
        print(f"\nCosine similarity (ML vs Python): {sim:.4f}")

    if vectors[0] is not None and vectors[2] is not None:
        sim = cosine_similarity(vectors[0], vectors[2])
        print(f"Cosine similarity (ML vs Weather): {sim:.4f}")

    # Show cache stats
    stats = get_cache_stats()
    print(f"\nCache stats: {stats['count']} embeddings, {stats['size_mb']} MB")
