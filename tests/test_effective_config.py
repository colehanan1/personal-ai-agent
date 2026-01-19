"""Tests for centralized effective configuration resolution.

These tests ensure all Milton entrypoints resolve STATE_DIR and config
consistently, preventing "separate brains" issues.

All tests are hermetic (no network, no filesystem side effects).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from milton_orchestrator.effective_config import get_effective_config, EffectiveConfig
from milton_orchestrator.state_paths import resolve_state_dir, DEFAULT_STATE_DIR


class TestStateDirResolution:
    """Test state directory resolution consistency."""

    def test_default_env_gives_expected_default(self):
        """Default environment should resolve to ~/.local/state/milton."""
        config = get_effective_config(env={})
        assert config.state_dir == DEFAULT_STATE_DIR
        assert config.state_dir_source == "default"

    def test_milton_state_dir_overrides_default(self):
        """MILTON_STATE_DIR should take precedence."""
        custom_path = "/tmp/custom-milton-state"
        env = {"MILTON_STATE_DIR": custom_path}

        config = get_effective_config(env=env)
        assert config.state_dir == Path(custom_path)
        assert config.state_dir_source == "MILTON_STATE_DIR"

    def test_state_dir_fallback(self):
        """STATE_DIR should be used if MILTON_STATE_DIR not set."""
        custom_path = "/tmp/state-dir-fallback"
        env = {"STATE_DIR": custom_path}

        config = get_effective_config(env=env)
        assert config.state_dir == Path(custom_path)
        assert config.state_dir_source == "STATE_DIR"

    def test_milton_state_dir_takes_precedence_over_state_dir(self):
        """MILTON_STATE_DIR should take precedence over STATE_DIR."""
        milton_path = "/tmp/milton-priority"
        state_path = "/tmp/state-fallback"
        env = {
            "MILTON_STATE_DIR": milton_path,
            "STATE_DIR": state_path,
        }

        config = get_effective_config(env=env)
        assert config.state_dir == Path(milton_path)
        assert config.state_dir_source == "MILTON_STATE_DIR"

    def test_tilde_expansion(self):
        """Paths with ~ should be expanded."""
        env = {"MILTON_STATE_DIR": "~/custom-milton"}
        config = get_effective_config(env=env)

        assert "~" not in str(config.state_dir)
        assert config.state_dir == Path.home() / "custom-milton"


class TestEndpointResolution:
    """Test service endpoint resolution."""

    def test_default_endpoints(self):
        """Default environment should give standard localhost endpoints."""
        config = get_effective_config(env={})

        assert config.milton_api_url == "http://localhost:8001"
        assert config.milton_api_source == "default"

        assert config.gateway_url == "http://localhost:8081"
        assert config.gateway_source == "default"

        assert config.llm_api_url == "http://localhost:8000"
        assert config.llm_api_source == "default"

        assert config.weaviate_url == "http://localhost:8080"
        assert config.weaviate_source == "default"

    def test_custom_endpoints(self):
        """Environment variables should override endpoint defaults."""
        env = {
            "MILTON_API_URL": "http://api.example.com:9001",
            "GATEWAY_URL": "http://gateway.example.com:9081",
            "LLM_API_URL": "http://llm.example.com:9000",
            "WEAVIATE_URL": "http://weaviate.example.com:8080",
        }

        config = get_effective_config(env=env)

        assert config.milton_api_url == "http://api.example.com:9001"
        assert config.milton_api_source == "MILTON_API_URL"

        assert config.gateway_url == "http://gateway.example.com:9081"
        assert config.gateway_source == "GATEWAY_URL"

        assert config.llm_api_url == "http://llm.example.com:9000"
        assert config.llm_api_source == "LLM_API_URL"

        assert config.weaviate_url == "http://weaviate.example.com:8080"
        assert config.weaviate_source == "WEAVIATE_URL"

    def test_llm_url_fallback_to_ollama(self):
        """LLM_API_URL should fall back to OLLAMA_API_URL."""
        env = {"OLLAMA_API_URL": "http://ollama.local:11434"}
        config = get_effective_config(env=env)

        assert config.llm_api_url == "http://ollama.local:11434"
        assert config.llm_api_source == "OLLAMA_API_URL"

    def test_llm_url_precedence(self):
        """LLM_API_URL should take precedence over OLLAMA_API_URL."""
        env = {
            "LLM_API_URL": "http://llm.primary:8000",
            "OLLAMA_API_URL": "http://ollama.fallback:11434",
        }
        config = get_effective_config(env=env)

        assert config.llm_api_url == "http://llm.primary:8000"
        assert config.llm_api_source == "LLM_API_URL"

    def test_trailing_slashes_stripped(self):
        """Trailing slashes should be removed from URLs."""
        env = {
            "MILTON_API_URL": "http://localhost:8001/",
            "GATEWAY_URL": "http://localhost:8081///",
            "LLM_API_URL": "http://localhost:8000/",
        }
        config = get_effective_config(env=env)

        assert not config.milton_api_url.endswith("/")
        assert not config.gateway_url.endswith("/")
        assert not config.llm_api_url.endswith("/")


class TestMemoryBackendResolution:
    """Test memory backend configuration resolution."""

    def test_default_memory_backend(self):
        """Default should be weaviate with auto-detect."""
        config = get_effective_config(env={})
        assert config.memory_backend == "weaviate"
        assert config.memory_backend_source == "auto-detect"

    def test_explicit_memory_backend(self):
        """MILTON_MEMORY_BACKEND should override auto-detection."""
        for backend in ["weaviate", "jsonl", "off"]:
            env = {"MILTON_MEMORY_BACKEND": backend}
            config = get_effective_config(env=env)

            assert config.memory_backend == backend
            assert config.memory_backend_source == "MILTON_MEMORY_BACKEND"

    def test_invalid_memory_backend_warns(self):
        """Invalid memory backend should warn and use default."""
        env = {"MILTON_MEMORY_BACKEND": "invalid-backend"}
        config = get_effective_config(env=env)

        assert config.memory_backend == "weaviate"  # Falls back
        assert len(config.warnings) > 0
        assert "invalid-backend" in config.warnings[0].lower()

    def test_case_insensitive_memory_backend(self):
        """Memory backend should be case-insensitive."""
        env = {"MILTON_MEMORY_BACKEND": "WEAVIATE"}
        config = get_effective_config(env=env)

        assert config.memory_backend == "weaviate"


class TestConsistencyAcrossEntrypoints:
    """Test that different entrypoints resolve config identically."""

    def test_same_env_gives_same_state_dir(self):
        """Same environment should give same state_dir from all paths."""
        env = {"MILTON_STATE_DIR": "/tmp/consistent-state"}

        # Direct call to get_effective_config
        config1 = get_effective_config(env=env)

        # Direct call to resolve_state_dir
        with patch.dict(os.environ, env, clear=True):
            state_dir2 = resolve_state_dir()

        # Both should match
        assert config1.state_dir == state_dir2

    def test_multiple_calls_identical_results(self):
        """Multiple calls with same env should give identical results."""
        env = {
            "MILTON_STATE_DIR": "/tmp/test-state",
            "MILTON_API_URL": "http://localhost:9001",
            "LLM_API_URL": "http://localhost:9000",
        }

        config1 = get_effective_config(env=env)
        config2 = get_effective_config(env=env)

        assert config1.state_dir == config2.state_dir
        assert config1.milton_api_url == config2.milton_api_url
        assert config1.llm_api_url == config2.llm_api_url

    def test_entrypoint_imports_work(self):
        """Verify key entrypoints can import and use effective config."""
        # This tests that imports don't fail (no network calls)
        from milton_orchestrator.effective_config import get_effective_config
        from milton_orchestrator.state_paths import resolve_state_dir

        # Both should be callable
        assert callable(get_effective_config)
        assert callable(resolve_state_dir)


class TestConfigSerialization:
    """Test configuration serialization to dict/JSON."""

    def test_to_dict_includes_all_fields(self):
        """to_dict() should include all configuration fields."""
        config = get_effective_config(env={})
        config_dict = config.to_dict()

        required_fields = [
            "state_dir",
            "state_dir_source",
            "milton_api_url",
            "milton_api_source",
            "gateway_url",
            "gateway_source",
            "llm_api_url",
            "llm_api_source",
            "weaviate_url",
            "weaviate_source",
            "memory_backend",
            "memory_backend_source",
            "warnings",
        ]

        for field in required_fields:
            assert field in config_dict, f"Missing field: {field}"

    def test_to_dict_serializable(self):
        """to_dict() result should be JSON-serializable."""
        import json

        config = get_effective_config(env={})
        config_dict = config.to_dict()

        # Should not raise
        json_str = json.dumps(config_dict)
        assert isinstance(json_str, str)

    def test_state_dir_as_string_in_dict(self):
        """State dir should be converted to string in dict."""
        config = get_effective_config(env={})
        config_dict = config.to_dict()

        assert isinstance(config_dict["state_dir"], str)
        assert not isinstance(config_dict["state_dir"], Path)


class TestWarnings:
    """Test configuration warning generation."""

    def test_no_warnings_for_valid_config(self):
        """Valid configuration should produce no warnings."""
        config = get_effective_config(env={})
        assert config.warnings == []

    def test_warnings_for_invalid_memory_backend(self):
        """Invalid memory backend should generate warning."""
        env = {"MILTON_MEMORY_BACKEND": "bad-backend"}
        config = get_effective_config(env=env)

        assert len(config.warnings) > 0
        assert any("MILTON_MEMORY_BACKEND" in w for w in config.warnings)


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_env_dict(self):
        """Empty environment dict should work (all defaults)."""
        config = get_effective_config(env={})

        assert config.state_dir == DEFAULT_STATE_DIR
        assert config.milton_api_url == "http://localhost:8001"
        assert config.warnings == []

    def test_none_env_uses_os_environ(self):
        """Passing env=None should use os.environ."""
        # This test just verifies it doesn't crash
        with patch.dict(os.environ, {"MILTON_STATE_DIR": "/tmp/test"}, clear=True):
            config = get_effective_config(env=None)
            assert config.state_dir == Path("/tmp/test")

    def test_path_with_spaces(self):
        """Paths with spaces should be handled correctly."""
        env = {"MILTON_STATE_DIR": "/tmp/path with spaces/milton"}
        config = get_effective_config(env=env)

        assert config.state_dir == Path("/tmp/path with spaces/milton")

    def test_relative_path_resolution(self):
        """Relative paths should be handled (though not recommended)."""
        env = {"MILTON_STATE_DIR": "./relative/milton"}
        config = get_effective_config(env=env)

        # Should be a Path object
        assert isinstance(config.state_dir, Path)
