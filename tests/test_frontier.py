"""
Unit tests for FRONTIER discovery agent with mocked external calls.

Tests:
- Cached discovery methods (find_papers_cached, monitor_ai_news_cached)
- Cache TTL behavior
- Graceful degradation (works without API keys)
- DiscoveryResult schema validation
- daily_discovery() integration
"""

import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from agents.frontier import FRONTIER
from agents.frontier_cache import DiscoveryCache
from agents.contracts import DiscoveryResult


@pytest.fixture
def test_cache_dir():
    """Create temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_arxiv_results():
    """Mock arXiv API results."""
    return [
        {
            "id": "2401.12345",
            "arxiv_id": "2401.12345",
            "title": "Deep Learning for fMRI Analysis",
            "authors": ["Smith, J.", "Doe, A."],
            "abstract": "We present a novel approach to fMRI analysis using deep learning...",
            "published": "2024-01-15T10:00:00Z",
            "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
        },
        {
            "id": "2401.54321",
            "arxiv_id": "2401.54321",
            "title": "Brain Imaging with Neural Networks",
            "authors": ["Johnson, B.", "Williams, C."],
            "abstract": "Brain imaging techniques using neural networks for biomedical engineering...",
            "published": "2024-01-14T12:00:00Z",
            "pdf_url": "https://arxiv.org/pdf/2401.54321.pdf",
        },
    ]


@pytest.fixture
def mock_news_results():
    """Mock NewsAPI results."""
    return [
        {
            "title": "Breakthrough in AI Research",
            "url": "https://example.com/ai-breakthrough",
            "published_at": "2024-01-15T08:00:00Z",
            "source": "Tech News",
        },
        {
            "title": "Machine Learning Advances",
            "url": "https://example.com/ml-advances",
            "published_at": "2024-01-14T14:00:00Z",
            "source": "Science Daily",
        },
    ]


def test_discovery_result_validation():
    """Test DiscoveryResult schema validation with new fields."""
    from agents.contracts import generate_task_id, generate_iso_timestamp

    # Valid result
    result = DiscoveryResult(
        task_id=generate_task_id("test"),
        completed_at=generate_iso_timestamp(),
        agent="frontier",
        query="fMRI research",
        summary="Found 5 papers on fMRI",
        findings=["Paper 1: Novel approach", "Paper 2: Survey"],
        citations=["arxiv:2401.12345", "https://arxiv.org/pdf/2401.54321.pdf"],
        source_timestamps={"arxiv": "2024-01-15T10:00:00"},
        confidence="high",
        papers=[],
        news_items=[],
    )

    assert result.summary == "Found 5 papers on fMRI"
    assert len(result.findings) == 2
    assert len(result.citations) == 2
    assert result.confidence == "high"
    assert "arxiv" in result.source_timestamps


def test_discovery_result_validation_fails():
    """Test DiscoveryResult validation with invalid data."""
    from agents.contracts import generate_task_id, generate_iso_timestamp

    # Missing summary (required)
    with pytest.raises(ValueError, match="summary must be a non-empty string"):
        DiscoveryResult(
            task_id=generate_task_id("test"),
            completed_at=generate_iso_timestamp(),
            agent="frontier",
            query="test",
            summary="",  # Empty summary
        )

    # Invalid confidence level
    with pytest.raises(ValueError, match="confidence must be one of"):
        DiscoveryResult(
            task_id=generate_task_id("test"),
            completed_at=generate_iso_timestamp(),
            agent="frontier",
            query="test",
            summary="Test summary",
            confidence="invalid",  # Not in [low, medium, high]
        )


def test_find_papers_cached_miss_then_hit(test_cache_dir, mock_arxiv_results):
    """Test cache miss followed by cache hit."""
    with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results):
        frontier = FRONTIER()

        # Override cache directory
        from agents.frontier_cache import get_discovery_cache
        cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

        with patch("agents.frontier.get_discovery_cache", return_value=cache):
            # First call: cache miss, should call find_papers
            papers1 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=True)

            assert len(papers1) == 2
            assert "retrieved_at" in papers1[0]
            assert papers1[0]["title"] == "Deep Learning for fMRI Analysis"

            # Second call: cache hit, should NOT call find_papers again
            with patch.object(FRONTIER, "find_papers") as mock_find:
                papers2 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=True)

                # Should not have called find_papers (cache hit)
                mock_find.assert_not_called()

                # Results should match
                assert len(papers2) == 2
                assert papers2[0]["id"] == papers1[0]["id"]
                assert papers2[0]["retrieved_at"] == papers1[0]["retrieved_at"]


def test_find_papers_cached_disabled(mock_arxiv_results):
    """Test that caching can be disabled."""
    with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results) as mock_find:
        frontier = FRONTIER()

        # First call with cache disabled
        papers1 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=False)
        assert mock_find.call_count == 1

        # Second call with cache disabled, should call API again
        papers2 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=False)
        assert mock_find.call_count == 2


def test_monitor_ai_news_cached_graceful_degradation(test_cache_dir):
    """Test graceful degradation when NEWS_API_KEY not set."""
    with patch.dict("os.environ", {}, clear=False):
        # Remove NEWS_API_KEY
        import os
        os.environ.pop("NEWS_API_KEY", None)

        frontier = FRONTIER()

        # Should return empty list without errors
        news = frontier.monitor_ai_news_cached(max_articles=5, use_cache=True)

        assert isinstance(news, list)
        assert len(news) == 0


def test_monitor_ai_news_cached_with_api_key(test_cache_dir, mock_news_results):
    """Test news caching when API key is configured."""
    with patch.dict("os.environ", {"NEWS_API_KEY": "test_key"}):
        with patch.object(FRONTIER, "monitor_ai_news", return_value=mock_news_results):
            frontier = FRONTIER()

            cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

            with patch("agents.frontier.get_discovery_cache", return_value=cache):
                # First call: cache miss
                news1 = frontier.monitor_ai_news_cached(max_articles=5, use_cache=True)

                assert len(news1) == 2
                assert "retrieved_at" in news1[0]

                # Second call: cache hit
                with patch.object(FRONTIER, "monitor_ai_news") as mock_news:
                    news2 = frontier.monitor_ai_news_cached(max_articles=5, use_cache=True)

                    # Should not call API (cache hit)
                    mock_news.assert_not_called()
                    assert len(news2) == 2


def test_cache_ttl_expiration(test_cache_dir, mock_arxiv_results):
    """Test that cached results expire after TTL."""
    with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results):
        frontier = FRONTIER()

        # Short TTL for testing (1 second)
        cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=1/3600)  # 1 second

        with patch("agents.frontier.get_discovery_cache", return_value=cache):
            # First call: populate cache
            papers1 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=True)
            assert len(papers1) == 2

            # Verify cache hit immediately
            with patch.object(FRONTIER, "find_papers") as mock_find:
                papers2 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=True)
                mock_find.assert_not_called()

            # Wait for TTL to expire
            import time
            time.sleep(1.5)

            # Should be cache miss now (expired)
            with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results) as mock_find:
                papers3 = frontier.find_papers_cached("fMRI", max_results=5, use_cache=True)
                mock_find.assert_called_once()


def test_daily_discovery_integration(test_cache_dir, mock_arxiv_results, mock_news_results):
    """Test daily_discovery() with full integration."""
    with patch.dict("os.environ", {"NEWS_API_KEY": "test_key"}):
        with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results):
            with patch.object(FRONTIER, "monitor_ai_news", return_value=mock_news_results):
                frontier = FRONTIER()

                cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

                with patch("agents.frontier.get_discovery_cache", return_value=cache):
                    # Run daily discovery
                    result = frontier.daily_discovery()

                    # Verify DiscoveryResult structure
                    assert isinstance(result, DiscoveryResult)
                    assert result.agent == "frontier"
                    assert result.query == "Daily Discovery"
                    assert result.summary  # Non-empty summary
                    assert len(result.findings) > 0  # Should have findings
                    assert len(result.citations) > 0  # Should have citations
                    assert len(result.source_timestamps) > 0  # Should have timestamps
                    assert result.confidence in ["low", "medium", "high"]

                    # Verify papers and news
                    assert len(result.papers) > 0
                    assert len(result.news_items) > 0

                    # Verify metadata
                    assert "research_interests" in result.metadata
                    assert "cache_enabled" in result.metadata
                    assert result.metadata["cache_enabled"] is True


def test_daily_discovery_without_news(test_cache_dir, mock_arxiv_results):
    """Test daily_discovery() without NEWS_API_KEY (graceful degradation)."""
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("NEWS_API_KEY", None)

        with patch.object(FRONTIER, "find_papers", return_value=mock_arxiv_results):
            frontier = FRONTIER()

            cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

            with patch("agents.frontier.get_discovery_cache", return_value=cache):
                result = frontier.daily_discovery()

                # Should still work without news
                assert isinstance(result, DiscoveryResult)
                assert len(result.papers) > 0
                assert len(result.news_items) == 0  # No news
                assert len(result.citations) > 0  # Still have paper citations
                assert result.metadata["news_api_configured"] is False


def test_daily_discovery_no_results(test_cache_dir):
    """Test daily_discovery() with no papers or news (low confidence)."""
    with patch.object(FRONTIER, "find_papers", return_value=[]):
        with patch.object(FRONTIER, "monitor_ai_news", return_value=[]):
            frontier = FRONTIER()

            cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

            with patch("agents.frontier.get_discovery_cache", return_value=cache):
                result = frontier.daily_discovery()

                # Should have low confidence
                assert result.confidence == "low"
                assert len(result.papers) == 0
                assert len(result.news_items) == 0
                assert result.summary  # Still has summary


def test_cache_key_generation(test_cache_dir):
    """Test that cache keys are deterministic for same queries."""
    cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

    # Same query, same params -> same key
    key1 = cache._generate_cache_key("arxiv", "fMRI", {"max_results": 5})
    key2 = cache._generate_cache_key("arxiv", "fMRI", {"max_results": 5})
    assert key1 == key2

    # Different query -> different key
    key3 = cache._generate_cache_key("arxiv", "brain imaging", {"max_results": 5})
    assert key1 != key3

    # Different params -> different key
    key4 = cache._generate_cache_key("arxiv", "fMRI", {"max_results": 10})
    assert key1 != key4


def test_cache_stats(test_cache_dir, mock_arxiv_results):
    """Test cache statistics tracking."""
    cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

    # Initially empty
    stats = cache.get_stats()
    assert stats["total"] == 0

    # Add some cached data
    cache.set("arxiv", "fMRI", mock_arxiv_results, {"max_results": 5})
    cache.set("arxiv", "brain", mock_arxiv_results, {"max_results": 5})

    stats = cache.get_stats()
    assert stats["total"] == 2
    assert "by_source" in stats
    assert stats["by_source"]["arxiv"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
