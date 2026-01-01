"""Healthcheck utilities for Milton runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import os

import requests
from dotenv import load_dotenv

from memory.backends import backend_status


DEFAULT_LLM_URL = "http://localhost:8000"
DEFAULT_WEAVIATE_URL = "http://localhost:8080"

load_dotenv()


@dataclass
class ServiceCheck:
    """Result of a single service check."""

    name: str
    url: str
    status: str
    detail: str
    required: bool


def _api_key_headers() -> dict[str, str]:
    token = (
        os.getenv("LLM_API_KEY")
        or os.getenv("VLLM_API_KEY")
        or os.getenv("OLLAMA_API_KEY")
    )
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _http_check(url: str, headers: Optional[dict[str, str]] = None) -> tuple[bool, str]:
    try:
        response = requests.get(url, headers=headers or {}, timeout=2)
        if response.status_code in (200, 401):
            return True, f"HTTP {response.status_code}"
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def resolve_runtime_urls(repo_root: Path) -> tuple[str, bool, str, bool, bool]:
    """Resolve runtime endpoints and whether they are required."""
    llm_env = os.getenv("LLM_API_URL")
    llm_url = (llm_env or DEFAULT_LLM_URL).rstrip("/")
    llm_defaulted = not llm_env

    weaviate_env = os.getenv("WEAVIATE_URL")
    weaviate_required = bool(weaviate_env) or (repo_root / "docker-compose.yml").exists()
    weaviate_url = (weaviate_env or DEFAULT_WEAVIATE_URL).rstrip("/")
    weaviate_defaulted = not weaviate_env

    return llm_url, llm_defaulted, weaviate_url, weaviate_defaulted, weaviate_required


def check_llm(llm_base_url: str, defaulted: bool = False) -> ServiceCheck:
    url = f"{llm_base_url}/v1/models"
    ok, detail = _http_check(url, headers=_api_key_headers())
    if defaulted:
        detail = f"{detail} (default url)"
    return ServiceCheck(
        name="LLM",
        url=url,
        status="OK" if ok else "FAIL",
        detail=detail,
        required=True,
    )


def check_weaviate(
    weaviate_base_url: str,
    required: bool,
    defaulted: bool,
    repo_root: Path,
) -> ServiceCheck:
    if not required:
        return ServiceCheck(
            name="Weaviate",
            url="n/a",
            status="SKIP",
            detail="WEAVIATE_URL not set and no docker-compose.yml",
            required=False,
        )

    url = f"{weaviate_base_url}/v1/meta"
    ok, detail = _http_check(url)
    if defaulted:
        detail = f"{detail} (default url)"
    if ok:
        return ServiceCheck(
            name="Weaviate",
            url=url,
            status="OK",
            detail=detail,
            required=True,
        )

    status = backend_status(repo_root)
    if status.degraded:
        return ServiceCheck(
            name="Weaviate",
            url=url,
            status="DEGRADED",
            detail=f"{detail}; {status.detail}",
            required=True,
        )

    return ServiceCheck(
        name="Weaviate",
        url=url,
        status="FAIL",
        detail=detail,
        required=True,
    )


def run_checks(repo_root: Optional[Path] = None) -> list[ServiceCheck]:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]

    (
        llm_url,
        llm_defaulted,
        weaviate_url,
        weaviate_defaulted,
        weaviate_required,
    ) = resolve_runtime_urls(repo_root)

    return [
        check_llm(llm_url, defaulted=llm_defaulted),
        check_weaviate(
            weaviate_url,
            required=weaviate_required,
            defaulted=weaviate_defaulted,
            repo_root=repo_root,
        ),
    ]


def overall_ok(checks: Iterable[ServiceCheck]) -> bool:
    ok_statuses = {"OK", "DEGRADED"}
    return all(check.status in ok_statuses for check in checks if check.required)


def format_table(checks: Iterable[ServiceCheck]) -> str:
    rows = [("Component", "Status", "URL", "Detail")]
    for check in checks:
        rows.append((check.name, check.status, check.url, check.detail))

    col_widths = [0, 0, 0, 0]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(cell))

    lines = []
    for idx, row in enumerate(rows):
        padded = "  ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(row)
        )
        lines.append(padded.rstrip())
        if idx == 0:
            lines.append(
                "  ".join("-" * width for width in col_widths).rstrip()
            )
    return "\n".join(lines)
