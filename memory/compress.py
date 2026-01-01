"""Compression pipeline for Milton memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any

from .backends import get_backend
from .schema import MemoryItem, ProjectMemory
from .store import upsert_user_profile

PROJECT_TAG_PREFIX = "project:"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _project_tags(item: MemoryItem) -> list[str]:
    tags: list[str] = []
    for tag in item.tags:
        if tag.startswith(PROJECT_TAG_PREFIX):
            project_name = tag.split(":", 1)[1].strip()
            if project_name:
                tags.append(project_name)
    return tags


def _bucket_project_item(item: MemoryItem) -> str:
    if "blocker" in item.tags:
        return "blockers"
    if "next_step" in item.tags or "next" in item.tags:
        return "next_steps"
    if "goal" in item.tags:
        return "goals"
    if item.type in {"project"}:
        return "goals"
    if item.type in {"decision"}:
        return "next_steps"
    return "next_steps"


def compress_short_to_long(
    cutoff_hours: int = 48,
    *,
    repo_root: Optional[Path] = None,
    backend: Optional[Any] = None,
) -> dict[str, int]:
    """Summarize older short-term memories into long-term profiles and projects."""
    backend = backend or get_backend(repo_root=repo_root)
    items = backend.list_short_term()
    cutoff = _now_utc() - timedelta(hours=cutoff_hours)

    old_items = [item for item in items if item.ts < cutoff]
    if not old_items:
        return {"compressed": 0, "projects": 0, "profile": 0}

    profile_items = [
        item
        for item in old_items
        if not _project_tags(item)
        and item.type in {"preference", "fact", "decision"}
    ]

    profile_updated = 0
    if profile_items:
        patch = {
            "preferences": [item.content for item in profile_items if item.type == "preference"],
            "stable_facts": [
                item.content for item in profile_items if item.type in {"fact", "decision"}
            ],
            "do_not_assume": [
                item.content
                for item in profile_items
                if "do_not_assume" in item.tags
            ],
        }
        evidence_ids = [item.id for item in profile_items]
        upsert_user_profile(
            patch, evidence_ids, repo_root=repo_root, backend=backend
        )
        profile_updated = 1

    project_map: dict[str, dict[str, list[str]]] = {}
    evidence_map: dict[str, list[str]] = {}
    for item in old_items:
        projects = _project_tags(item)
        if not projects:
            continue
        bucket = _bucket_project_item(item)
        for project_name in projects:
            project_map.setdefault(
                project_name,
                {"goals": [], "blockers": [], "next_steps": []},
            )
            project_map[project_name][bucket].append(item.content)
            evidence_map.setdefault(project_name, []).append(item.id)

    project_count = 0
    for project_name, buckets in project_map.items():
        project = ProjectMemory(
            project_name=project_name,
            goals=buckets.get("goals", []),
            blockers=buckets.get("blockers", []),
            next_steps=buckets.get("next_steps", []),
            evidence_ids=evidence_map.get(project_name, []),
        )
        backend.upsert_project_memory(project)
        project_count += 1

    backend.delete_short_term_before(cutoff)

    return {"compressed": len(old_items), "projects": project_count, "profile": profile_updated}
