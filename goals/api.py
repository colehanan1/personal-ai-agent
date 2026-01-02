"""Goal tracking API for daily/weekly/monthly goals."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
import re

import yaml
from milton_orchestrator.state_paths import resolve_state_dir

VALID_SCOPES = {"daily", "weekly", "monthly"}
SCHEMA_VERSION = 1


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    return resolve_state_dir(base_dir)


def _now_utc(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _normalize_scope(scope: str) -> str:
    if not scope:
        raise ValueError("scope is required")
    normalized = scope.strip().lower()
    if normalized not in VALID_SCOPES:
        raise ValueError(f"Unsupported scope '{scope}'. Use daily, weekly, or monthly.")
    return normalized


def _normalize_tags(tags: Optional[list[str]]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        value = str(tag).strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered not in cleaned:
            cleaned.append(lowered)
    return cleaned


def _normalize_due_date(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _current_path(scope: str, base_dir: Path) -> Path:
    return base_dir / "goals" / "current" / f"{scope}.yaml"


def _archive_path(scope: str, base_dir: Path) -> Path:
    return base_dir / "goals" / "archive" / f"{scope}.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return {}
    return data


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _load_goals(scope: str, base_dir: Path) -> dict[str, Any]:
    path = _current_path(scope, base_dir)
    data = _load_yaml(path)
    goals = data.get("goals") if isinstance(data.get("goals"), list) else []
    return {
        "schema_version": data.get("schema_version", SCHEMA_VERSION),
        "scope": scope,
        "updated_at": data.get("updated_at"),
        "goals": goals,
    }


def _load_archive(scope: str, base_dir: Path) -> dict[str, Any]:
    path = _archive_path(scope, base_dir)
    data = _load_yaml(path)
    goals = data.get("goals") if isinstance(data.get("goals"), list) else []
    return {
        "schema_version": data.get("schema_version", SCHEMA_VERSION),
        "scope": scope,
        "updated_at": data.get("updated_at"),
        "goals": goals,
    }


def _save_goals(scope: str, base_dir: Path, payload: dict[str, Any], now: datetime) -> None:
    payload["schema_version"] = SCHEMA_VERSION
    payload["scope"] = scope
    payload["updated_at"] = now.isoformat()
    _write_yaml(_current_path(scope, base_dir), payload)


def _save_archive(scope: str, base_dir: Path, payload: dict[str, Any], now: datetime) -> None:
    payload["schema_version"] = SCHEMA_VERSION
    payload["scope"] = scope
    payload["updated_at"] = now.isoformat()
    _write_yaml(_archive_path(scope, base_dir), payload)


def _next_goal_id(scope: str, now: datetime, base_dir: Path) -> str:
    prefix = f"{scope[0]}-{now.strftime('%Y%m%d')}"
    pattern = re.compile(rf"^{re.escape(prefix)}-(\\d+)$")
    max_index = 0

    for dataset in (_load_goals(scope, base_dir), _load_archive(scope, base_dir)):
        for goal in dataset.get("goals", []):
            goal_id = str(goal.get("id", ""))
            match = pattern.match(goal_id)
            if match:
                try:
                    max_index = max(max_index, int(match.group(1)))
                except ValueError:
                    continue

    return f"{prefix}-{max_index + 1:03d}"


def _find_goal(goals: list[dict[str, Any]], goal_id: str) -> tuple[int, dict[str, Any]]:
    for idx, goal in enumerate(goals):
        if str(goal.get("id")) == goal_id:
            return idx, goal
    raise KeyError(f"Goal '{goal_id}' not found")


def add_goal(
    scope: str,
    text: str,
    due_date: Optional[Any] = None,
    tags: Optional[list[str]] = None,
    *,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    scope = _normalize_scope(scope)
    if not text or not str(text).strip():
        raise ValueError("Goal text is required")

    base = _state_dir(base_dir)
    timestamp = _now_utc(now)
    data = _load_goals(scope, base)
    goal_id = _next_goal_id(scope, timestamp, base)

    goal = {
        "id": goal_id,
        "text": str(text).strip(),
        "status": "active",
        "created_at": timestamp.isoformat(),
        "due_date": _normalize_due_date(due_date),
        "tags": _normalize_tags(tags),
    }

    data["goals"].append(goal)
    _save_goals(scope, base, data, timestamp)
    return goal_id


def list_goals(
    scope: str,
    *,
    base_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    scope = _normalize_scope(scope)
    base = _state_dir(base_dir)
    data = _load_goals(scope, base)
    return list(data.get("goals", []))


def complete_goal(
    scope: str,
    goal_id: str,
    *,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    scope = _normalize_scope(scope)
    base = _state_dir(base_dir)
    timestamp = _now_utc(now)

    data = _load_goals(scope, base)
    index, goal = _find_goal(data.get("goals", []), goal_id)

    goal["status"] = "completed"
    goal["completed_at"] = timestamp.isoformat()

    data["goals"].pop(index)
    _save_goals(scope, base, data, timestamp)

    archive = _load_archive(scope, base)
    archive["goals"].append(goal)
    _save_archive(scope, base, archive, timestamp)

    return goal


def defer_goal(
    scope: str,
    goal_id: str,
    new_scope: Optional[str] = None,
    *,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    scope = _normalize_scope(scope)
    base = _state_dir(base_dir)
    timestamp = _now_utc(now)

    data = _load_goals(scope, base)
    index, goal = _find_goal(data.get("goals", []), goal_id)
    data["goals"].pop(index)
    _save_goals(scope, base, data, timestamp)

    if new_scope:
        target_scope = _normalize_scope(new_scope)
    else:
        target_scope = "weekly" if scope == "daily" else "monthly" if scope == "weekly" else "monthly"

    goal["deferred_from"] = scope
    goal["deferred_at"] = timestamp.isoformat()
    goal["status"] = "active"

    target_data = _load_goals(target_scope, base)
    target_data["goals"].append(goal)
    _save_goals(target_scope, base, target_data, timestamp)

    return goal
