#!/usr/bin/env python3
"""
Test Weaviate security configuration.

Validates that default configuration binds to localhost only.
"""
import os
import re
from pathlib import Path


def test_docker_compose_binds_to_localhost_by_default():
    """
    Verify docker-compose.yml binds Weaviate to localhost by default.
    
    This prevents accidental network exposure of the vector database.
    """
    compose_file = Path(__file__).parent.parent / "docker-compose.yml"
    content = compose_file.read_text()
    
    # Check that ports use ${WEAVIATE_BIND_HOST:-127.0.0.1} pattern
    # This ensures localhost binding by default with opt-in override
    assert "${WEAVIATE_BIND_HOST:-127.0.0.1}:8080:8080" in content, (
        "docker-compose.yml must bind Weaviate HTTP port to localhost by default"
    )
    assert "${WEAVIATE_BIND_HOST:-127.0.0.1}:50051:50051" in content, (
        "docker-compose.yml must bind Weaviate gRPC port to localhost by default"
    )
    
    # Ensure no unguarded 0.0.0.0 or bare port bindings
    # Pattern like "8080:8080" without host prefix is unsafe
    unsafe_patterns = [
        r'^\s*-\s*"8080:8080"\s*$',
        r'^\s*-\s*"50051:50051"\s*$',
        r'^\s*-\s*"0\.0\.0\.0:8080',
        r'^\s*-\s*"0\.0\.0\.0:50051',
    ]
    
    for line in content.split('\n'):
        for pattern in unsafe_patterns:
            assert not re.match(pattern, line), (
                f"Found unsafe port binding in docker-compose.yml: {line.strip()}"
            )


def test_weaviate_url_defaults_to_localhost():
    """
    Verify WEAVIATE_URL environment variable defaults to localhost in client code.
    
    Checks that memory/backends.py uses localhost as the default.
    """
    backends_file = Path(__file__).parent.parent / "memory" / "backends.py"
    content = backends_file.read_text()
    
    # Verify that probe_weaviate uses localhost default
    # Pattern: url or os.getenv("WEAVIATE_URL") or "http://localhost:8080"
    assert '"http://localhost:8080"' in content, (
        "memory/backends.py must default WEAVIATE_URL to localhost"
    )
    
    # Verify no 0.0.0.0 or non-localhost defaults
    assert '"http://0.0.0.0' not in content, (
        "memory/backends.py must not default to 0.0.0.0"
    )


def test_weaviate_bind_host_override():
    """
    Verify WEAVIATE_BIND_HOST can be explicitly overridden for advanced users.
    
    This allows opt-in network exposure when needed (e.g., multi-host setups).
    """
    compose_file = Path(__file__).parent.parent / "docker-compose.yml"
    content = compose_file.read_text()
    
    # Check that override mechanism exists
    assert "WEAVIATE_BIND_HOST" in content, (
        "docker-compose.yml must support WEAVIATE_BIND_HOST override"
    )
    
    # Check that default is 127.0.0.1
    assert "127.0.0.1" in content, (
        "docker-compose.yml must default to 127.0.0.1 for localhost binding"
    )


def test_env_example_documents_security():
    """
    Verify .env.example documents the security implications of WEAVIATE_BIND_HOST.
    """
    env_example = Path(__file__).parent.parent / ".env.example"
    content = env_example.read_text()
    
    # Check for WEAVIATE_BIND_HOST documentation
    assert "WEAVIATE_BIND_HOST" in content, (
        ".env.example must document WEAVIATE_BIND_HOST"
    )
    
    # Check for security guidance
    security_keywords = ["127.0.0.1", "localhost", "security"]
    found_keywords = [kw for kw in security_keywords if kw.lower() in content.lower()]
    assert len(found_keywords) >= 2, (
        f".env.example must mention security and localhost binding. "
        f"Found keywords: {found_keywords}"
    )
