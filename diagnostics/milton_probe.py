"""Probe Milton storage and local services."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import os
import time
import urllib.error
import urllib.request

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "cache",
    "models",
    "outputs",
}


@dataclass
class ProbeResult:
    root: str
    weaviate: Dict[str, Any]
    sqlite: Dict[str, Any]
    json_files: Dict[str, Any]
    yaml_files: Dict[str, Any]
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    status: str = "warn"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "weaviate": self.weaviate,
            "sqlite": self.sqlite,
            "json_files": self.json_files,
            "yaml_files": self.yaml_files,
            "notes": self.notes,
            "warnings": self.warnings,
            "errors": self.errors,
            "status": self.status,
        }


@dataclass
class SystemCheckResult:
    status: str
    api_url: str
    latency_ms: float | None = None
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "api_url": self.api_url,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def _scan_extensions(root: Path, extensions: Tuple[str, ...], limit: int) -> Tuple[int, List[str]]:
    total = 0
    samples: List[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if _should_skip(path):
            continue
        if path.suffix.lower() in extensions:
            total += 1
            if len(samples) < limit:
                samples.append(str(path.relative_to(root)))
    return total, samples


def _detect_weaviate(root: Path) -> Dict[str, Any]:
    reasons: List[str] = []
    memory_init = root / "memory" / "init_db.py"
    if memory_init.exists():
        reasons.append("memory/init_db.py")

    compose_path = root / "docker-compose.yml"
    if compose_path.exists():
        try:
            content = compose_path.read_text(encoding="utf-8")
            if "weaviate" in content:
                reasons.append("docker-compose.yml")
        except OSError:
            pass

    requirements_path = root / "requirements.txt"
    if requirements_path.exists():
        try:
            content = requirements_path.read_text(encoding="utf-8")
            if "weaviate" in content:
                reasons.append("requirements.txt")
        except OSError:
            pass

    env_url = os.getenv("WEAVIATE_URL")
    return {
        "detected": bool(reasons),
        "reasons": reasons,
        "url": env_url,
    }


def detect_storage(root: Path, sample_limit: int = 20) -> ProbeResult:
    root = root.resolve()
    if not root.exists():
        return ProbeResult(
            root=str(root),
            weaviate={"detected": False, "reasons": [], "url": None},
            sqlite={"count": 0, "samples": []},
            json_files={"count": 0, "samples": []},
            yaml_files={"count": 0, "samples": []},
            errors=["Root path does not exist"],
            status="fail",
        )

    weaviate = _detect_weaviate(root)
    sqlite_count, sqlite_samples = _scan_extensions(root, (".db", ".sqlite", ".sqlite3"), sample_limit)
    json_count, json_samples = _scan_extensions(root, (".json",), sample_limit)
    yaml_count, yaml_samples = _scan_extensions(root, (".yaml", ".yml"), sample_limit)

    notes: List[str] = []
    warnings: List[str] = []
    status = "pass"

    if weaviate["detected"]:
        notes.append("Weaviate memory code detected")
    else:
        warnings.append("Weaviate memory code not detected")

    if sqlite_count == 0 and json_count == 0 and yaml_count == 0:
        warnings.append("No storage files detected in repo")

    if warnings:
        status = "warn"

    return ProbeResult(
        root=str(root),
        weaviate=weaviate,
        sqlite={"count": sqlite_count, "samples": sqlite_samples},
        json_files={"count": json_count, "samples": json_samples},
        yaml_files={"count": yaml_count, "samples": yaml_samples},
        notes=notes,
        warnings=warnings,
        status=status,
    )


def check_api_status(api_url: str, timeout: float = 2.0) -> SystemCheckResult:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "milton-diagnostics"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = (time.perf_counter() - start) * 1000.0
            if resp.status != 200:
                return SystemCheckResult(
                    status="warn",
                    api_url=api_url,
                    latency_ms=latency_ms,
                    warnings=[f"HTTP {resp.status}"],
                )
            payload = resp.read().decode("utf-8")
            try:
                details = json.loads(payload)
            except json.JSONDecodeError:
                details = {"raw": payload[:200]}
            return SystemCheckResult(
                status="pass",
                api_url=api_url,
                latency_ms=latency_ms,
                details=details,
            )
    except urllib.error.URLError as exc:
        return SystemCheckResult(
            status="warn",
            api_url=api_url,
            warnings=["Milton API not reachable"],
            errors=[str(exc)],
        )
    except Exception as exc:
        return SystemCheckResult(
            status="fail",
            api_url=api_url,
            errors=[str(exc)],
        )
