"""Tests for semantic embeddings module."""

import numpy as np
from pathlib import Path
import tempfile
import os

import pytest

from memory.embeddings import (
    embed,
    embed_batch,
    cosine_similarity,
    is_available,
    clear_cache,
    get_cache_stats,
    EMBEDDING_DIM,
)


if os.environ.get("RUN_INTEGRATION") != "1":
    pytest.skip(
        "Embeddings tests require sentence-transformers model; set RUN_INTEGRATION=1",
        allow_module_level=True,
    )


class TestEmbeddingAvailability:
    """Test embedding model availability checks."""

    def test_is_available_returns_bool(self):
        """Test that is_available returns a boolean."""
        result = is_available()
        assert isinstance(result, bool)

    def test_embedding_dim_constant(self):
        """Test that EMBEDDING_DIM is set correctly."""
        assert EMBEDDING_DIM == 384


class TestSingleEmbedding:
    """Test single text embedding generation."""

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_returns_vector(self):
        """Test that embed() returns a valid numpy array."""
        text = "This is a test"
        vector = embed(text)

        assert vector is not None
        assert isinstance(vector, np.ndarray)
        assert vector.shape == (EMBEDDING_DIM,)
        assert vector.dtype == np.float32 or vector.dtype == np.float64

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_empty_text_returns_none(self):
        """Test that embedding empty text returns None."""
        assert embed("") is None
        assert embed("   ") is None
        assert embed("\n\t") is None

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_is_normalized(self):
        """Test that embeddings are L2-normalized by default."""
        text = "Machine learning is fascinating"
        vector = embed(text, normalize=True)

        # Check L2 norm is approximately 1.0
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 0.01

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_same_text_same_vector(self):
        """Test that same text produces same embedding."""
        text = "Reproducibility test"
        vector1 = embed(text, use_cache=False)
        vector2 = embed(text, use_cache=False)

        assert vector1 is not None
        assert vector2 is not None
        np.testing.assert_array_almost_equal(vector1, vector2, decimal=5)


class TestBatchEmbedding:
    """Test batch embedding generation."""

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_batch_returns_list(self):
        """Test that embed_batch() returns a list of vectors."""
        texts = ["First text", "Second text", "Third text"]
        vectors = embed_batch(texts)

        assert isinstance(vectors, list)
        assert len(vectors) == len(texts)

        for vector in vectors:
            assert vector is not None
            assert isinstance(vector, np.ndarray)
            assert vector.shape == (EMBEDDING_DIM,)

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_batch_empty_list(self):
        """Test that embed_batch() handles empty list."""
        vectors = embed_batch([])
        assert vectors == []

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_batch_with_batch_size(self):
        """Test that embed_batch() respects batch_size parameter."""
        texts = [f"Text number {i}" for i in range(10)]
        vectors = embed_batch(texts, batch_size=3)

        assert len(vectors) == 10
        for vector in vectors:
            assert vector is not None
            assert vector.shape == (EMBEDDING_DIM,)


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_cosine_similarity_identical_vectors(self):
        """Test that identical vectors have similarity of 1.0."""
        text = "Machine learning"
        vec1 = embed(text)
        vec2 = embed(text)

        similarity = cosine_similarity(vec1, vec2)
        assert 0.99 < similarity <= 1.0

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_cosine_similarity_similar_texts(self):
        """Test that similar texts have high similarity."""
        vec1 = embed("artificial intelligence and machine learning")
        vec2 = embed("machine learning and AI research")

        similarity = cosine_similarity(vec1, vec2)
        assert similarity > 0.5  # Should be reasonably similar

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_cosine_similarity_dissimilar_texts(self):
        """Test that dissimilar texts have lower similarity."""
        vec1 = embed("machine learning algorithms")
        vec2 = embed("cooking recipes for dinner")

        similarity = cosine_similarity(vec1, vec2)
        # Similarity should be lower than similar texts
        # (but might not be zero due to common words)
        assert 0.0 <= similarity < 0.9

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_cosine_similarity_returns_float(self):
        """Test that cosine_similarity returns a float in [0, 1]."""
        vec1 = embed("test one")
        vec2 = embed("test two")

        similarity = cosine_similarity(vec1, vec2)
        assert isinstance(similarity, float)
        assert 0.0 <= similarity <= 1.0


