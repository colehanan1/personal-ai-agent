"""
Unit tests for training data export script.

Tests:
- PII detection patterns
- PII redaction
- Request-result pairing logic
- Chat message formatting
- Train/test splitting
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.export_training_data import (
    contains_pii,
    redact_pii,
    pair_requests_results,
    format_as_chat,
    split_train_test,
    compute_dataset_hash
)
from memory.schema import MemoryItem


class TestPIIDetection:
    """Test PII detection patterns."""

    def test_detects_email(self):
        """Should detect email addresses."""
        assert contains_pii("Contact me at john@example.com") is True
        assert contains_pii("My email is user.name+tag@domain.co.uk") is True
        assert contains_pii("No email here") is False

    def test_detects_phone(self):
        """Should detect phone numbers."""
        assert contains_pii("Call me at 555-123-4567") is True
        assert contains_pii("Phone: (555)123-4567") is True  # No space after paren
        assert contains_pii("My number is +1-555-123-4567") is True
        assert contains_pii("No phone here") is False

    def test_detects_api_key(self):
        """Should detect API keys."""
        assert contains_pii("API key: sk-abcdefghijk12345678901234567890") is True
        assert contains_pii("My pk_12345678901234567890abcdef") is True
        assert contains_pii("token: key-abcd1234efgh5678ijkl9012mnop3456") is True
        assert contains_pii("No API key here") is False

    def test_detects_url_with_token(self):
        """Should detect URLs with tokens."""
        assert contains_pii("https://api.example.com/data?token=abc123") is True
        assert contains_pii("http://site.com/path?api_key=secret") is True
        assert contains_pii("https://example.com/page") is False

    def test_redacts_email(self):
        """Should redact email addresses."""
        text = "Contact john@example.com for info"
        redacted = redact_pii(text)
        assert "[EMAIL]" in redacted
        assert "john@example.com" not in redacted

    def test_redacts_phone(self):
        """Should redact phone numbers."""
        text = "Call 555-123-4567"
        redacted = redact_pii(text)
        assert "[PHONE]" in redacted
        assert "555-123-4567" not in redacted

    def test_redacts_api_key(self):
        """Should redact API keys."""
        text = "Use sk-abc123def456ghi789jkl012mno345pqr678"
        redacted = redact_pii(text)
        assert "[API_KEY]" in redacted
        assert "abc123" not in redacted

    def test_redacts_url_with_token(self):
        """Should redact URLs with tokens."""
        text = "Visit https://api.com/data?token=secret123"
        redacted = redact_pii(text)
        assert "[URL_WITH_TOKEN]" in redacted
        assert "secret123" not in redacted


class TestDataPairing:
    """Test request-result pairing logic."""

    def create_memory_item(
        self,
        item_id: str,
        type_: str,
        content: str,
        request_id: str,
        ts_offset: int = 0
    ) -> MemoryItem:
        """Helper to create MemoryItem for testing."""
        return MemoryItem(
            id=item_id,
            ts=datetime.now(timezone.utc).replace(hour=12 + ts_offset),
            agent="test",
            type=type_,
            content=content,
            tags=[],
            importance=0.5,
            source="test",
            request_id=request_id,
            evidence=[]
        )

    def test_pairs_matching_request_result(self):
        """Should pair request with matching result."""
        items = [
            self.create_memory_item("1", "request", "What is 2+2?", "req1", ts_offset=0),
            self.create_memory_item("2", "result", "2+2 equals 4", "req1", ts_offset=1)
        ]

        pairs = pair_requests_results(items)

        assert len(pairs) == 1
        req, res = pairs[0]
        assert req.content == "What is 2+2?"
        assert res.content == "2+2 equals 4"

    def test_ignores_orphaned_requests(self):
        """Should skip requests without matching results."""
        items = [
            self.create_memory_item("1", "request", "Question 1", "req1"),
            self.create_memory_item("2", "request", "Question 2", "req2"),
            self.create_memory_item("3", "result", "Answer 1", "req1", ts_offset=1)
        ]

        pairs = pair_requests_results(items)

        assert len(pairs) == 1  # Only req1 has a result

    def test_ignores_orphaned_results(self):
        """Should skip results without matching requests."""
        items = [
            self.create_memory_item("1", "result", "Answer without question", "req1")
        ]

        pairs = pair_requests_results(items)

        assert len(pairs) == 0

    def test_pairs_multiple_request_result_pairs(self):
        """Should pair multiple request-result pairs."""
        items = [
            self.create_memory_item("1", "request", "Q1", "req1", ts_offset=0),
            self.create_memory_item("2", "result", "A1", "req1", ts_offset=1),
            self.create_memory_item("3", "request", "Q2", "req2", ts_offset=2),
            self.create_memory_item("4", "result", "A2", "req2", ts_offset=3)
        ]

        pairs = pair_requests_results(items)

        assert len(pairs) == 2

    def test_verifies_timestamp_order(self):
        """Should only pair if result comes after request."""
        items = [
            self.create_memory_item("1", "result", "Answer", "req1", ts_offset=0),
            self.create_memory_item("2", "request", "Question", "req1", ts_offset=1)
        ]

        pairs = pair_requests_results(items)

        assert len(pairs) == 0  # Result before request is invalid

    def test_formats_as_chat_messages(self):
        """Should format pair as chat messages."""
        request = self.create_memory_item("1", "request", "Hello", "req1")
        result = self.create_memory_item("2", "result", "Hi there!", "req1", ts_offset=1)

        formatted = format_as_chat((request, result))

        assert "messages" in formatted
        assert len(formatted["messages"]) == 3  # system, user, assistant

        messages = formatted["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Hi there!"


class TestTrainTestSplit:
    """Test train/test splitting logic."""

    def test_split_ratio(self):
        """Should split according to ratio."""
        data = [{"id": i} for i in range(100)]

        train, test = split_train_test(data, ratio=0.2, seed=42)

        assert len(train) == 80
        assert len(test) == 20

    def test_deterministic_split(self):
        """Should produce same split with same seed."""
        data = [{"id": i} for i in range(100)]

        train1, test1 = split_train_test(data, ratio=0.2, seed=42)
        train2, test2 = split_train_test(data, ratio=0.2, seed=42)

        assert train1 == train2
        assert test1 == test2

    def test_different_seeds_produce_different_splits(self):
        """Different seeds should produce different splits."""
        data = [{"id": i} for i in range(100)]

        train1, test1 = split_train_test(data, ratio=0.2, seed=42)
        train2, test2 = split_train_test(data, ratio=0.2, seed=99)

        assert train1 != train2


class TestDatasetHash:
    """Test dataset hashing for provenance."""

    def test_computes_hash(self):
        """Should compute SHA256 hash of data."""
        data = [{"id": 1, "content": "test"}]

        hash1 = compute_dataset_hash(data)

        assert len(hash1) == 64  # SHA256 hex digest length

    def test_deterministic_hash(self):
        """Same data should produce same hash."""
        data = [{"id": 1, "content": "test"}, {"id": 2, "content": "test2"}]

        hash1 = compute_dataset_hash(data)
        hash2 = compute_dataset_hash(data)

        assert hash1 == hash2

    def test_different_data_different_hash(self):
        """Different data should produce different hash."""
        data1 = [{"id": 1, "content": "test1"}]
        data2 = [{"id": 1, "content": "test2"}]

        hash1 = compute_dataset_hash(data1)
        hash2 = compute_dataset_hash(data2)

        assert hash1 != hash2
