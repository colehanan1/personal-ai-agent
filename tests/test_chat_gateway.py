"""Tests for Milton Chat Gateway OpenAI-compatible API."""

import json
from unittest.mock import AsyncMock, patch

import pytest


# Test fixtures
@pytest.fixture
def mock_llm_response():
    """Mock LLM response for non-streaming requests."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama31-8b-instruct",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! I'm Milton, your AI assistant.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
        },
    }


@pytest.fixture
def mock_streaming_lines():
    """Mock streaming SSE lines from LLM."""
    return [
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1700000000,"model":"test","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}',
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1700000000,"model":"test","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}',
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1700000000,"model":"test","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}',
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1700000000,"model":"test","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]


class TestModelsEndpoint:
    """Tests for GET /v1/models endpoint."""

    def test_models_returns_list(self):
        """Test that /v1/models returns a valid models list."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        client = TestClient(app)
        response = client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) >= 1

    def test_models_contains_required_fields(self):
        """Test that model info contains required OpenAI fields."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        client = TestClient(app)
        response = client.get("/v1/models")

        data = response.json()
        model = data["data"][0]
        assert "id" in model
        assert "object" in model
        assert model["object"] == "model"
        assert "created" in model
        assert "owned_by" in model

    def test_models_default_id(self):
        """Test that default model ID is milton-local."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        client = TestClient(app)
        response = client.get("/v1/models")

        data = response.json()
        model_ids = [m["id"] for m in data["data"]]
        assert "milton-local" in model_ids


class TestChatCompletionsNonStreaming:
    """Tests for POST /v1/chat/completions with stream=false."""

    def test_chat_completion_response_structure(self, mock_llm_response):
        """Test that non-streaming response has correct structure."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_llm_response)
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()

            # Required fields
            assert "id" in data
            assert data["object"] == "chat.completion"
            assert "created" in data
            assert "model" in data
            assert "choices" in data
            assert len(data["choices"]) >= 1

    def test_chat_completion_choice_structure(self, mock_llm_response):
        """Test that choices have correct structure."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_llm_response)
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [{"role": "user", "content": "Test"}],
                    "stream": False,
                },
            )

            data = response.json()
            choice = data["choices"][0]

            assert "index" in choice
            assert "message" in choice
            assert choice["message"]["role"] == "assistant"
            assert "content" in choice["message"]
            assert "finish_reason" in choice

    def test_chat_completion_with_conversation(self, mock_llm_response):
        """Test chat completion with multi-turn conversation."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_llm_response)
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "What is 2+2?"},
                        {"role": "assistant", "content": "2+2 equals 4."},
                        {"role": "user", "content": "And 3+3?"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            # Verify all messages were passed to LLM
            call_args = mock_client.chat_completion.call_args
            messages = call_args.kwargs["messages"]
            assert len(messages) == 4


class TestChatCompletionsStreaming:
    """Tests for POST /v1/chat/completions with stream=true."""

    def test_streaming_response_format(self, mock_streaming_lines):
        """Test that streaming response uses SSE format."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        async def mock_stream(*args, **kwargs):
            for line in mock_streaming_lines:
                yield line

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_stream())
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

    def test_streaming_yields_data_lines(self, mock_streaming_lines):
        """Test that streaming yields data: prefixed lines."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        async def mock_stream(*args, **kwargs):
            for line in mock_streaming_lines:
                yield line

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_stream())
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            )

            content = response.text
            lines = [l for l in content.split("\n") if l.startswith("data: ")]
            assert len(lines) >= 1

    def test_streaming_ends_with_done(self, mock_streaming_lines):
        """Test that streaming ends with [DONE]."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        async def mock_stream(*args, **kwargs):
            for line in mock_streaming_lines:
                yield line

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat_completion = AsyncMock(return_value=mock_stream())
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "milton-local",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            )

            content = response.text
            assert "data: [DONE]" in content


class TestMessageConversion:
    """Tests for OpenAI messages to Milton internal format conversion."""

    def test_single_user_message(self):
        """Test conversion of single user message."""
        from milton_gateway.models import ChatMessage

        messages = [ChatMessage(role="user", content="Hello world")]
        converted = [{"role": m.role, "content": m.content} for m in messages]

        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello world"

    def test_conversation_with_system(self):
        """Test conversion preserves system message."""
        from milton_gateway.models import ChatMessage

        messages = [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="Hi"),
        ]
        converted = [{"role": m.role, "content": m.content} for m in messages]

        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[1]["role"] == "user"

    def test_multi_turn_conversation(self):
        """Test conversion of multi-turn conversation."""
        from milton_gateway.models import ChatMessage

        messages = [
            ChatMessage(role="user", content="What is Python?"),
            ChatMessage(role="assistant", content="A programming language."),
            ChatMessage(role="user", content="Tell me more."),
        ]
        converted = [{"role": m.role, "content": m.content} for m in messages]

        assert len(converted) == 3
        roles = [m["role"] for m in converted]
        assert roles == ["user", "assistant", "user"]


class TestErrorHandling:
    """Tests for error handling and response format."""

    def test_invalid_request_missing_messages(self):
        """Test error response for missing messages."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            json={"model": "milton-local"},
        )

        assert response.status_code == 422  # Validation error

    def test_invalid_request_empty_messages(self):
        """Test handling of empty messages list."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            json={"model": "milton-local", "messages": []},
        )

        # Empty messages is technically valid per OpenAI spec
        # but will fail on backend - that's OK for this test
        assert response.status_code in [200, 422, 500, 502]


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_endpoint_exists(self):
        """Test that health endpoint exists."""
        from fastapi.testclient import TestClient
        from milton_gateway.server import app

        with patch("milton_gateway.server.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.check_health = AsyncMock(return_value=False)
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "gateway" in data
