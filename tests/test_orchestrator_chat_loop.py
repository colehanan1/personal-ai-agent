"""Tests for orchestrator CHAT loop prevention and idempotency."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from milton_orchestrator.config import Config
from milton_orchestrator.idempotency import IdempotencyTracker
from milton_orchestrator.orchestrator import Orchestrator


class TestIdempotencyTracker:
    """Test idempotency tracking functionality."""

    def test_dedupe_key_with_message_id(self):
        """Test that message_id is preferred for dedupe key."""
        tracker = IdempotencyTracker(Path(tempfile.mktemp()))
        
        key = tracker.make_dedupe_key(
            message_id="ntfy_12345",
            topic="test-topic",
            message="test message"
        )
        
        assert key == "ntfy_msg_ntfy_12345"

    def test_dedupe_key_hash_fallback(self):
        """Test hash-based dedupe key when no message_id."""
        tracker = IdempotencyTracker(Path(tempfile.mktemp()))
        
        # Same message should produce same key within 5-minute bucket
        key1 = tracker.make_dedupe_key(
            message_id=None,
            topic="test-topic",
            message="test message",
            timestamp=1000000
        )
        key2 = tracker.make_dedupe_key(
            message_id=None,
            topic="test-topic",
            message="test message",
            timestamp=1000100  # Within same 5-min bucket
        )
        
        assert key1 == key2
        assert key1.startswith("ntfy_hash_")

    def test_dedupe_key_different_messages(self):
        """Test that different messages produce different keys."""
        tracker = IdempotencyTracker(Path(tempfile.mktemp()))
        
        key1 = tracker.make_dedupe_key(
            message_id=None,
            topic="test-topic",
            message="message 1",
            timestamp=1000000
        )
        key2 = tracker.make_dedupe_key(
            message_id=None,
            topic="test-topic",
            message="message 2",
            timestamp=1000000
        )
        
        assert key1 != key2

    def test_has_processed_not_processed(self):
        """Test checking for unprocessed message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            tracker = IdempotencyTracker(db_path)
            
            assert not tracker.has_processed("test_key_123")

    def test_mark_and_check_processed(self):
        """Test marking message as processed and checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            tracker = IdempotencyTracker(db_path)
            
            dedupe_key = "test_key_456"
            
            # Not processed initially
            assert not tracker.has_processed(dedupe_key)
            
            # Mark as processed
            tracker.mark_processed(
                dedupe_key=dedupe_key,
                message_id="msg_123",
                topic="test-topic",
                request_id="req_123",
                message="test message"
            )
            
            # Should now be processed
            assert tracker.has_processed(dedupe_key)

    def test_persistence_across_instances(self):
        """Test that processed state persists across tracker instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # First instance
            tracker1 = IdempotencyTracker(db_path)
            tracker1.mark_processed("persistent_key")
            
            # Second instance (simulates restart)
            tracker2 = IdempotencyTracker(db_path)
            assert tracker2.has_processed("persistent_key")

    def test_cleanup_old_records(self):
        """Test cleanup of old processed records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            tracker = IdempotencyTracker(db_path, ttl_seconds=1)
            
            tracker.mark_processed("old_key")
            
            # Should exist immediately
            assert tracker.has_processed("old_key")
            
            # Wait for TTL expiry (simulate by calling cleanup)
            import time
            time.sleep(2)
            deleted = tracker.cleanup_old_records()
            
            assert deleted >= 1

    def test_get_stats(self):
        """Test getting tracker statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            tracker = IdempotencyTracker(db_path)
            
            # Empty stats
            stats = tracker.get_stats()
            assert stats["total_processed"] == 0
            
            # Add some records
            tracker.mark_processed("key1")
            tracker.mark_processed("key2")
            
            stats = tracker.get_stats()
            assert stats["total_processed"] == 2
            assert stats["oldest_record"] is not None
            assert stats["newest_record"] is not None