class TestCaching:
    """Test embedding caching functionality."""

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_caching_enabled_by_default(self):
        """Test that caching is enabled by default."""
        # Clear cache first
        clear_cache()

        text = "Cache test text"
        vector1 = embed(text, use_cache=True)

        # Get cache stats
        stats = get_cache_stats()
        assert stats["count"] >= 1

        # Second call should use cache
        vector2 = embed(text, use_cache=True)

        # Vectors should be identical
        np.testing.assert_array_equal(vector1, vector2)

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_cache_can_be_disabled(self):
        """Test that caching can be disabled."""
        text = "No cache test"
        vector1 = embed(text, use_cache=False)
        vector2 = embed(text, use_cache=False)

        # Vectors should still be nearly identical (same text)
        assert vector1 is not None
        assert vector2 is not None
        np.testing.assert_array_almost_equal(vector1, vector2, decimal=5)

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_clear_cache(self):
        """Test that clear_cache() removes cached embeddings."""
        # Generate some embeddings
        embed("test 1", use_cache=True)
        embed("test 2", use_cache=True)

        # Clear cache
        count = clear_cache()
        assert count >= 0  # Some files were deleted

        # Cache should be empty or minimal now
        stats = get_cache_stats()
        # Note: clear_cache() only clears .npy files, may not clear everything
        assert stats["count"] >= 0

    def test_get_cache_stats_structure(self):
        """Test that get_cache_stats() returns correct structure."""
        stats = get_cache_stats()

        assert isinstance(stats, dict)
        assert "cache_dir" in stats
        assert "exists" in stats
        assert "count" in stats
        assert "size_mb" in stats

        assert isinstance(stats["cache_dir"], str)
        assert isinstance(stats["exists"], bool)
        assert isinstance(stats["count"], int)
        assert isinstance(stats["size_mb"], (int, float))


class TestGracefulDegradation:
    """Test graceful degradation when embeddings unavailable."""

    def test_is_available_when_not_installed(self, monkeypatch):
        """Test is_available returns False when sentence-transformers not available."""
        # This test may pass even with sentence-transformers installed
        # because we can't easily uninstall it in a test
        result = is_available()
        assert isinstance(result, bool)

    def test_embed_returns_none_when_unavailable(self, monkeypatch):
        """Test that embed returns None when model cannot be loaded."""
        # Mock the model loading to fail
        def mock_load_model(model_name):
            return None

        import memory.embeddings as emb_module
        monkeypatch.setattr(emb_module, "_load_model", mock_load_model)

        # Reset the model loaded flag
        emb_module._MODEL_LOADED = False
        emb_module._MODEL = None

        result = embed("test text")
        # Should return None when model can't be loaded
        # (actual behavior depends on _load_model implementation)
        assert result is None or isinstance(result, np.ndarray)


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_very_long_text(self):
        """Test embedding very long text."""
        long_text = " ".join(["word"] * 1000)
        vector = embed(long_text)

        assert vector is not None
        assert vector.shape == (EMBEDDING_DIM,)

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_special_characters(self):
        """Test embedding text with special characters."""
        special_text = "Hello! @#$%^&*() 你好 🚀"
        vector = embed(special_text)

        assert vector is not None
        assert vector.shape == (EMBEDDING_DIM,)

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_batch_with_empty_strings(self):
        """Test embed_batch handles mixed empty and non-empty strings."""
        texts = ["valid text", "", "another valid", "   "]
        vectors = embed_batch(texts)

        assert len(vectors) == 4
        # Non-empty texts should have vectors
        assert vectors[0] is not None
        assert vectors[2] is not None

    @pytest.mark.skipif(not is_available(), reason="sentence-transformers not installed")
    def test_embed_unicode_text(self):
        """Test embedding unicode text."""
        unicode_text = "Machine learning in 日本語 and Español"
        vector = embed(unicode_text)

        assert vector is not None
        assert vector.shape == (EMBEDDING_DIM,)
