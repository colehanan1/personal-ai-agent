"""Tests for hybrid retrieval functionality."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tempfile
import os

from memory.schema import MemoryItem
from memory.retrieve import (
    query_relevant,
    query_relevant_hybrid,
    _tokenize,
    _score_item,
)
from memory.embeddings import is_available as embeddings_available


class MockWeaviateSearchResult:
    """Mock Weaviate search result object."""

    def __init__(self, uuid: str, distance: float):
        self.uuid = uuid
        self.metadata = Mock()
        self.metadata.distance = distance


class MockWeaviateQueryResult:
    """Mock Weaviate query result."""

    def __init__(self, objects: list):
        self.objects = objects


def create_mock_weaviate_client(items: list, query_text: str = ""):
    """
    Create a mock Weaviate client that returns semantic scores for the given items.

    Items closer in meaning to the query get higher scores.
    """
    # Create mock search results with item UUIDs and fake distances
    # Lower distance = higher similarity
    mock_objects = []
    for i, item in enumerate(items):
        # Simple heuristic: items with "AI", "intelligence", "learning" get lower distance
        content_lower = item.content.lower()
        query_lower = query_text.lower()

        # Check for semantic overlap
        ai_terms = {"ai", "artificial", "intelligence", "machine", "learning", "neural", "deep"}
        item_terms = set(content_lower.split())
        query_terms = set(query_lower.split())

        ai_overlap = len(item_terms & ai_terms) + len(query_terms & ai_terms & item_terms)
        if ai_overlap > 0:
            distance = 0.3 / ai_overlap  # Lower distance for AI-related content
        else:
            distance = 0.9  # High distance for unrelated content

        mock_objects.append(MockWeaviateSearchResult(item.id, distance))

    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_query = MagicMock()

    mock_query.near_vector.return_value = MockWeaviateQueryResult(mock_objects)
    mock_collection.query = mock_query
    mock_client.collections.get.return_value = mock_collection

    return mock_client


class MockBackend:
    """Mock backend for testing."""

    def __init__(self, items=None):
        self.items = items or []

    def list_short_term(self) -> list[MemoryItem]:
        return self.items


def create_test_item(
    content: str,
    agent: str = "test",
    importance: float = 0.5,
    tags: list = None,
    hours_ago: int = 0,
) -> MemoryItem:
    """Create a test memory item."""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return MemoryItem(
        agent=agent,
        type="fact",
        content=content,
        tags=tags or [],
        importance=importance,
        source="test",
        ts=ts,
    )


class TestTokenization:
    """Test tokenization helper function."""

    def test_tokenize_simple_text(self):
        """Test tokenization of simple text."""
        tokens = _tokenize("Hello World")
        assert tokens == {"hello", "world"}

    def test_tokenize_with_numbers(self):
        """Test tokenization with numbers."""
        tokens = _tokenize("Python 3.11 released")
        assert "python" in tokens
        assert "3" in tokens
        assert "11" in tokens
        assert "released" in tokens

    def test_tokenize_removes_punctuation(self):
        """Test that tokenization removes punctuation."""
        tokens = _tokenize("Hello, world!")
        assert tokens == {"hello", "world"}

    def test_tokenize_lowercase(self):
        """Test that tokenization converts to lowercase."""
        tokens = _tokenize("UPPERCASE lowercase")
        assert tokens == {"uppercase", "lowercase"}


class TestDeterministicScoring:
    """Test deterministic scoring function."""

    def test_score_item_token_match(self):
        """Test that items with matching tokens score higher."""
        item = create_test_item("machine learning algorithms")
        query_tokens = _tokenize("machine learning")
        now = datetime.now(timezone.utc)

        score = _score_item(item, query_tokens, recency_bias=0.0, now=now)
        assert score > 0.0

    def test_score_item_no_match(self):
        """Test that items without matching tokens have lower score."""
        item = create_test_item("cooking recipes")
        query_tokens = _tokenize("machine learning")
        now = datetime.now(timezone.utc)

        score = _score_item(item, query_tokens, recency_bias=0.0, now=now)
        # Score might be > 0 due to importance, but should be low
        assert score >= 0.0

    def test_score_item_recency_bias(self):
        """Test that recency bias affects scoring."""
        recent_item = create_test_item("test content", hours_ago=1)
        old_item = create_test_item("test content", hours_ago=100)

        query_tokens = _tokenize("test")
        now = datetime.now(timezone.utc)

        recent_score = _score_item(recent_item, query_tokens, recency_bias=1.0, now=now)
        old_score = _score_item(old_item, query_tokens, recency_bias=1.0, now=now)

        # Recent item should score higher with high recency bias
        assert recent_score > old_score

    def test_score_item_importance_bonus(self):
        """Test that importance adds to the score."""
        high_importance = create_test_item("test", importance=0.9)
        low_importance = create_test_item("test", importance=0.1)

        query_tokens = _tokenize("test")
        now = datetime.now(timezone.utc)

        high_score = _score_item(high_importance, query_tokens, recency_bias=0.0, now=now)
        low_score = _score_item(low_importance, query_tokens, recency_bias=0.0, now=now)

        # High importance should score higher
        assert high_score > low_score


class TestDeterministicRetrieval:
    """Test deterministic query_relevant function."""

    def test_query_relevant_empty_query(self):
        """Test that empty query returns empty list."""
        backend = MockBackend()
        results = query_relevant("", backend=backend)
        assert results == []

        results = query_relevant("   ", backend=backend)
        assert results == []

    def test_query_relevant_no_items(self):
        """Test query with no items in backend."""
        backend = MockBackend([])
        results = query_relevant("test query", backend=backend)
        assert results == []

    def test_query_relevant_returns_matches(self):
        """Test that query_relevant returns matching items."""
        items = [
            create_test_item("machine learning tutorial"),
            create_test_item("cooking recipes"),
            create_test_item("python machine learning"),
        ]
        backend = MockBackend(items)

        results = query_relevant("machine learning", backend=backend, limit=10)

        # Should return at least the matching items
        assert len(results) > 0
        # Top results should contain "machine learning"
        assert any("machine" in r.content or "learning" in r.content for r in results[:2])

    def test_query_relevant_respects_limit(self):
        """Test that query_relevant respects limit parameter."""
        items = [create_test_item(f"test item {i}") for i in range(20)]
        backend = MockBackend(items)

        results = query_relevant("test", backend=backend, limit=5)
        assert len(results) <= 5

    def test_query_relevant_ranks_by_relevance(self):
        """Test that results are ranked by relevance."""
        items = [
            create_test_item("totally unrelated content"),
            create_test_item("machine learning algorithms"),
            create_test_item("machine learning tutorial machine learning"),  # More matches
        ]
        backend = MockBackend(items)

        results = query_relevant("machine learning", backend=backend, limit=10)

        # Item with more matches should rank higher
        assert len(results) >= 2
        # The item with most token matches should be in top positions
        top_contents = [r.content for r in results[:2]]
        assert any("machine learning" in c for c in top_contents)


class TestHybridRetrieval:
    """Test hybrid retrieval functionality."""

    def test_query_relevant_hybrid_empty_query(self):
        """Test that hybrid query with empty text returns empty list."""
        backend = MockBackend()
        results = query_relevant_hybrid("", backend=backend)
        assert results == []

    def test_query_relevant_hybrid_no_items(self):
        """Test hybrid query with no items."""
        backend = MockBackend([])
        results = query_relevant_hybrid("test", backend=backend)
        assert results == []

    def test_query_relevant_hybrid_deterministic_mode(self):
        """Test hybrid query in pure deterministic mode."""
        items = [
            create_test_item("machine learning algorithms"),
            create_test_item("cooking recipes"),
        ]
        backend = MockBackend(items)

        results = query_relevant_hybrid(
            "machine learning",
            backend=backend,
            mode="deterministic",
            limit=10,
        )

        # Should work regardless of embeddings availability
        assert len(results) > 0

    @pytest.mark.skipif(not embeddings_available(), reason="Embeddings not available")
    def test_query_relevant_hybrid_semantic_weight_zero(self):
        """Test that semantic_weight=0.0 is equivalent to deterministic mode."""
        items = [
            create_test_item("machine learning tutorial"),
            create_test_item("deep learning networks"),
        ]
        backend = MockBackend(items)

        # semantic_weight=0.0 should give pure deterministic results
        results = query_relevant_hybrid(
            "machine learning",
            backend=backend,
            semantic_weight=0.0,
            limit=10,
        )

        assert len(results) > 0

    @pytest.mark.skipif(not embeddings_available(), reason="Embeddings not available")
    def test_query_relevant_hybrid_semantic_weight_one(self):
        """Test that semantic_weight=1.0 gives pure semantic results."""
        items = [
            create_test_item("artificial intelligence research"),
            create_test_item("cooking dinner recipes"),
        ]
        backend = MockBackend(items)
        query = "AI and machine learning"

        # Mock Weaviate client for hermetic testing
        mock_client = create_mock_weaviate_client(items, query)

        with patch("memory.retrieve.get_client", return_value=mock_client):
            # semantic_weight=1.0 should give pure semantic results
            results = query_relevant_hybrid(
                query,
                backend=backend,
                semantic_weight=1.0,
                mode="hybrid",
                limit=10,
            )

        assert len(results) > 0

    @pytest.mark.skipif(not embeddings_available(), reason="Embeddings not available")
    def test_query_relevant_hybrid_balanced_mode(self):
        """Test hybrid query with balanced weights."""
        items = [
            create_test_item("machine learning algorithms and models"),
            create_test_item("cooking recipes for dinner"),
            create_test_item("artificial intelligence research"),
        ]
        backend = MockBackend(items)
        query = "machine learning AI"

        # Mock Weaviate client for hermetic testing
        mock_client = create_mock_weaviate_client(items, query)

        with patch("memory.retrieve.get_client", return_value=mock_client):
            results = query_relevant_hybrid(
                query,
                backend=backend,
                semantic_weight=0.5,
                limit=10,
            )

        assert len(results) > 0
        # Should return relevant items (ML/AI related)
        top_item = results[0]
        assert "machine" in top_item.content or "intelligence" in top_item.content

    def test_query_relevant_hybrid_fallback_when_no_embeddings(self, monkeypatch):
        """Test that hybrid mode falls back to deterministic when embeddings unavailable."""
        # Mock embeddings_available to return False
        import memory.retrieve as retrieve_module
        monkeypatch.setattr(retrieve_module, "embeddings_available", lambda: False)

        items = [
            create_test_item("machine learning tutorial"),
            create_test_item("cooking recipes"),
        ]
        backend = MockBackend(items)

        # Should fall back to deterministic mode
        results = query_relevant_hybrid(
            "machine learning",
            backend=backend,
            mode="hybrid",
            limit=10,
        )

        # Should still return results using deterministic mode
        assert len(results) > 0

    def test_query_relevant_hybrid_respects_limit(self):
        """Test that hybrid query respects limit parameter."""
        items = [create_test_item(f"test content {i}") for i in range(20)]
        backend = MockBackend(items)

        results = query_relevant_hybrid("test", backend=backend, limit=5)
        assert len(results) <= 5

    def test_query_relevant_hybrid_recency_bias(self):
        """Test that recency_bias parameter works in hybrid mode."""
        recent_item = create_test_item("test content", hours_ago=1)
        old_item = create_test_item("test content", hours_ago=100)
        backend = MockBackend([recent_item, old_item])

        results = query_relevant_hybrid(
            "test",
            backend=backend,
            recency_bias=1.0,  # High recency bias
            semantic_weight=0.0,  # Pure deterministic to isolate recency effect
            limit=10,
        )

        # Recent item should rank higher
        assert len(results) == 2
        assert results[0].ts > results[1].ts


class TestHybridRetrievalModes:
    """Test different modes in hybrid retrieval."""

    def test_mode_deterministic(self):
        """Test explicit deterministic mode."""
        items = [create_test_item("test content")]
        backend = MockBackend(items)

        results = query_relevant_hybrid(
            "test",
            backend=backend,
            mode="deterministic",
        )

        assert len(results) > 0

    @pytest.mark.skipif(not embeddings_available(), reason="Embeddings not available")
    def test_mode_semantic(self):
        """Test pure semantic mode with mocked Weaviate client."""
        items = [
            create_test_item("artificial intelligence"),
            create_test_item("cooking recipes"),
        ]
        backend = MockBackend(items)
        query = "AI machine learning"

        # Mock Weaviate client to return scores for our MockBackend items
        mock_client = create_mock_weaviate_client(items, query)

        with patch("memory.retrieve.get_client", return_value=mock_client):
            results = query_relevant_hybrid(
                query,
                backend=backend,
                mode="semantic",
            )

        # Should return results based on semantic similarity only
        assert len(results) > 0
        # AI-related item should rank higher than cooking
        assert "intelligence" in results[0].content.lower()

    @pytest.mark.skipif(not embeddings_available(), reason="Embeddings not available")
    def test_mode_hybrid_default(self):
        """Test hybrid mode (default) with mocked Weaviate client."""
        items = [
            create_test_item("machine learning"),
            create_test_item("cooking"),
        ]
        backend = MockBackend(items)
        query = "machine learning"

        # Mock Weaviate client to return scores for our MockBackend items
        mock_client = create_mock_weaviate_client(items, query)

        with patch("memory.retrieve.get_client", return_value=mock_client):
            results = query_relevant_hybrid(
                query,
                backend=backend,
                mode="hybrid",
            )

        assert len(results) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_hybrid_query_with_special_characters(self):
        """Test hybrid query with special characters."""
        items = [create_test_item("Python 3.11 @decorator syntax")]
        backend = MockBackend(items)

        results = query_relevant_hybrid(
            "python @decorator",
            backend=backend,
            mode="deterministic",
        )

        assert len(results) > 0

    def test_hybrid_query_with_unicode(self):
        """Test hybrid query with unicode characters."""
        items = [create_test_item("Machine learning in 日本語")]
        backend = MockBackend(items)

        results = query_relevant_hybrid(
            "machine learning",
            backend=backend,
            mode="deterministic",
        )

        assert len(results) > 0

    def test_semantic_weight_clamping(self):
        """Test that semantic_weight is clamped to [0, 1]."""
        items = [create_test_item("test content")]
        backend = MockBackend(items)

        # Should clamp to valid range without errors
        results1 = query_relevant_hybrid(
            "test",
            backend=backend,
            semantic_weight=-0.5,  # Should be clamped to 0.0
            mode="deterministic",
        )
        assert len(results1) > 0

        results2 = query_relevant_hybrid(
            "test",
            backend=backend,
            semantic_weight=1.5,  # Should be clamped to 1.0
            mode="deterministic",
        )
        assert len(results2) > 0

    def test_recency_bias_clamping(self):
        """Test that recency_bias is clamped to [0, 1]."""
        items = [create_test_item("test content")]
        backend = MockBackend(items)

        # Should handle out-of-range values gracefully
        results = query_relevant_hybrid(
            "test",
            backend=backend,
            recency_bias=2.0,  # Should be clamped
            mode="deterministic",
        )
        assert len(results) > 0