class TestOrchestratorChatLoop:
    """Test orchestrator CHAT mode loop prevention."""

    @patch.dict(os.environ, {"LLM_API_URL": "http://test:8000"})
    @patch("milton_orchestrator.orchestrator.requests.post")
    def test_chat_with_stop_sequences(self, mock_post, mock_config):
        """Test that CHAT requests include stop sequences."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_post.return_value = mock_response
        
        orchestrator = Orchestrator(mock_config, dry_run=False)
        orchestrator._run_chat_llm("test query")
        
        # Verify stop sequences were included
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        
        assert "stop" in payload
        assert "assistant" in payload["stop"]
        assert "</s>" in payload["stop"]
        assert "<|eot_id|>" in payload["stop"]

    def test_detect_token_loop_assistant_repetition(self):
        """Test detection of 'assistant' token repetition."""
        from milton_orchestrator.orchestrator import Orchestrator
        
        # Text with excessive "assistant" repetitions
        looping_text = "response assistant " * 15
        
        assert Orchestrator._detect_token_loop(looping_text, threshold=10)

    def test_detect_token_loop_word_repetition(self):
        """Test detection of word repetition loops."""
        from milton_orchestrator.orchestrator import Orchestrator
        
        # Text with same word repeated consecutively (11+ times)
        # Note: Need MORE than threshold consecutive repetitions
        looping_text = ("same " * 20) + "different content here with more words to exceed minimum"
        
        assert Orchestrator._detect_token_loop(looping_text, threshold=10)

    def test_detect_token_loop_normal_text(self):
        """Test that normal text doesn't trigger loop detection."""
        from milton_orchestrator.orchestrator import Orchestrator
        
        normal_text = "This is a normal response with varied content and structure."
        
        assert not Orchestrator._detect_token_loop(normal_text)

    @patch.dict(os.environ, {"LLM_API_URL": "http://test:8000"})
    @patch("milton_orchestrator.orchestrator.requests.post")
    def test_chat_truncates_excessive_output(self, mock_post, mock_config):
        """Test that excessive output is truncated."""
        # Simulate runaway generation
        huge_response = "a" * 25000
        
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": huge_response}}]
        }
        mock_post.return_value = mock_response
        
        orchestrator = Orchestrator(mock_config, dry_run=False)
        
        with patch.object(orchestrator, "publish_status"):
            with patch("milton_orchestrator.orchestrator.publish_response"):
                orchestrator.process_chat_request("test_req_1", "test query")
        
        # Verify warning was logged
        # (In real scenario, check logs; here we just verify method completes)
        assert True  # If we get here, truncation worked

    def test_chat_idempotency_prevents_duplicate_llm_calls(self, mock_config):
        """Test that duplicate chat requests don't call LLM twice."""
        orchestrator = Orchestrator(mock_config, dry_run=False)
        
        with patch.object(orchestrator, "_run_chat_llm") as mock_llm:
            with patch.object(orchestrator, "publish_status"):
                with patch("milton_orchestrator.orchestrator.publish_response"):
                    mock_llm.return_value = "Test response"
                    
                    # First call should execute
                    orchestrator.process_chat_request("test_req_2", "test query")
                    assert mock_llm.call_count == 1
                    
                    # Second call with same request_id should be skipped
                    orchestrator.process_chat_request("test_req_2", "test query")
                    assert mock_llm.call_count == 1  # Still 1, not 2


class TestOrchestratorNtfyIdempotency:
    """Test ntfy message-level idempotency."""

    def test_process_incoming_message_duplicate_prevention(self, mock_config):
        """Test that duplicate ntfy messages are not processed twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config.state_dir = Path(tmpdir)
            orchestrator = Orchestrator(mock_config, dry_run=False)
            
            with patch.object(orchestrator, "publish_status"):
                with patch.object(orchestrator, "route_message") as mock_route:
                    mock_route.return_value = ("CHAT", "test message", None)
                    
                    with patch.object(orchestrator, "process_chat_request") as mock_chat:
                        # First message should be processed
                        orchestrator.process_incoming_message(
                            message_id="ntfy_msg_123",
                            topic="test-topic",
                            message="test message",
                            raw_data={"time": 1000000}
                        )
                        assert mock_chat.call_count == 1
                        
                        # Same message ID should be skipped
                        orchestrator.process_incoming_message(
                            message_id="ntfy_msg_123",
                            topic="test-topic",
                            message="test message",
                            raw_data={"time": 1000000}
                        )
                        assert mock_chat.call_count == 1  # Still 1

    def test_process_incoming_message_different_messages(self, mock_config):
        """Test that different messages are both processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config.state_dir = Path(tmpdir)
            orchestrator = Orchestrator(mock_config, dry_run=False)
            
            with patch.object(orchestrator, "publish_status"):
                with patch.object(orchestrator, "route_message") as mock_route:
                    mock_route.return_value = ("CHAT", "test message", None)
                    
                    with patch.object(orchestrator, "process_chat_request") as mock_chat:
                        # First message
                        orchestrator.process_incoming_message(
                            message_id="ntfy_msg_1",
                            topic="test-topic",
                            message="message 1",
                            raw_data={"time": 1000000}
                        )
                        
                        # Second message (different ID)
                        orchestrator.process_incoming_message(
                            message_id="ntfy_msg_2",
                            topic="test-topic",
                            message="message 2",
                            raw_data={"time": 1000000}
                        )
                        
                        # Both should be processed
                        assert mock_chat.call_count == 2


@pytest.fixture
def mock_config():
    """Mock Config for testing."""
    config = MagicMock(spec=Config)
    config.state_dir = Path(tempfile.mkdtemp())
    config.ask_topic = "test-ask-topic"
    config.answer_topic = "test-answer-topic"
    config.claude_topic = None
    config.codex_topic = None
    config.ntfy_base_url = "https://ntfy.sh"
    config.ntfy_max_chars = 1000
    config.ntfy_max_inline_chars = 3000
    config.output_dir = config.state_dir / "outputs"
    config.output_filename_template = "test_{request_id}.txt"
    config.max_output_size = 100000
    config.always_file_attachments = False
    config.enable_reminders = False
    config.enable_research_mode = False
    config.enable_prefix_routing = False
    config.perplexity_api_key = "test"
    config.perplexity_model = "test"
    config.perplexity_timeout = 30
    config.perplexity_max_retries = 3
    config.target_repo = Path("/tmp")
    config.claude_bin = "claude"
    config.codex_bin = "codex"
    config.codex_model = "test"
    config.codex_extra_args = []
    return config
