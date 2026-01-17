"""
Hermetic unit tests for milton_doctor.py

Tests URL resolution and messaging without making network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.milton_doctor import (
    EndpointInfo,
    HealthCheckResult,
    check_endpoint_health,
    determine_exit_code,
    get_effective_endpoints,
)


class TestGetEffectiveEndpoints:
    """Tests for endpoint resolution logic."""

    def test_all_defaults(self):
        """Test that defaults are used when no env vars are set."""
        env = {}
        endpoints = get_effective_endpoints(env)

        assert endpoints["api"].url == "http://localhost:8001"
        assert endpoints["api"].source == "default"
        assert endpoints["api"].required is True

        assert endpoints["gateway"].url == "http://localhost:8081"
        assert endpoints["gateway"].source == "default"
        assert endpoints["gateway"].required is False

        assert endpoints["llm"].url == "http://localhost:8000"
        assert endpoints["llm"].source == "default"
        assert endpoints["llm"].required is True

        assert endpoints["weaviate"].url == "http://localhost:8080"
        assert endpoints["weaviate"].source == "default"

    def test_all_env_overrides(self):
        """Test that env vars override defaults."""
        env = {
            "MILTON_API_URL": "http://api.example.com:9001",
            "GATEWAY_URL": "http://gateway.example.com:9081",
            "LLM_API_URL": "http://llm.example.com:9000",
            "WEAVIATE_URL": "http://weaviate.example.com:9080",
        }
        endpoints = get_effective_endpoints(env)

        assert endpoints["api"].url == "http://api.example.com:9001"
        assert endpoints["api"].source == "MILTON_API_URL"

        assert endpoints["gateway"].url == "http://gateway.example.com:9081"
        assert endpoints["gateway"].source == "GATEWAY_URL"

        assert endpoints["llm"].url == "http://llm.example.com:9000"
        assert endpoints["llm"].source == "LLM_API_URL"

        assert endpoints["weaviate"].url == "http://weaviate.example.com:9080"
        assert endpoints["weaviate"].source == "WEAVIATE_URL"

    def test_llm_ollama_fallback(self):
        """Test that OLLAMA_API_URL is used if LLM_API_URL is not set."""
        env = {"OLLAMA_API_URL": "http://ollama.local:11434"}
        endpoints = get_effective_endpoints(env)

        assert endpoints["llm"].url == "http://ollama.local:11434"
        assert endpoints["llm"].source == "OLLAMA_API_URL"

    def test_llm_api_url_takes_precedence(self):
        """Test that LLM_API_URL takes precedence over OLLAMA_API_URL."""
        env = {
            "LLM_API_URL": "http://vllm.local:8000",
            "OLLAMA_API_URL": "http://ollama.local:11434",
        }
        endpoints = get_effective_endpoints(env)

        assert endpoints["llm"].url == "http://vllm.local:8000"
        assert endpoints["llm"].source == "LLM_API_URL"

    def test_trailing_slashes_stripped(self):
        """Test that trailing slashes are removed from URLs."""
        env = {
            "MILTON_API_URL": "http://localhost:8001/",
            "LLM_API_URL": "http://localhost:8000///",
            "WEAVIATE_URL": "http://localhost:8080/",
        }
        endpoints = get_effective_endpoints(env)

        assert endpoints["api"].url == "http://localhost:8001"
        assert endpoints["llm"].url == "http://localhost:8000"
        assert endpoints["weaviate"].url == "http://localhost:8080"

    def test_weaviate_required_when_env_set(self):
        """Test that Weaviate is required when WEAVIATE_URL is set."""
        env = {"WEAVIATE_URL": "http://weaviate.example.com:8080"}
        endpoints = get_effective_endpoints(env)

        assert endpoints["weaviate"].required is True

    def test_weaviate_required_when_docker_compose_exists(self, tmp_path, monkeypatch):
        """Test that Weaviate is required when docker-compose.yml exists."""
        # Create docker-compose.yml in tmp_path
        (tmp_path / "docker-compose.yml").write_text("version: '3'")
        
        # Patch __file__ to be inside tmp_path
        fake_script_path = tmp_path / "scripts" / "milton_doctor.py"
        fake_script_path.parent.mkdir(parents=True, exist_ok=True)
        fake_script_path.write_text("# fake")
        
        # Replace __file__ reference in the module
        import scripts.milton_doctor
        original_file = scripts.milton_doctor.__file__
        try:
            scripts.milton_doctor.__file__ = str(fake_script_path)
            
            env = {}
            endpoints = get_effective_endpoints(env)
            
            assert endpoints["weaviate"].required is True
        finally:
            scripts.milton_doctor.__file__ = original_file

    def test_health_paths(self):
        """Test that health check paths are correctly set."""
        endpoints = get_effective_endpoints({})

        assert endpoints["api"].health_path == "/health"
        assert endpoints["gateway"].health_path == "/health"
        assert endpoints["llm"].health_path == "/v1/models"
        assert endpoints["weaviate"].health_path == "/v1/meta"


class TestCheckEndpointHealth:
    """Tests for health check function (with mocked network calls)."""

    def test_check_healthy_endpoint(self):
        """Test checking a healthy endpoint (200 OK)."""
        endpoint = EndpointInfo(
            name="Test Service",
            url="http://localhost:8000",
            source="default",
            health_path="/health",
            required=True,
        )

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("scripts.milton_doctor.requests.get", return_value=mock_response):
            result = check_endpoint_health(endpoint, timeout=2.0)

        assert result.status == "OK"
        assert result.name == "Test Service"
        assert result.url == "http://localhost:8000/health"
        assert "HTTP 200" in result.detail
        assert result.remediation is None

    def test_check_endpoint_with_auth_required(self):
        """Test checking an endpoint that returns 401 (auth required but up)."""
        endpoint = EndpointInfo(
            name="Test Service",
            url="http://localhost:8000",
            source="default",
            health_path="/v1/models",
            required=True,
        )

        mock_response = Mock()
        mock_response.status_code = 401

        with patch("scripts.milton_doctor.requests.get", return_value=mock_response):
            result = check_endpoint_health(endpoint, timeout=2.0)

        assert result.status == "OK"
        assert "auth required" in result.detail.lower()

    def test_check_endpoint_connection_refused(self):
        """Test checking an endpoint that refuses connections."""
        endpoint = EndpointInfo(
            name="Milton API",
            url="http://localhost:8001",
            source="default",
            health_path="/health",
            required=True,
        )

        with patch(
            "scripts.milton_doctor.requests.get",
            side_effect=Exception("Connection refused")
        ):
            result = check_endpoint_health(endpoint, timeout=2.0)

        assert result.status == "FAIL"
        assert result.remediation is not None
        assert "start_api_server" in result.remediation.lower()

    def test_check_endpoint_timeout(self):
        """Test checking an endpoint that times out."""
        endpoint = EndpointInfo(
            name="LLM",
            url="http://localhost:8000",
            source="default",
            health_path="/v1/models",
            required=True,
        )

        import requests
        with patch(
            "scripts.milton_doctor.requests.get",
            side_effect=requests.exceptions.Timeout("Timeout")
        ):
            result = check_endpoint_health(endpoint, timeout=2.0)

        assert result.status == "FAIL"
        assert "timeout" in result.detail.lower()
        assert result.remediation is not None

    def test_llm_with_api_key_header(self):
        """Test that LLM checks include API key headers when available."""
        endpoint = EndpointInfo(
            name="LLM",
            url="http://localhost:8000",
            source="LLM_API_URL",
            health_path="/v1/models",
            required=True,
        )

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("scripts.milton_doctor.os.getenv", return_value="test-api-key"):
            with patch("scripts.milton_doctor.requests.get", return_value=mock_response) as mock_get:
                result = check_endpoint_health(endpoint, timeout=2.0)

                # Verify Authorization header was included
                call_args = mock_get.call_args
                headers = call_args.kwargs.get("headers", {})
                assert "Authorization" in headers
                assert headers["Authorization"] == "Bearer test-api-key"

        assert result.status == "OK"


class TestDetermineExitCode:
    """Tests for exit code determination logic."""

    def test_all_healthy_returns_zero(self):
        """Test that exit code 0 is returned when all required services are healthy."""
        endpoints = {
            "api": EndpointInfo("Milton API", "http://localhost:8001", "default", "/health", True),
            "llm": EndpointInfo("LLM", "http://localhost:8000", "default", "/v1/models", True),
            "gateway": EndpointInfo("Gateway", "http://localhost:8081", "default", "/health", False),
            "weaviate": EndpointInfo("Weaviate", "http://localhost:8080", "default", "/v1/meta", False),
        }

        results = [
            HealthCheckResult("Milton API", "http://localhost:8001/health", "OK", "HTTP 200"),
            HealthCheckResult("LLM", "http://localhost:8000/v1/models", "OK", "HTTP 200"),
            HealthCheckResult("Gateway", "http://localhost:8081/health", "OK", "HTTP 200"),
            HealthCheckResult("Weaviate", "http://localhost:8080/v1/meta", "OK", "HTTP 200"),
        ]

        exit_code = determine_exit_code(results, endpoints)
        assert exit_code == 0

    def test_api_down_returns_two(self):
        """Test that exit code 2 is returned when API is down."""
        endpoints = {
            "api": EndpointInfo("Milton API", "http://localhost:8001", "default", "/health", True),
            "llm": EndpointInfo("LLM", "http://localhost:8000", "default", "/v1/models", True),
            "gateway": EndpointInfo("Gateway", "http://localhost:8081", "default", "/health", False),
            "weaviate": EndpointInfo("Weaviate", "http://localhost:8080", "default", "/v1/meta", False),
        }

        results = [
            HealthCheckResult("Milton API", "http://localhost:8001/health", "FAIL", "Connection refused"),
            HealthCheckResult("LLM", "http://localhost:8000/v1/models", "OK", "HTTP 200"),
        ]

        exit_code = determine_exit_code(results, endpoints)
        assert exit_code == 2

    def test_llm_down_returns_three(self):
        """Test that exit code 3 is returned when LLM is down."""
        endpoints = {
            "api": EndpointInfo("Milton API", "http://localhost:8001", "default", "/health", True),
            "llm": EndpointInfo("LLM", "http://localhost:8000", "default", "/v1/models", True),
            "gateway": EndpointInfo("Gateway", "http://localhost:8081", "default", "/health", False),
            "weaviate": EndpointInfo("Weaviate", "http://localhost:8080", "default", "/v1/meta", False),
        }

        results = [
            HealthCheckResult("Milton API", "http://localhost:8001/health", "OK", "HTTP 200"),
            HealthCheckResult("LLM", "http://localhost:8000/v1/models", "FAIL", "Connection refused"),
        ]

        exit_code = determine_exit_code(results, endpoints)
        assert exit_code == 3

    def test_weaviate_down_required_returns_four(self):
        """Test that exit code 4 is returned when required Weaviate is down."""
        endpoints = {
            "api": EndpointInfo("Milton API", "http://localhost:8001", "default", "/health", True),
            "llm": EndpointInfo("LLM", "http://localhost:8000", "default", "/v1/models", True),
            "gateway": EndpointInfo("Gateway", "http://localhost:8081", "default", "/health", False),
            "weaviate": EndpointInfo("Weaviate", "http://localhost:8080", "default", "/v1/meta", True),
        }

        results = [
            HealthCheckResult("Milton API", "http://localhost:8001/health", "OK", "HTTP 200"),
            HealthCheckResult("LLM", "http://localhost:8000/v1/models", "OK", "HTTP 200"),
            HealthCheckResult("Weaviate", "http://localhost:8080/v1/meta", "FAIL", "Connection refused"),
        ]

        exit_code = determine_exit_code(results, endpoints)
        assert exit_code == 4

    def test_weaviate_down_optional_returns_zero(self):
        """Test that exit code 0 is returned when optional Weaviate is down."""
        endpoints = {
            "api": EndpointInfo("Milton API", "http://localhost:8001", "default", "/health", True),
            "llm": EndpointInfo("LLM", "http://localhost:8000", "default", "/v1/models", True),
            "gateway": EndpointInfo("Gateway", "http://localhost:8081", "default", "/health", False),
            "weaviate": EndpointInfo("Weaviate", "http://localhost:8080", "default", "/v1/meta", False),
        }

        results = [
            HealthCheckResult("Milton API", "http://localhost:8001/health", "OK", "HTTP 200"),
            HealthCheckResult("LLM", "http://localhost:8000/v1/models", "OK", "HTTP 200"),
            HealthCheckResult("Weaviate", "http://localhost:8080/v1/meta", "FAIL", "Connection refused"),
        ]

        exit_code = determine_exit_code(results, endpoints)
        assert exit_code == 0


class TestRemediation:
    """Tests for remediation message generation."""

    def test_api_remediation(self):
        """Test remediation message for Milton API."""
        endpoint = EndpointInfo(
            name="Milton API",
            url="http://localhost:8001",
            source="default",
            health_path="/health",
            required=True,
        )

        with patch("scripts.milton_doctor.requests.get", side_effect=Exception("Connection refused")):
            result = check_endpoint_health(endpoint, timeout=1.0)

        assert result.remediation is not None
        assert "start_api_server.py" in result.remediation

    def test_llm_remediation_vllm(self):
        """Test remediation message for LLM (vLLM)."""
        endpoint = EndpointInfo(
            name="LLM",
            url="http://localhost:8000",
            source="LLM_API_URL",
            health_path="/v1/models",
            required=True,
        )

        with patch("scripts.milton_doctor.requests.get", side_effect=Exception("Connection refused")):
            result = check_endpoint_health(endpoint, timeout=1.0)

        assert result.remediation is not None
        assert "start_vllm.py" in result.remediation or "LLM_API_URL" in result.remediation

    def test_llm_remediation_ollama(self):
        """Test remediation message for LLM (Ollama)."""
        endpoint = EndpointInfo(
            name="LLM",
            url="http://localhost:11434",
            source="OLLAMA_API_URL",
            health_path="/v1/models",
            required=True,
        )

        with patch("scripts.milton_doctor.requests.get", side_effect=Exception("Connection refused")):
            result = check_endpoint_health(endpoint, timeout=1.0)

        assert result.remediation is not None
        assert "Ollama" in result.remediation

    def test_weaviate_remediation(self):
        """Test remediation message for Weaviate."""
        endpoint = EndpointInfo(
            name="Weaviate",
            url="http://localhost:8080",
            source="default",
            health_path="/v1/meta",
            required=True,
        )

        with patch("scripts.milton_doctor.requests.get", side_effect=Exception("Connection refused")):
            result = check_endpoint_health(endpoint, timeout=1.0)

        assert result.remediation is not None
        assert "docker compose" in result.remediation.lower()

    def test_gateway_remediation(self):
        """Test remediation message for Gateway."""
        endpoint = EndpointInfo(
            name="Gateway",
            url="http://localhost:8081",
            source="default",
            health_path="/health",
            required=False,
        )

        with patch("scripts.milton_doctor.requests.get", side_effect=Exception("Connection refused")):
            result = check_endpoint_health(endpoint, timeout=1.0)

        assert result.remediation is not None
        assert "start_chat_gateway.py" in result.remediation
