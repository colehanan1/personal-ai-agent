"""Memory backend implementations with JSONL fallback."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

try:
    import weaviate  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    weaviate = None

from .init_db import get_client
from .schema import MemoryItem, ProjectMemory, UserProfile

logger = logging.getLogger(__name__)

SHORT_TERM_FILE = "short_term.jsonl"
LONG_TERM_FILE = "long_term.jsonl"
WEAVIATE_FETCH_LIMIT = 2000


@dataclass
class BackendStatus:
    mode: str
    degraded: bool
    detail: str
    weaviate_available: bool


def repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[1]


def memory_paths(repo_root: Path) -> tuple[Path, Path]:
    base = repo_root / "data" / "memory"
    return base / SHORT_TERM_FILE, base / LONG_TERM_FILE


def ensure_memory_dir(repo_root: Path) -> None:
    base = repo_root / "data" / "memory"
    base.mkdir(parents=True, exist_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    if content:
        content += "\n"
    path.write_text(content)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")


def _serialize_metadata(metadata: Optional[dict[str, Any]]) -> str:
    return json.dumps(metadata or {})


def _deserialize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": value}
    return {"value": value}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def probe_weaviate(url: Optional[str] = None) -> bool:
    base_url = (url or os.getenv("WEAVIATE_URL") or "http://localhost:8080").rstrip("/")
    try:
        response = requests.get(f"{base_url}/v1/meta", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def _should_try_weaviate(repo_root: Path) -> bool:
    forced = os.getenv("MILTON_MEMORY_BACKEND")
    if forced == "jsonl":
        return False
    if forced == "weaviate":
        return True
    if os.getenv("WEAVIATE_URL"):
        return True
    if (repo_root / "docker-compose.yml").exists():
        return True
    return False


def backend_status(repo_root: Optional[Path] = None) -> BackendStatus:
    root = repo_root or repo_root_from_file()
    should_try = _should_try_weaviate(root)
    available = probe_weaviate() if should_try else False

    if should_try and available:
        return BackendStatus(
            mode="weaviate",
            degraded=False,
            detail="Weaviate reachable",
            weaviate_available=True,
        )
    if should_try and not available:
        return BackendStatus(
            mode="jsonl",
            degraded=True,
            detail="Weaviate unavailable; using local JSONL",
            weaviate_available=False,
        )
    return BackendStatus(
        mode="jsonl",
        degraded=False,
        detail="Weaviate not configured; using local JSONL",
        weaviate_available=False,
    )


class JsonlBackend:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.short_path, self.long_path = memory_paths(repo_root)

    def append_short_term(self, item: MemoryItem) -> str:
        ensure_memory_dir(self.repo_root)
        record = {"record_type": "memory_item", "data": item.model_dump(mode="json")}
        _append_jsonl(self.short_path, record)
        return item.id

    def list_short_term(self) -> list[MemoryItem]:
        records = _read_jsonl(self.short_path)
        items: list[MemoryItem] = []
        for record in records:
            if record.get("record_type") != "memory_item":
                continue
            data = record.get("data", {})
            try:
                items.append(MemoryItem.model_validate(data))
            except Exception:
                continue
        return items

    def delete_short_term_before(self, cutoff: datetime) -> int:
        records = _read_jsonl(self.short_path)
        kept: list[dict[str, Any]] = []
        removed = 0
        for record in records:
            if record.get("record_type") != "memory_item":
                kept.append(record)
                continue
            try:
                item = MemoryItem.model_validate(record.get("data", {}))
            except Exception:
                kept.append(record)
                continue
            if item.ts < cutoff:
                removed += 1
                continue
            kept.append(record)
        if removed:
            ensure_memory_dir(self.repo_root)
            _write_jsonl(self.short_path, kept)
        return removed

    def get_user_profile(self) -> Optional[UserProfile]:
        records = _read_jsonl(self.long_path)
        profiles: list[UserProfile] = []
        for record in records:
            if record.get("record_type") != "user_profile":
                continue
            try:
                profiles.append(UserProfile.model_validate(record.get("data", {})))
            except Exception:
                continue
        if not profiles:
            return None
        return max(profiles, key=lambda profile: profile.last_updated)

    def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        ensure_memory_dir(self.repo_root)
        record = {"record_type": "user_profile", "data": profile.model_dump(mode="json")}
        _append_jsonl(self.long_path, record)
        return profile

    def upsert_project_memory(self, project: ProjectMemory) -> ProjectMemory:
        ensure_memory_dir(self.repo_root)
        record = {
            "record_type": "project_memory",
            "data": project.model_dump(mode="json"),
        }
        _append_jsonl(self.long_path, record)
        return project

    def list_project_memories(self) -> list[ProjectMemory]:
        records = _read_jsonl(self.long_path)
        projects: list[ProjectMemory] = []
        for record in records:
            if record.get("record_type") != "project_memory":
                continue
            try:
                projects.append(ProjectMemory.model_validate(record.get("data", {})))
            except Exception:
                continue
        return projects


class WeaviateBackend:
    def __init__(self, client: Any):
        self.client = client
        self._owns_client = False  # Track if we should close the client

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close client if we own it."""
        if self._owns_client and self.client:
            self.client.close()

    def close(self):
        """Explicitly close the client if we own it."""
        if self._owns_client and self.client:
            self.client.close()

    def append_short_term(self, item: MemoryItem) -> str:
        collection = self.client.collections.get("ShortTermMemory")
        memory_id = collection.data.insert(
            properties={
                "timestamp": item.ts.isoformat(),
                "agent": item.agent,
                "content": item.content,
                "context": item.type,
                "metadata": _serialize_metadata(
                    {
                        "type": item.type,
                        "tags": item.tags,
                        "importance": item.importance,
                        "source": item.source,
                        "request_id": item.request_id,
                        "evidence": item.evidence,
                    }
                ),
            }
        )
        return str(memory_id)

    def list_short_term(self) -> list[MemoryItem]:
        collection = self.client.collections.get("ShortTermMemory")
        query = collection.query.fetch_objects(limit=WEAVIATE_FETCH_LIMIT)
        items: list[MemoryItem] = []
        for obj in query.objects:
            props = obj.properties or {}
            metadata = _deserialize_metadata(props.get("metadata"))
            parsed_ts = _parse_timestamp(props.get("timestamp"))
            if not parsed_ts:
                continue
            data = {
                "id": str(obj.uuid),
                "ts": parsed_ts,
                "agent": props.get("agent") or "unknown",
                "type": metadata.get("type") or "crumb",
                "content": props.get("content") or "",
                "tags": metadata.get("tags") or [],
                "importance": metadata.get("importance", 0.5),
                "source": metadata.get("source") or "weaviate",
                "request_id": metadata.get("request_id"),
                "evidence": metadata.get("evidence") or [],
            }
            try:
                items.append(MemoryItem.model_validate(data))
            except Exception:
                continue
        return items

    def delete_short_term_before(self, cutoff: datetime) -> int:
        collection = self.client.collections.get("ShortTermMemory")
        query = collection.query.fetch_objects(limit=WEAVIATE_FETCH_LIMIT)
        deleted = 0
        for obj in query.objects:
            props = obj.properties or {}
            parsed_ts = _parse_timestamp(props.get("timestamp"))
            if parsed_ts and parsed_ts < cutoff:
                collection.data.delete_by_id(obj.uuid)
                deleted += 1
        return deleted

    def get_user_profile(self) -> Optional[UserProfile]:
        collection = self.client.collections.get("LongTermMemory")
        query = collection.query.fetch_objects(limit=WEAVIATE_FETCH_LIMIT)
        profiles: list[UserProfile] = []
        for obj in query.objects:
            props = obj.properties or {}
            if props.get("category") != "user_profile":
                continue
            metadata = _deserialize_metadata(props.get("metadata"))
            data = metadata.get("profile") or {}
            try:
                profiles.append(UserProfile.model_validate(data))
            except Exception:
                continue
        if not profiles:
            return None
        return max(profiles, key=lambda profile: profile.last_updated)

    def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        collection = self.client.collections.get("LongTermMemory")
        summary = (
            "Preferences: "
            + ", ".join(profile.preferences[:5])
            + " | Facts: "
            + ", ".join(profile.stable_facts[:5])
        )
        collection.data.insert(
            properties={
                "timestamp": profile.last_updated.isoformat(),
                "category": "user_profile",
                "summary": summary,
                "importance": 1.0,
                "tags": ["user_profile"],
                "metadata": _serialize_metadata(
                    {"record_type": "user_profile", "profile": profile.model_dump(mode="json")}
                ),
            }
        )
        return profile

    def upsert_project_memory(self, project: ProjectMemory) -> ProjectMemory:
        collection = self.client.collections.get("LongTermMemory")
        summary = (
            f"Goals: {len(project.goals)} | Blockers: {len(project.blockers)} | "
            f"Next steps: {len(project.next_steps)}"
        )
        collection.data.insert(
            properties={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": "project_summary",
                "summary": summary,
                "importance": 0.8,
                "tags": [f"project:{project.project_name}"],
                "metadata": _serialize_metadata(
                    {"record_type": "project_memory", "project": project.model_dump(mode="json")}
                ),
            }
        )
        return project

    def list_project_memories(self) -> list[ProjectMemory]:
        collection = self.client.collections.get("LongTermMemory")
        query = collection.query.fetch_objects(limit=WEAVIATE_FETCH_LIMIT)
        projects: list[ProjectMemory] = []
        for obj in query.objects:
            props = obj.properties or {}
            metadata = _deserialize_metadata(props.get("metadata"))
            if metadata.get("record_type") != "project_memory":
                continue
            data = metadata.get("project") or {}
            try:
                projects.append(ProjectMemory.model_validate(data))
            except Exception:
                continue
        return projects


def get_backend(
    repo_root: Optional[Path] = None, client: Optional[Any] = None
) -> JsonlBackend | WeaviateBackend:
    root = repo_root or repo_root_from_file()
    if client is not None:
        return WeaviateBackend(client)

    forced = os.getenv("MILTON_MEMORY_BACKEND")
    if forced == "jsonl":
        return JsonlBackend(root)

    should_try = _should_try_weaviate(root)
    if should_try and probe_weaviate():
        if weaviate is None:
            logger.warning("Weaviate client not installed; falling back to JSONL.")
            return JsonlBackend(root)
        backend = WeaviateBackend(get_client())
        backend._owns_client = True  # Mark that this backend should close the client
        return backend

    return JsonlBackend(root)
