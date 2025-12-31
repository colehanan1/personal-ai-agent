"""Reminder scheduling and persistence for Milton Orchestrator."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Reminder:
    """Stored reminder record."""

    id: int
    kind: str
    message: str
    due_at: int
    created_at: int
    sent_at: Optional[int]
    canceled_at: Optional[int]


@dataclass
class ReminderCommand:
    """Parsed reminder command."""

    action: str  # "schedule", "list", "cancel"
    kind: str
    due_at: Optional[int] = None
    message: Optional[str] = None
    reminder_id: Optional[int] = None


class ReminderStore:
    """SQLite-backed reminder storage."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    due_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    sent_at INTEGER,
                    canceled_at INTEGER
                )
                """
            )

    def add_reminder(self, kind: str, due_at: int, message: str, created_at: Optional[int] = None) -> int:
        created_at = created_at or int(time.time())
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO reminders (kind, message, due_at, created_at) VALUES (?, ?, ?, ?)",
                (kind, message, due_at, created_at),
            )
            return int(cursor.lastrowid)

    def list_reminders(self, include_sent: bool = False, include_canceled: bool = False) -> list[Reminder]:
        clauses = []
        if not include_sent:
            clauses.append("sent_at IS NULL")
        if not include_canceled:
            clauses.append("canceled_at IS NULL")
        where_sql = " AND ".join(clauses)
        if where_sql:
            where_sql = "WHERE " + where_sql
        query = f"SELECT * FROM reminders {where_sql} ORDER BY due_at ASC"
        with self._lock:
            rows = list(self._conn.execute(query))
        return [self._row_to_reminder(row) for row in rows]

    def cancel_reminder(self, reminder_id: int, canceled_at: Optional[int] = None) -> bool:
        canceled_at = canceled_at or int(time.time())
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE reminders SET canceled_at = ? WHERE id = ? AND sent_at IS NULL AND canceled_at IS NULL",
                (canceled_at, reminder_id),
            )
            return cursor.rowcount > 0

    def get_due(self, now_ts: Optional[int] = None) -> list[Reminder]:
        now_ts = now_ts or int(time.time())
        with self._lock:
            rows = list(
                self._conn.execute(
                    "SELECT * FROM reminders WHERE due_at <= ? AND sent_at IS NULL AND canceled_at IS NULL",
                    (now_ts,),
                )
            )
        return [self._row_to_reminder(row) for row in rows]

    def mark_sent(self, reminder_ids: Iterable[int], sent_at: Optional[int] = None) -> None:
        sent_at = sent_at or int(time.time())
        reminder_ids = list(reminder_ids)
        if not reminder_ids:
            return
        placeholders = ",".join("?" for _ in reminder_ids)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE reminders SET sent_at = ? WHERE id IN ({placeholders})",
                [sent_at, *reminder_ids],
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=int(row["id"]),
            kind=row["kind"],
            message=row["message"],
            due_at=int(row["due_at"]),
            created_at=int(row["created_at"]),
            sent_at=row["sent_at"],
            canceled_at=row["canceled_at"],
        )


class ReminderScheduler(threading.Thread):
    """Background scheduler that dispatches reminders when due."""

    def __init__(
        self,
        store: ReminderStore,
        publish_fn: Callable[[str], bool],
        interval_seconds: int = 5,
        now_fn: Optional[Callable[[], int]] = None,
    ):
        super().__init__(daemon=True)
        self.store = store
        self.publish_fn = publish_fn
        self.interval_seconds = interval_seconds
        self.now_fn = now_fn or (lambda: int(time.time()))
        self._stop_event = threading.Event()

    def run(self) -> None:
        logger.info("Reminder scheduler started")
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.error(f"Reminder scheduler error: {exc}", exc_info=True)
            self._stop_event.wait(self.interval_seconds)

    def run_once(self) -> None:
        now_ts = self.now_fn()
        due = self.store.get_due(now_ts)
        if not due:
            return
        sent_ids = []
        for reminder in due:
            message = f"[REMINDER] {reminder.kind} ({reminder.id}): {reminder.message}"
            if self.publish_fn(message):
                sent_ids.append(reminder.id)
        if sent_ids:
            self.store.mark_sent(sent_ids, sent_at=now_ts)

    def stop(self) -> None:
        self._stop_event.set()


def parse_reminder_command(
    text: str,
    kind: str,
    now: Optional[datetime] = None,
) -> ReminderCommand:
    """Parse a REMIND/ALARM command payload."""
    normalized = text.strip()
    if not normalized:
        raise ValueError("Reminder command is empty")

    lower = normalized.lower()
    if lower == "list":
        return ReminderCommand(action="list", kind=kind)

    if lower.startswith("cancel"):
        parts = normalized.split()
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError("Cancel command requires an integer id")
        return ReminderCommand(action="cancel", kind=kind, reminder_id=int(parts[1]))

    time_part, message = _split_time_and_message(normalized)
    due_at = parse_time_expression(time_part, now=now)
    if due_at is None:
        raise ValueError(f"Unrecognized time format: {time_part}")

    return ReminderCommand(
        action="schedule",
        kind=kind,
        due_at=due_at,
        message=message or "Reminder",
    )


def parse_time_expression(text: str, now: Optional[datetime] = None) -> Optional[int]:
    """Parse a minimal time expression and return a local timestamp."""
    now = now or datetime.now()
    normalized = text.strip().lower()

    match = re.match(r"^in\s+(\d+)\s*([mhd])$", normalized)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        delta = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }[unit]
        return _to_timestamp(now + delta)

    match = re.match(r"^at\s+(\d{1,2}):(\d{2})$", normalized)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return _to_timestamp(due)

    try:
        due = datetime.strptime(normalized, "%Y-%m-%d %H:%M")
        return _to_timestamp(due)
    except ValueError:
        return None


def format_timestamp_local(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _split_time_and_message(text: str) -> tuple[str, Optional[str]]:
    if "|" in text:
        time_part, message = text.split("|", 1)
        return time_part.strip(), message.strip()
    return text.strip(), None


def _to_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())
