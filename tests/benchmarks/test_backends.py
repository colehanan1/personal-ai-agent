"""
Tests for benchmark backends.

Hermetic tests with mocked responses. Integration tests guarded by env var.
"""
import os
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

from benchmarks.backends.base import InferenceResult, BenchmarkBackend
from benchmarks.backends.vllm_openai import VLLMOpenAIBackend


class TestInferenceResult:
    """Test InferenceResult dataclass."""
    
    def test_basic_result(self):
        """Test basic result creation."""
        result = InferenceResult(
            prompt="test",
            response="response",
            first_token_latency_ms=50.0,
            total_latency_ms=200.0,
            tokens_per_sec=100.0,
        )
        
        assert result.prompt == "test"
        assert result.response == "response"
        assert result.first_token_latency_ms == 50.0
        assert result.error is None
    
    def test_error_result(self):
        """Test result with error."""
        result = InferenceResult(
            prompt="test",
            response="",
            error="Connection failed",
        )
        
        assert result.error == "Connection failed"
        assert result.response == ""


class TestVLLMOpenAIBackend:
    """Test vLLM OpenAI backend (mocked)."""
    
    def test_initialization(self):
        """Test backend initialization."""
        backend = VLLMOpenAIBackend(
            base_url="http://localhost:8000",
            model_name="test-model",
        )
        
        assert backend.base_url == "http://localhost:8000"
        assert backend.model_name == "test-model"
    
    @patch('requests.get')
    def test_is_available_success(self, mock_get):
        """Test availability check when server is up."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        backend = VLLMOpenAIBackend()
        assert backend.is_available() is True
        assert backend.get_availability_error() is None
    
    @patch('requests.get')
    def test_is_available_connection_error(self, mock_get):
        """Test availability check when server is down."""
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        backend = VLLMOpenAIBackend()
        assert backend.is_available() is False
        assert "Cannot connect" in backend.get_availability_error()
    
    @patch('requests.get')
    def test_is_available_http_error(self, mock_get):
        """Test availability check with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        backend = VLLMOpenAIBackend()
        assert backend.is_available() is False
        assert "500" in backend.get_availability_error()
    
    @patch('requests.post')
    @patch('requests.get')
    def test_run_inference_mocked(self, mock_get, mock_post):
        """Test inference with mocked streaming response."""
        # Mock availability check
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get.return_value = mock_get_response
        
        # Mock streaming response
        mock_response = Mock()
        mock_response.status_code = 200
        
        # Simulate streaming chunks
        chunks = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
            b'data: [DONE]\n',
        ]
        mock_response.iter_lines.return_value = chunks
        mock_post.return_value = mock_response
        
        backend = VLLMOpenAIBackend()
        result = backend.run_inference("test prompt", max_tokens=100)
        
        assert result.error is None
        assert "Hello" in result.response
        assert "world" in result.response
        assert result.first_token_latency_ms is not None
        assert result.total_latency_ms is not None
        assert result.total_latency_ms > 0
    
    @patch('requests.post')
    @patch('requests.get')
    def test_run_inference_timeout(self, mock_get, mock_post):
        """Test inference with timeout."""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get.return_value = mock_get_response
        
        mock_post.side_effect = requests.exceptions.Timeout()
        
        backend = VLLMOpenAIBackend(timeout=10)
        result = backend.run_inference("test prompt")
        
        assert result.error is not None
        assert "timeout" in result.error.lower()
    
    @patch('requests.post')
    @patch('requests.get')
    def test_run_inference_backend_unavailable(self, mock_get, mock_post):
        """Test inference when backend is unavailable."""
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        backend = VLLMOpenAIBackend()
        result = backend.run_inference("test prompt")
        
        assert result.error is not None
        assert "connect" in result.error.lower()
    
    @patch('requests.post')
    @patch('requests.get')
    def test_warmup(self, mock_get, mock_post):
        """Test warmup calls."""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get.return_value = mock_get_response
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [b'data: [DONE]\n']
        mock_post.return_value = mock_response
        
        backend = VLLMOpenAIBackend()
        backend.warmup(num_iterations=3)
        
        # Should have made 3 inference calls
        assert mock_post.call_count == 3
    
    @patch('requests.get')
    def test_get_backend_info(self, mock_get):
        """Test backend info retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "model-1"}, {"id": "model-2"}]
        }
        mock_get.return_value = mock_response
        
        backend = VLLMOpenAIBackend()
        info = backend.get_backend_info()
        
        assert info["backend_type"] == "vllm_openai"
        assert info["base_url"] == "http://localhost:8000"
        assert "available_models" in info
        assert "model-1" in info["available_models"]


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_BENCH"),
    reason="Live backend tests require RUN_LIVE_BENCH=1"
)
class TestVLLMOpenAIBackendLive:
    """
    Integration tests against live backend.
    
    Run with: RUN_LIVE_BENCH=1 pytest tests/benchmarks/test_backends.py
    Requires vLLM server running at http://localhost:8000
    """
    
    def test_live_availability(self):
        """Test availability check against live backend."""
        backend = VLLMOpenAIBackend()
        
        is_available = backend.is_available()
        if not is_available:
            pytest.skip(f"Backend not available: {backend.get_availability_error()}")
        
        assert is_available is True
    
    def test_live_inference(self):
        """Test inference against live backend."""
        backend = VLLMOpenAIBackend()
        
        if not backend.is_available():
            pytest.skip(f"Backend not available: {backend.get_availability_error()}")
        
        result = backend.run_inference(
            prompt="What is 2+2?",
            max_tokens=50,
            temperature=0.0,
        )
        
        assert result.error is None, f"Inference failed: {result.error}"
        assert len(result.response) > 0
        assert result.first_token_latency_ms is not None
        assert result.first_token_latency_ms > 0
        assert result.total_latency_ms is not None
        assert result.total_latency_ms > result.first_token_latency_ms
        assert result.tokens_per_sec is not None
        assert result.tokens_per_sec > 0
    
    def test_live_warmup(self):
        """Test warmup against live backend."""
        backend = VLLMOpenAIBackend()
        
        if not backend.is_available():
            pytest.skip(f"Backend not available: {backend.get_availability_error()}")
        
        # Should complete without error
        backend.warmup(num_iterations=2)
    
    def test_live_backend_info(self):
        """Test backend info retrieval from live backend."""
        backend = VLLMOpenAIBackend()
        
        if not backend.is_available():
            pytest.skip(f"Backend not available: {backend.get_availability_error()}")
        
        info = backend.get_backend_info()
        
        assert "backend_type" in info
        assert "base_url" in info
        assert info["backend_type"] == "vllm_openai"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
