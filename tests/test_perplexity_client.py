"""Tests for Perplexity client"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from milton_orchestrator.perplexity_client import (
    PerplexityClient,
    fallback_prompt_optimizer,
)


class TestPerplexityClient:
    """Tests for PerplexityClient"""

    @pytest.fixture
    def client(self):
        return PerplexityClient(
            api_key="test_key",
            model="sonar-pro",
            timeout=30,
            max_retries=2,
        )

    def test_init(self, client):
        assert client.api_key == "test_key"
        assert client.model == "sonar-pro"
        assert client.timeout == 30
        assert client.max_retries == 2

    @patch("milton_orchestrator.perplexity_client.requests.Session")
    def test_chat_success(self, mock_session_class, client):
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "This is the response"
                    }
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        # Mock session
        mock_session = Mock()
        mock_session.post.return_value = mock_response
        client.session = mock_session

        # Call chat
        messages = [{"role": "user", "content": "test"}]
        result = client.chat(messages)

        assert result == "This is the response"
        mock_session.post.assert_called_once()

    @patch("milton_orchestrator.perplexity_client.requests.Session")
    def test_chat_timeout_with_retry(self, mock_session_class, client):
        import requests

        # Mock session that times out then succeeds
        mock_session = Mock()
        mock_session.post.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            Mock(
                json=lambda: {
                    "choices": [{"message": {"content": "Success after retry"}}]
                },
                raise_for_status=Mock(),
            ),
        ]
        client.session = mock_session

        messages = [{"role": "user", "content": "test"}]
        result = client.chat(messages)

        assert result == "Success after retry"
        assert mock_session.post.call_count == 2

    @patch("milton_orchestrator.perplexity_client.requests.Session")
    def test_chat_all_retries_fail(self, mock_session_class, client):
        import requests

        mock_session = Mock()
        mock_session.post.side_effect = requests.exceptions.Timeout("Timeout")
        client.session = mock_session

        messages = [{"role": "user", "content": "test"}]
        result = client.chat(messages)

        assert result is None
        assert mock_session.post.call_count == client.max_retries

    @patch("milton_orchestrator.perplexity_client.requests.Session")
    def test_chat_malformed_response(self, mock_session_class, client):
        mock_response = Mock()
        mock_response.json.return_value = {"invalid": "structure"}
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        client.session = mock_session

        messages = [{"role": "user", "content": "test"}]
        result = client.chat(messages)

        assert result is None

    @patch.object(PerplexityClient, "chat")
    def test_research_and_optimize(self, mock_chat, client):
        mock_chat.return_value = "Optimized specification"

        result = client.research_and_optimize(
            "Add login feature",
            "/path/to/repo",
        )

        assert result == "Optimized specification"
        mock_chat.assert_called_once()

        # Check that messages were passed
        call_args = mock_chat.call_args
        messages = call_args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Add login feature" in messages[1]["content"]


class TestFallbackOptimizer:
    """Tests for fallback prompt optimizer"""

    def test_basic_optimization(self):
        result = fallback_prompt_optimizer(
            "Add a new feature",
            "/path/to/repo",
        )

        assert "Specification" in result
        assert "Objective" in result
        assert "Add a new feature" in result
        assert "/path/to/repo" in result

    def test_detects_test_request(self):
        result = fallback_prompt_optimizer(
            "Write tests for the auth module",
            "/repo",
        )

        assert "pytest" in result
        assert "tests pass" in result

    def test_detects_bug_fix(self):
        result = fallback_prompt_optimizer(
            "Fix the login bug",
            "/repo",
        )

        assert "Bug Fix" in result

    def test_detects_feature(self):
        result = fallback_prompt_optimizer(
            "Implement new dashboard",
            "/repo",
        )

        assert "Feature" in result

    def test_includes_implementation_plan(self):
        result = fallback_prompt_optimizer("Do something", "/repo")

        assert "Implementation Plan" in result
        assert "Analyze existing code" in result
        assert "Implement required changes" in result

    def test_includes_deliverables(self):
        result = fallback_prompt_optimizer("Task", "/repo")

        assert "Deliverables" in result
        assert "Modified/new files" in result
