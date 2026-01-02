"""Reminder scheduling and persistence for Milton Orchestrator."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

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
    timezone: str = "America/New_York"
    delivery_target: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class ReminderCommand:
    """Parsed reminder command."""

    action: str  # "schedule", "list", "cancel"
    kind: str
    due_at: Optional[int] = None
    message: Optional[str] = None
    reminder_id: Optional[int] = None


class ReminderStore:
    """SQLite-backed reminder storage with timezone support."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._migrate_schema()

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
                    canceled_at INTEGER,
                    timezone TEXT DEFAULT 'America/New_York',
                    delivery_target TEXT,
                    last_error TEXT
                )
                """
            )

    def _migrate_schema(self) -> None:
        """Migrate existing database schema to add new columns."""
        with self._lock, self._conn:
            cursor = self._conn.execute("PRAGMA table_info(reminders)")
            columns = {row[1] for row in cursor.fetchall()}

            if "timezone" not in columns:
                logger.info("Adding timezone column to reminders table")
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN timezone TEXT DEFAULT 'America/New_York'"
                )

            if "delivery_target" not in columns:
                logger.info("Adding delivery_target column to reminders table")
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN delivery_target TEXT"
                )

            if "last_error" not in columns:
                logger.info("Adding last_error column to reminders table")
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN last_error TEXT"
                )

    def add_reminder(
        self,
        kind: str,
        due_at: int,
        message: str,
        created_at: Optional[int] = None,
        timezone: str = "America/New_York",
        delivery_target: Optional[str] = None,
    ) -> int:
        created_at = created_at or int(time.time())
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """INSERT INTO reminders
                   (kind, message, due_at, created_at, timezone, delivery_target)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kind, message, due_at, created_at, timezone, delivery_target),
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

    def mark_error(self, reminder_id: int, error: str) -> None:
        """Mark a reminder as having an error during delivery."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE reminders SET last_error = ? WHERE id = ?",
                (error, reminder_id),
            )

    def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        """Get a single reminder by ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return self._row_to_reminder(row) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> Reminder:
        # Helper to safely get column value with default
        def safe_get(row, key: str, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        return Reminder(
            id=int(row["id"]),
            kind=row["kind"],
            message=row["message"],
            due_at=int(row["due_at"]),
            created_at=int(row["created_at"]),
            sent_at=row["sent_at"],
            canceled_at=row["canceled_at"],
            timezone=safe_get(row, "timezone", "America/New_York"),
            delivery_target=safe_get(row, "delivery_target"),
            last_error=safe_get(row, "last_error"),
        )


class ReminderScheduler(threading.Thread):
    """Background scheduler that dispatches reminders when due with retry logic."""

    def __init__(
        self,
        store: ReminderStore,
        publish_fn: Callable[[str, str, int], bool],  # message, title, reminder_id -> success
        interval_seconds: int = 5,
        now_fn: Optional[Callable[[], int]] = None,
        max_retries: int = 3,
        retry_backoff: int = 60,
    ):
        super().__init__(daemon=True)
        self.store = store
        self.publish_fn = publish_fn
        self.interval_seconds = interval_seconds
        self.now_fn = now_fn or (lambda: int(time.time()))
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._stop_event = threading.Event()
        self._retry_tracker: dict[int, tuple[int, int]] = {}  # reminder_id -> (attempts, next_retry_ts)

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
            # Check if we should retry this reminder
            if reminder.id in self._retry_tracker:
                attempts, next_retry = self._retry_tracker[reminder.id]
                if now_ts < next_retry:
                    continue  # Not time to retry yet
                if attempts >= self.max_retries:
                    # Max retries exceeded, mark as failed
                    error = f"Failed after {attempts} attempts"
                    logger.error(f"Reminder {reminder.id} failed: {error}")
                    self.store.mark_error(reminder.id, error)
                    self.store.mark_sent([reminder.id], sent_at=now_ts)
                    del self._retry_tracker[reminder.id]
                    continue
            else:
                attempts = 0

            # Try to send the reminder
            message = reminder.message
            title = f"Milton Reminder ({reminder.kind})"

            try:
                success = self.publish_fn(message, title, reminder.id)
                if success:
                    sent_ids.append(reminder.id)
                    if reminder.id in self._retry_tracker:
                        del self._retry_tracker[reminder.id]
                    logger.info(f"Sent reminder {reminder.id}: {message[:50]}...")
                else:
                    # Delivery failed, schedule retry
                    attempts += 1
                    next_retry = now_ts + (self.retry_backoff * attempts)
                    self._retry_tracker[reminder.id] = (attempts, next_retry)
                    error = f"Delivery failed (attempt {attempts}/{self.max_retries})"
                    logger.warning(f"Reminder {reminder.id}: {error}, retry at {format_timestamp_local(next_retry)}")
                    self.store.mark_error(reminder.id, error)
            except Exception as exc:
                # Exception during delivery, schedule retry
                attempts += 1
                next_retry = now_ts + (self.retry_backoff * attempts)
                self._retry_tracker[reminder.id] = (attempts, next_retry)
                error = f"Exception: {str(exc)[:200]}"
                logger.error(f"Reminder {reminder.id} exception: {exc}", exc_info=True)
                self.store.mark_error(reminder.id, error)

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


def parse_time_expression(
    text: str,
    now: Optional[datetime] = None,
    timezone: str = "America/New_York",
) -> Optional[int]:
    """
    Parse a time expression and return a timestamp in the specified timezone.

    Supports:
    - Relative: "in 10m", "in 2h", "in 3d"
    - Time today/tomorrow: "at 14:30", "at 9:00"
    - Natural language (if dateparser available): "tomorrow at 9am", "next monday 3pm"
    - Absolute: "2026-01-15 14:30"

    Args:
        text: Time expression to parse
        now: Reference time (defaults to current time in specified timezone)
        timezone: Timezone to use (default: America/New_York)

    Returns:
        Unix timestamp (UTC) or None if parsing failed
    """
    normalized = text.strip().lower()

    # Get timezone object
    tz = None
    if PYTZ_AVAILABLE:
        try:
            tz = pytz.timezone(timezone)
        except Exception:
            logger.warning(f"Invalid timezone {timezone}, falling back to system local")

    # Get current time in the specified timezone
    if now is None:
        if tz:
            now = datetime.now(tz).replace(tzinfo=None)  # Convert to naive for compatibility
        else:
            now = datetime.now()

    # Try simple relative patterns first (faster)
    match = re.match(r"^in\s+(\d+)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)$", normalized)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit.startswith('m'):
            delta = timedelta(minutes=value)
        elif unit.startswith('h'):
            delta = timedelta(hours=value)
        elif unit.startswith('d'):
            delta = timedelta(days=value)
        else:
            return None
        return _to_timestamp(now + delta)

    # Try "at HH:MM" pattern
    match = re.match(r"^at\s+(\d{1,2}):(\d{2})$", normalized)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return _to_timestamp(due)

    # Try absolute datetime format
    try:
        due = datetime.strptime(normalized, "%Y-%m-%d %H:%M")
        return _to_timestamp(due)
    except ValueError:
        pass

    # Try dateparser for natural language (if available)
    if DATEPARSER_AVAILABLE:
        try:
            settings = {
                'TIMEZONE': timezone,
                'RETURN_AS_TIMEZONE_AWARE': False,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': now,
            }
            parsed = dateparser.parse(text, settings=settings)
            if parsed:
                # Ensure it's in the future
                if parsed <= now:
                    # Try adding a day
                    parsed += timedelta(days=1)
                return _to_timestamp(parsed)
        except Exception as exc:
            logger.debug(f"dateparser failed for '{text}': {exc}")

    return None


def format_timestamp_local(timestamp: int, timezone: str = "America/New_York") -> str:
    """Format a timestamp in the specified timezone."""
    if PYTZ_AVAILABLE:
        try:
            tz = pytz.timezone(timezone)
            dt = datetime.fromtimestamp(timestamp, tz=tz)
            return dt.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            pass
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _split_time_and_message(text: str) -> tuple[str, Optional[str]]:
    if "|" in text:
        time_part, message = text.split("|", 1)
        return time_part.strip(), message.strip()
    return text.strip(), None


def _to_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())
