"""Centralized configuration resolution for all Milton entrypoints.

This module provides a single source of truth for:
- State directory resolution
- Service endpoint URLs
- Memory backend configuration
- Configuration diagnostics

All Milton entrypoints (API server, gateway, CLI tools, etc.) should use
get_effective_config() to ensure consistent "brain" state across the system.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from .state_paths import resolve_state_dir, DEFAULT_STATE_DIR


@dataclass
class EffectiveConfig:
    """Complete effective configuration for Milton."""

    # State and directories
    state_dir: Path
    state_dir_source: str  # "MILTON_STATE_DIR" | "STATE_DIR" | "default"

    # Service endpoints
    milton_api_url: str
    milton_api_source: str
    gateway_url: str
    gateway_source: str
    llm_api_url: str
    llm_api_source: str
    weaviate_url: str
    weaviate_source: str

    # Memory configuration
    memory_backend: str  # "weaviate" | "jsonl" | "off"
    memory_backend_source: str

    # Warnings (empty if no issues)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state_dir": str(self.state_dir),
            "state_dir_source": self.state_dir_source,
            "milton_api_url": self.milton_api_url,
            "milton_api_source": self.milton_api_source,
            "gateway_url": self.gateway_url,
            "gateway_source": self.gateway_source,
            "llm_api_url": self.llm_api_url,
            "llm_api_source": self.llm_api_source,
            "weaviate_url": self.weaviate_url,
            "weaviate_source": self.weaviate_source,
            "memory_backend": self.memory_backend,
            "memory_backend_source": self.memory_backend_source,
            "warnings": self.warnings,
        }


def get_effective_config(env: Optional[Mapping[str, str]] = None) -> EffectiveConfig:
    """
    Resolve effective configuration from environment variables.

    This is the single source of truth for configuration resolution.
    All Milton entrypoints should call this function.

    Args:
        env: Environment variables mapping (defaults to os.environ)

    Returns:
        EffectiveConfig with all resolved values and sources

    Precedence rules:
    - State dir: MILTON_STATE_DIR > STATE_DIR > ~/.local/state/milton
    - API URL: MILTON_API_URL > default http://localhost:8001
    - Gateway URL: GATEWAY_URL > default http://localhost:8081
    - LLM URL: LLM_API_URL > OLLAMA_API_URL > default http://localhost:8000
    - Weaviate URL: WEAVIATE_URL > default http://localhost:8080
    - Memory backend: MILTON_MEMORY_BACKEND > detect from weaviate presence
    """
    if env is None:
        env = os.environ

    warnings: list[str] = []

    # Resolve state directory
    milton_state = env.get("MILTON_STATE_DIR")
    state_env = env.get("STATE_DIR")

    if milton_state:
        state_dir = Path(milton_state).expanduser().resolve()
        state_dir_source = "MILTON_STATE_DIR"
    elif state_env:
        state_dir = Path(state_env).expanduser().resolve()
        state_dir_source = "STATE_DIR"
    else:
        state_dir = DEFAULT_STATE_DIR
        state_dir_source = "default"

    # Resolve service endpoints
    milton_api_url = env.get("MILTON_API_URL", "http://localhost:8001").rstrip("/")
    milton_api_source = "MILTON_API_URL" if "MILTON_API_URL" in env else "default"

    gateway_url = env.get("GATEWAY_URL", "http://localhost:8081").rstrip("/")
    gateway_source = "GATEWAY_URL" if "GATEWAY_URL" in env else "default"

    # LLM URL with fallback chain
    llm_api_url = env.get("LLM_API_URL") or env.get("OLLAMA_API_URL", "http://localhost:8000")
    llm_api_url = llm_api_url.rstrip("/")
    if "LLM_API_URL" in env:
        llm_api_source = "LLM_API_URL"
    elif "OLLAMA_API_URL" in env:
        llm_api_source = "OLLAMA_API_URL"
    else:
        llm_api_source = "default"

    weaviate_url = env.get("WEAVIATE_URL", "http://localhost:8080").rstrip("/")
    weaviate_source = "WEAVIATE_URL" if "WEAVIATE_URL" in env else "default"

    # Resolve memory backend
    memory_backend_env = env.get("MILTON_MEMORY_BACKEND")
    if memory_backend_env:
        memory_backend = memory_backend_env.lower()
        memory_backend_source = "MILTON_MEMORY_BACKEND"
        if memory_backend not in ("weaviate", "jsonl", "off"):
            warnings.append(
                f"Invalid MILTON_MEMORY_BACKEND={memory_backend_env}. "
                f"Valid values: weaviate, jsonl, off. Using 'weaviate' as default."
            )
            memory_backend = "weaviate"
    else:
        # Auto-detect based on whether weaviate is configured
        if weaviate_source != "default":
            memory_backend = "weaviate"
        else:
            memory_backend = "weaviate"  # Default to weaviate
        memory_backend_source = "auto-detect"

    # Check for common misconfigurations
    if state_dir_source == "default":
        # This is normal, not a warning
        pass

    return EffectiveConfig(
        state_dir=state_dir,
        state_dir_source=state_dir_source,
        milton_api_url=milton_api_url,
        milton_api_source=milton_api_source,
        gateway_url=gateway_url,
        gateway_source=gateway_source,
        llm_api_url=llm_api_url,
        llm_api_source=llm_api_source,
        weaviate_url=weaviate_url,
        weaviate_source=weaviate_source,
        memory_backend=memory_backend,
        memory_backend_source=memory_backend_source,
        warnings=warnings,
    )


def print_effective_config(config: EffectiveConfig) -> None:
    """Print effective configuration in human-readable format."""
    print("\n╔═══════════════════════════════════════════════════════════════════════╗")
    print("║                    MILTON EFFECTIVE CONFIGURATION                     ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝\n")

    # State directory
    print("STATE DIRECTORY")
    print(f"  Path:   {config.state_dir}")
    print(f"  Source: {config.state_dir_source}")
    print()

    # Service endpoints
    print("SERVICE ENDPOINTS")
    print(f"  Milton API:  {config.milton_api_url}")
    print(f"               └─ source: {config.milton_api_source}")
    print(f"  Gateway:     {config.gateway_url}")
    print(f"               └─ source: {config.gateway_source}")
    print(f"  LLM:         {config.llm_api_url}")
    print(f"               └─ source: {config.llm_api_source}")
    print(f"  Weaviate:    {config.weaviate_url}")
    print(f"               └─ source: {config.weaviate_source}")
    print()

    # Memory configuration
    print("MEMORY BACKEND")
    print(f"  Backend: {config.memory_backend}")
    print(f"  Source:  {config.memory_backend_source}")
    print()

    # Warnings
    if config.warnings:
        print("⚠️  WARNINGS")
        for warning in config.warnings:
            print(f"  - {warning}")
        print()
