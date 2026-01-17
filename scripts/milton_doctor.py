#!/usr/bin/env python3
"""
Milton Doctor - Connectivity Diagnostic Tool

Reports Milton's effective endpoints and checks their health status.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


@dataclass
class EndpointInfo:
    """Information about a Milton service endpoint."""

    name: str
    url: str
    source: str  # env var name or "default"
    health_path: str
    required: bool


@dataclass
class HealthCheckResult:
    """Result of checking an endpoint's health."""

    name: str
    url: str
    status: str  # "OK", "FAIL", "SKIP"
    detail: str
    remediation: Optional[str] = None


def get_effective_endpoints(env: Optional[dict] = None) -> dict[str, EndpointInfo]:
    """
    Resolve Milton's effective service endpoints.

    Args:
        env: Environment variables dict (defaults to os.environ)

    Returns:
        Dictionary mapping service names to EndpointInfo objects
    """
    if env is None:
        env = os.environ

    # API Server (Milton REST API)
    api_url = env.get("MILTON_API_URL", "http://localhost:8001").rstrip("/")
    api_source = "MILTON_API_URL" if "MILTON_API_URL" in env else "default"

    # Gateway Server (OpenAI-compatible chat interface)
    gateway_url = env.get("GATEWAY_URL", "http://localhost:8081").rstrip("/")
    gateway_source = "GATEWAY_URL" if "GATEWAY_URL" in env else "default"

    # LLM API (vLLM or Ollama)
    llm_url = env.get("LLM_API_URL") or env.get("OLLAMA_API_URL", "http://localhost:8000")
    llm_url = llm_url.rstrip("/")
    if "LLM_API_URL" in env:
        llm_source = "LLM_API_URL"
    elif "OLLAMA_API_URL" in env:
        llm_source = "OLLAMA_API_URL"
    else:
        llm_source = "default"

    # Weaviate (memory store)
    weaviate_url = env.get("WEAVIATE_URL", "http://localhost:8080").rstrip("/")
    weaviate_source = "WEAVIATE_URL" if "WEAVIATE_URL" in env else "default"

    # Determine if Weaviate is required (exists in env or docker-compose.yml exists)
    repo_root = Path(__file__).resolve().parents[1]
    weaviate_required = "WEAVIATE_URL" in env or (repo_root / "docker-compose.yml").exists()

    return {
        "api": EndpointInfo(
            name="Milton API",
            url=api_url,
            source=api_source,
            health_path="/health",
            required=True,
        ),
        "gateway": EndpointInfo(
            name="Gateway",
            url=gateway_url,
            source=gateway_source,
            health_path="/health",
            required=False,
        ),
        "llm": EndpointInfo(
            name="LLM",
            url=llm_url,
            source=llm_source,
            health_path="/v1/models",
            required=True,
        ),
        "weaviate": EndpointInfo(
            name="Weaviate",
            url=weaviate_url,
            source=weaviate_source,
            health_path="/v1/meta",
            required=weaviate_required,
        ),
    }


def check_endpoint_health(endpoint: EndpointInfo, timeout: float = 2.0) -> HealthCheckResult:
    """
    Check if an endpoint is reachable and healthy.

    Args:
        endpoint: EndpointInfo to check
        timeout: HTTP timeout in seconds

    Returns:
        HealthCheckResult with status and details
    """
    if not endpoint.required:
        # Optional service - check but don't fail hard
        pass

    url = f"{endpoint.url}{endpoint.health_path}"

    # Get API key headers if needed
    headers = {}
    if endpoint.name == "LLM":
        token = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        if token:
            headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code in (200, 401):  # 401 = auth required but service is up
            status_text = "OK" if response.status_code == 200 else "OK (auth required)"
            return HealthCheckResult(
                name=endpoint.name,
                url=url,
                status="OK",
                detail=f"HTTP {response.status_code} - {status_text}",
                remediation=None,
            )
        else:
            return HealthCheckResult(
                name=endpoint.name,
                url=url,
                status="FAIL",
                detail=f"HTTP {response.status_code}",
                remediation=_get_remediation(endpoint),
            )
    except requests.exceptions.ConnectionError:
        return HealthCheckResult(
            name=endpoint.name,
            url=url,
            status="FAIL",
            detail="Connection refused",
            remediation=_get_remediation(endpoint),
        )
    except requests.exceptions.Timeout:
        return HealthCheckResult(
            name=endpoint.name,
            url=url,
            status="FAIL",
            detail=f"Timeout after {timeout}s",
            remediation=_get_remediation(endpoint),
        )
    except Exception as exc:
        return HealthCheckResult(
            name=endpoint.name,
            url=url,
            status="FAIL",
            detail=str(exc),
            remediation=_get_remediation(endpoint),
        )


