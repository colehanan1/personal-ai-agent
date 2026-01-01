"""Storage API for Milton memory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from .backends import get_backend
from .schema import MemoryItem, UserProfile


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def add_memory(
    item: MemoryItem, *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> str:
    """Add a memory item to short-term storage."""
    if not isinstance(item, MemoryItem):
        item = MemoryItem.model_validate(item)
    backend = backend or get_backend(repo_root=repo_root)
    return backend.append_short_term(item)


def get_user_profile(
    *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> UserProfile:
    """Return the latest user profile, or an empty profile."""
    backend = backend or get_backend(repo_root=repo_root)
    profile = backend.get_user_profile()
    if profile is None:
        profile = UserProfile()
    return profile


def upsert_user_profile(
    patch: dict, evidence_ids: list[str], *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> UserProfile:
    """Merge a profile patch with evidence and append as a new profile version."""
    if not evidence_ids:
        raise ValueError("evidence_ids must be provided for profile updates")

    backend = backend or get_backend(repo_root=repo_root)
    base = backend.get_user_profile() or UserProfile()

    allowed = {"preferences", "stable_facts", "do_not_assume"}
    unknown = set(patch) - allowed
    if unknown:
        raise ValueError(f"Unsupported profile fields: {sorted(unknown)}")

    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    updates = {key: _as_list(patch.get(key)) for key in allowed}

    merged = UserProfile(
        preferences=base.preferences + updates["preferences"],
        stable_facts=base.stable_facts + updates["stable_facts"],
        do_not_assume=base.do_not_assume + updates["do_not_assume"],
        last_updated=_now_utc(),
        evidence_ids=base.evidence_ids + evidence_ids,
    )
    return backend.upsert_user_profile(merged)
