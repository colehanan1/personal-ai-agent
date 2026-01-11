"""Tests for _run_chat_llm error handling."""
import pytest
from unittest.mock import patch, MagicMock

from milton_orchestrator.orchestrator import Orchestrator


class TestRunChatLLM:
    """Test _run_chat_llm static method."""

    def test_error_response_surfaces_body(self, monkeypatch):
        """When server returns 400, exception includes response body."""
        # Set up env vars
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("LLM_MODEL", "llama31-8b-instruct")
        monkeypatch.setenv("MILTON_CHAT_MAX_TOKENS", "4000")

        # Mock response with 400 error
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.reason = "Bad Request"
        mock_response.text = '{"error":"max_tokens exceeds context length"}'

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError) as exc_info:
                Orchestrator._run_chat_llm("Hello")

            # Error message should include status, reason, and body
            assert "400" in str(exc_info.value)
            assert "Bad Request" in str(exc_info.value)
            assert "max_tokens exceeds context length" in str(exc_info.value)

    def test_success_returns_content(self, monkeypatch):
        """Successful response returns message content."""
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("LLM_MODEL", "llama31-8b-instruct")
        monkeypatch.setenv("MILTON_CHAT_MAX_TOKENS", "4000")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  Hello there!  "}}]
        }

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            result = Orchestrator._run_chat_llm("Hello")

            assert result == "Hello there!"

    def test_uses_env_model(self, monkeypatch):
        """Uses LLM_MODEL from environment."""
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        monkeypatch.setenv("MILTON_CHAT_MAX_TOKENS", "4000")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            Orchestrator._run_chat_llm("Hello")

            # Verify the model was set correctly in the payload
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["model"] == "custom-model"

    def test_default_model_when_env_unset(self, monkeypatch):
        """Falls back to llama31-8b-instruct when LLM_MODEL not set."""
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("MILTON_CHAT_MAX_TOKENS", "4000")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            Orchestrator._run_chat_llm("Hello")

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["model"] == "llama31-8b-instruct"

    def test_default_max_tokens(self, monkeypatch):
        """Uses default 4000 max_tokens when env var not set."""
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("LLM_MODEL", "llama31-8b-instruct")
        monkeypatch.delenv("MILTON_CHAT_MAX_TOKENS", raising=False)

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            Orchestrator._run_chat_llm("Hello")

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["max_tokens"] == 4000

    def test_auth_header_when_api_key_set(self, monkeypatch):
        """Sends Authorization header when VLLM_API_KEY is set."""
        monkeypatch.setenv("LLM_API_URL", "http://localhost:8000")
        monkeypatch.setenv("LLM_MODEL", "llama31-8b-instruct")
        monkeypatch.setenv("VLLM_API_KEY", "test-key-123")
        monkeypatch.setenv("MILTON_CHAT_MAX_TOKENS", "4000")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        with patch("milton_orchestrator.orchestrator.requests.post") as mock_post:
            mock_post.return_value = mock_response

            Orchestrator._run_chat_llm("Hello")

            call_args = mock_post.call_args
            headers = call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer test-key-123"
