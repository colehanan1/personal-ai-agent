"""File-based overnight job queue API."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import json
import logging
import os
import re
import tempfile

from milton_orchestrator.state_paths import resolve_state_dir

PRIORITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

logger = logging.getLogger(__name__)

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - platform dependent
    fcntl = None


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    return resolve_state_dir(base_dir)


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


def _serialize_job(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _append_event(
    record: dict[str, Any],
    event: str,
    timestamp: datetime,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    events = record.setdefault("events", [])
    if not isinstance(events, list):
        events = []
        record["events"] = events
    entry = {
        "timestamp": timestamp.isoformat(),
        "event": event,
        "status": record.get("status"),
    }
    if detail:
        entry.update(detail)
    events.append(entry)


def _next_job_id(now: datetime, base_dir: Path) -> str:
    prefix = f"job-{now.strftime('%Y%m%d')}"
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
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


def _read_job_handle(handle: Any) -> Optional[dict[str, Any]]:
    try:
        handle.seek(0)
        data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_job_handle(handle: Any, payload: dict[str, Any]) -> None:
    data = _serialize_job(payload)
    handle.seek(0)
    handle.write(data)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _write_job(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialize_job(payload)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, path)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@contextmanager
def _locked_file(path: Path, *, mode: str = "r+", blocking: bool = True):
    handle = None
    try:
        handle = path.open(mode)
    except FileNotFoundError:
        yield None
        return
    try:
        if fcntl is not None:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError:
                handle.close()
                yield None
                return
        yield handle
    finally:
        if handle and not handle.closed:
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            handle.close()


@contextmanager
def _queue_lock(base_dir: Path):
    lock_path = base_dir / "job_queue" / ".queue.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _locked_file(lock_path, mode="a+", blocking=True) as handle:
        if handle is None:
            raise RuntimeError("Unable to acquire queue lock")
        yield


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
    priority_value = _normalize_priority(priority)
    job_id: Optional[str] = None

    with _queue_lock(base):
        job_id = _next_job_id(timestamp, base)
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

        _append_event(record, "enqueued", timestamp, {"priority": priority_value})

        tonight_dir, _archive_dir = _queue_dirs(base)
        _write_job(_job_file_path(tonight_dir, job_id), record)

    logger.debug("Enqueued job %s", job_id)
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

    ready: list[tuple[int, datetime, datetime, str, Path]] = []

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
        job_id = record.get("job_id")
        if not job_id:
            continue
        priority = _normalize_priority(record.get("priority"))
        priority_rank = PRIORITY_ORDER.get(priority, 1)
        ready.append((priority_rank, run_at, created_at, job_id, path))

    ready.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))

    jobs: list[dict[str, Any]] = []
    for _priority, _run_at, _created_at, _job_id, path in ready:
        with _locked_file(path, mode="r+", blocking=False) as handle:
            if handle is None:
                continue
            record = _read_job_handle(handle)
            if not record:
                continue
            if record.get("status") not in (None, "queued"):
                continue
            run_at = _parse_iso(record.get("run_at")) or timestamp
            if run_at > timestamp:
                continue
            record["status"] = "in_progress"
            record["updated_at"] = timestamp.isoformat()
            if not record.get("started_at"):
                record["started_at"] = timestamp.isoformat()
            _append_event(record, "claimed", timestamp, {"pid": os.getpid()})
            _write_job_handle(handle, record)
            jobs.append(record)
            logger.debug("Claimed job %s", record.get("job_id"))

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

    with _locked_file(path, mode="r+") as handle:
        if handle is None:
            raise FileNotFoundError(f"Job '{job_id}' not found in queue")

        record = _read_job_handle(handle)
        if record is None:
            raise FileNotFoundError(f"Job '{job_id}' not found in queue")

        record["status"] = "completed"
        record["completed_at"] = timestamp.isoformat()
        record["updated_at"] = timestamp.isoformat()
        record["artifacts"] = [str(item) for item in artifact_paths]
        if result is not None:
            record["result"] = result
        _append_event(record, "completed", timestamp, {"artifact_count": len(artifact_paths)})

        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = _job_file_path(archive_dir, job_id)
        _write_job(archive_path, record)
        path.unlink(missing_ok=True)
    logger.debug("Completed job %s", job_id)
    return record


def mark_failed(
    job_id: str,
    error: Any,
    *,
    base_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    if not job_id:
        raise ValueError("job_id is required")

    base = _state_dir(base_dir)
    timestamp = _now_utc(now)
    tonight_dir, _archive_dir = _queue_dirs(base)
    path = _job_file_path(tonight_dir, job_id)

    with _locked_file(path, mode="r+") as handle:
        if handle is None:
            raise FileNotFoundError(f"Job '{job_id}' not found in queue")

        record = _read_job_handle(handle)
        if record is None:
            raise FileNotFoundError(f"Job '{job_id}' not found in queue")

        record["status"] = "failed"
        record["failed_at"] = timestamp.isoformat()
        record["updated_at"] = timestamp.isoformat()
        record["error"] = str(error)
        _append_event(record, "failed", timestamp, {"error": str(error)})
        _write_job_handle(handle, record)

    logger.debug("Failed job %s", job_id)
    return record