def _get_remediation(endpoint: EndpointInfo) -> str:
    """Get remediation advice for a failed endpoint check."""
    if endpoint.name == "Milton API":
        return "Start with: python scripts/start_api_server.py"
    elif endpoint.name == "Gateway":
        return "Start with: python scripts/start_chat_gateway.py"
    elif endpoint.name == "LLM":
        if "OLLAMA" in endpoint.source.upper():
            return "Start Ollama or set LLM_API_URL to point to your LLM server"
        return "Start with: python scripts/start_vllm.py OR set LLM_API_URL"
    elif endpoint.name == "Weaviate":
        return "Start with: docker compose up -d"
    return "Check service configuration"


def print_endpoints_table(endpoints: dict[str, EndpointInfo]) -> None:
    """Print a formatted table of effective endpoints."""
    print("\n╔═══════════════════════════════════════════════════════════════════════╗")
    print("║                    MILTON EFFECTIVE ENDPOINTS                         ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝\n")

    # Calculate column widths
    max_name = max(len(ep.name) for ep in endpoints.values())
    max_source = max(len(ep.source) for ep in endpoints.values())

    for key in ["api", "gateway", "llm", "weaviate"]:
        if key not in endpoints:
            continue
        ep = endpoints[key]
        req = "REQUIRED" if ep.required else "optional"
        print(f"  {ep.name:<{max_name}}  {ep.url}")
        print(f"  {'':>{max_name}}  └─ source: {ep.source} ({req})")
        print()


def print_health_results(results: list[HealthCheckResult]) -> None:
    """Print formatted health check results."""
    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║                        HEALTH CHECK RESULTS                           ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝\n")

    for result in results:
        status_icon = "✅" if result.status == "OK" else "❌"
        print(f"{status_icon} {result.name}: {result.status}")
        print(f"   URL: {result.url}")
        print(f"   Detail: {result.detail}")
        if result.remediation:
            print(f"   ⚠️  Remediation: {result.remediation}")
        print()


def determine_exit_code(results: list[HealthCheckResult], endpoints: dict[str, EndpointInfo]) -> int:
    """
    Determine appropriate exit code based on health check results.

    Exit codes:
        0: All required services are healthy
        2: API server is down
        3: LLM is down
        4: Weaviate is down (and required)
    """
    # Build a map of service name to result
    result_map = {r.name: r for r in results}

    # Check critical services
    if result_map.get("Milton API", HealthCheckResult("", "", "FAIL", "")).status == "FAIL":
        return 2

    if result_map.get("LLM", HealthCheckResult("", "", "FAIL", "")).status == "FAIL":
        return 3

    weaviate_result = result_map.get("Weaviate")
    if weaviate_result and endpoints["weaviate"].required and weaviate_result.status == "FAIL":
        return 4

    return 0


def main() -> int:
    """Run the Milton doctor diagnostic."""
    print("\n🩺 MILTON DOCTOR - Connectivity Diagnostic")
    print("=" * 75)

    # Get effective endpoints
    endpoints = get_effective_endpoints()

    # Print endpoint configuration
    print_endpoints_table(endpoints)

    # Run health checks
    print("\n🔍 Running health checks...\n")
    results: list[HealthCheckResult] = []

    for key in ["api", "gateway", "llm", "weaviate"]:
        endpoint = endpoints[key]
        result = check_endpoint_health(endpoint, timeout=2.0)
        results.append(result)

    # Print results
    print_health_results(results)

    # Determine exit code
    exit_code = determine_exit_code(results, endpoints)

    # Print summary
    ok_count = sum(1 for r in results if r.status == "OK")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║                             SUMMARY                                   ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝\n")
    print(f"  ✅ Healthy: {ok_count}")
    print(f"  ❌ Failed:  {fail_count}")
    print(f"  Exit code: {exit_code}")

    if exit_code == 0:
        print("\n✨ All required services are operational!\n")
    else:
        print(f"\n⚠️  Some required services are down (exit code {exit_code})\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
