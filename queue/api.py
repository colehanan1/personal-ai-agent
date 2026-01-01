"""File-based overnight job queue API."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import json
import os
import re

PRIORITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    env_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR")
    if env_dir:
        return Path(env_dir)
    return _repo_root()


def _queue_dirs(base_dir: Path) -> tuple[Path, Path]:
    return base_dir / "job_queue" / "tonight", base_dir / "job_queue" / "archive"


def _now_utc(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _normalize_priority(priority: Any) -> str:
    if isinstance(priority, (int, float)):
        if priority >= 2:
            return "high"
        if priority <= 0:
            return "low"
        return "medium"
    text = str(priority or "medium").strip().lower()
    return text if text in PRIORITY_ORDER else "medium"


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _job_file_path(tonight_dir: Path, job_id: str) -> Path:
    return tonight_dir / f"{job_id}.json"


def _next_job_id(now: datetime, base_dir: Path) -> str:
    prefix = f"job-{now.strftime('%Y%m%d')}"
    pattern = re.compile(rf"^{re.escape(prefix)}-(\\d+)$")
    max_index = 0
    tonight_dir, archive_dir = _queue_dirs(base_dir)

    for directory in (tonight_dir, archive_dir):
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            job_id = path.stem
            match = pattern.match(job_id)
            if match:
                try:
                    max_index = max(max_index, int(match.group(1)))
                except ValueError:
                    continue

    return f"{prefix}-{max_index + 1:03d}"


def _read_job(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_job(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def enqueue_job(
    job_type: str,
    payload: dict[str, Any],
    priority: Any = "medium",
    *,
    run_at: Optional[datetime] = None,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    if not job_type or not str(job_type).strip():
        raise ValueError("job_type is required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    base = _state_dir(base_dir)
    timestamp = _now_utc(now)
    scheduled = _parse_iso(run_at) or timestamp
    job_id = _next_job_id(timestamp, base)
    priority_value = _normalize_priority(priority)

    record = {
        "job_id": job_id,
        "type": str(job_type).strip(),
        "payload": payload,
        "priority": priority_value,
        "status": "queued",
        "created_at": timestamp.isoformat(),
        "run_at": scheduled.isoformat(),
        "updated_at": timestamp.isoformat(),
        "artifacts": [],
    }

    if "task" in payload:
        record["task"] = payload["task"]

    tonight_dir, _archive_dir = _queue_dirs(base)
    _write_job(_job_file_path(tonight_dir, job_id), record)
    return job_id


def dequeue_ready_jobs(
    now: Optional[datetime] = None,
    *,
    base_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    base = _state_dir(base_dir)
    timestamp = _now_utc(now)
    tonight_dir, _archive_dir = _queue_dirs(base)
    if not tonight_dir.exists():
        return []

    ready: list[tuple[int, datetime, datetime, str, dict[str, Any], Path]] = []

    for path in tonight_dir.glob("*.json"):
        record = _read_job(path)
        if not record:
            continue
        if record.get("status") not in (None, "queued"):
            continue
        run_at = _parse_iso(record.get("run_at")) or timestamp
        if run_at > timestamp:
            continue
        created_at = _parse_iso(record.get("created_at")) or run_at
        priority = _normalize_priority(record.get("priority"))
        priority_rank = PRIORITY_ORDER.get(priority, 1)
        ready.append((priority_rank, run_at, created_at, record.get("job_id", ""), record, path))

    ready.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))

    jobs: list[dict[str, Any]] = []
    for _priority, _run_at, _created_at, _job_id, record, path in ready:
        record["status"] = "in_progress"
        record["updated_at"] = timestamp.isoformat()
        _write_job(path, record)
        jobs.append(record)

    return jobs


def mark_done(
    job_id: str,
    artifact_paths: list[str],
    result: Optional[dict[str, Any]] = None,
    *,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    if not job_id:
        raise ValueError("job_id is required")

    base = _state_dir(base_dir)
    timestamp = _now_utc(now)
    tonight_dir, archive_dir = _queue_dirs(base)
    path = _job_file_path(tonight_dir, job_id)

    record = _read_job(path)
    if record is None:
        raise FileNotFoundError(f"Job '{job_id}' not found in queue")

    record["status"] = "completed"
    record["completed_at"] = timestamp.isoformat()
    record["updated_at"] = timestamp.isoformat()
    record["artifacts"] = [str(item) for item in artifact_paths]
    if result is not None:
        record["result"] = result

    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = _job_file_path(archive_dir, job_id)
    _write_job(archive_path, record)
    path.unlink(missing_ok=True)

    return record
