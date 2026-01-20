"""Reminder scheduling and persistence for Milton Orchestrator."""

from __future__ import annotations

import json
import logging
import os
import re
import requests
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

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

# Phase 0 enum constants
REMINDER_CHANNELS = frozenset({"ntfy", "voice", "both"})
REMINDER_PRIORITIES = frozenset({"low", "med", "high"})
REMINDER_STATUSES = frozenset({"scheduled", "fired", "acknowledged", "snoozed", "canceled"})
REMINDER_ACTIONS = frozenset({"DONE", "SNOOZE_30", "DELAY_2H", "EDIT_TIME"})
REMINDER_SOURCES = frozenset({"webui", "phone", "voice", "other"})

# Default action buttons for reminders
DEFAULT_ACTIONS = ["DONE", "SNOOZE_30", "DELAY_2H"]


def _serialize_list(items: list) -> str:
    """Serialize a list to JSON string for storage."""
    return json.dumps(items)


def _deserialize_list(data: Optional[str]) -> list:
    """Deserialize a JSON string to list, with safe default."""
    if not data:
        return []
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return []


@dataclass
class Reminder:
    """Stored reminder record with Phase 0 enhancements."""

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
    # Phase 0 fields
    channel: str = "ntfy"
    priority: str = "med"
    status: str = "scheduled"
    actions: list = field(default_factory=lambda: list(DEFAULT_ACTIONS))
    source: str = "other"
    updated_at: Optional[int] = None
    audit_log: list = field(default_factory=list)
    # Phase 2C field
    context_ref: Optional[str] = None

    def __post_init__(self):
        """Validate enum fields."""
        if self.channel not in REMINDER_CHANNELS:
            raise ValueError(f"Invalid channel '{self.channel}', must be one of {sorted(REMINDER_CHANNELS)}")
        if self.priority not in REMINDER_PRIORITIES:
            raise ValueError(f"Invalid priority '{self.priority}', must be one of {sorted(REMINDER_PRIORITIES)}")
        if self.status not in REMINDER_STATUSES:
            raise ValueError(f"Invalid status '{self.status}', must be one of {sorted(REMINDER_STATUSES)}")
        if self.source not in REMINDER_SOURCES:
            raise ValueError(f"Invalid source '{self.source}', must be one of {sorted(REMINDER_SOURCES)}")
        if not isinstance(self.actions, list):
            raise ValueError("actions must be a list")
        for action in self.actions:
            if action not in REMINDER_ACTIONS:
                raise ValueError(f"Invalid action '{action}', must be one of {sorted(REMINDER_ACTIONS)}")


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
        """Migrate existing database schema to add new columns and tables."""
        with self._lock, self._conn:
            # Create scheduler_metadata table for health tracking
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at INTEGER
                )
                """
            )
            
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

            # Phase 0 column migrations
            if "channel" not in columns:
                logger.info("Adding Phase 0 columns to reminders table")
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN channel TEXT DEFAULT 'ntfy'"
                )
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN priority TEXT DEFAULT 'med'"
                )
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN status TEXT DEFAULT 'scheduled'"
                )
                self._conn.execute(
                    f"ALTER TABLE reminders ADD COLUMN actions TEXT DEFAULT '{_serialize_list(DEFAULT_ACTIONS)}'"
                )
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN source TEXT DEFAULT 'other'"
                )
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN updated_at INTEGER"
                )
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN audit_log TEXT DEFAULT '[]'"
                )
                # Backfill status from existing timestamps
                self._conn.execute("""
                    UPDATE reminders SET status = CASE
                        WHEN canceled_at IS NOT NULL THEN 'canceled'
                        WHEN sent_at IS NOT NULL THEN 'fired'
                        ELSE 'scheduled'
                    END
                """)
                # Backfill updated_at from created_at
                self._conn.execute(
                    "UPDATE reminders SET updated_at = created_at WHERE updated_at IS NULL"
                )
            
            # Phase 2C column migrations
            if "context_ref" not in columns:
                logger.info("Adding Phase 2C context_ref column to reminders table")
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN context_ref TEXT"
                )

    def add_reminder(
        self,
        kind: str,
        due_at: int,
        message: str,
        created_at: Optional[int] = None,
        timezone: str = "America/New_York",
        delivery_target: Optional[str] = None,
        # Phase 0 parameters
        channel: str = "ntfy",
        priority: str = "med",
        actions: Optional[list] = None,
        source: str = "other",
        # Phase 2C parameter
        context_ref: Optional[str] = None,
    ) -> int:
        created_at = created_at or int(time.time())
        if actions is None:
            actions = list(DEFAULT_ACTIONS)

        # Validate enum fields
        if channel not in REMINDER_CHANNELS:
            raise ValueError(f"Invalid channel '{channel}'")
        if priority not in REMINDER_PRIORITIES:
            raise ValueError(f"Invalid priority '{priority}'")
        if source not in REMINDER_SOURCES:
            raise ValueError(f"Invalid source '{source}'")
        for action in actions:
            if action not in REMINDER_ACTIONS:
                raise ValueError(f"Invalid action '{action}'")

        # Create initial audit log entry
        audit_log = [{
            "ts": created_at,
            "action": "created",
            "actor": "system",
            "details": f"Reminder created via {source}",
        }]

        with self._lock, self._conn:
            cursor = self._conn.execute(
                """INSERT INTO reminders
                   (kind, message, due_at, created_at, timezone, delivery_target,
                    channel, priority, status, actions, source, updated_at, audit_log, context_ref)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (kind, message, due_at, created_at, timezone, delivery_target,
                 channel, priority, "scheduled", _serialize_list(actions),
                 source, created_at, _serialize_list(audit_log), context_ref),
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

    def cancel_reminder(
        self,
        reminder_id: int,
        canceled_at: Optional[int] = None,
        actor: str = "system",
        details: Optional[str] = None,
    ) -> bool:
        """Cancel a reminder with audit logging."""
        canceled_at = canceled_at or int(time.time())
        with self._lock, self._conn:
            # Get current audit log
            row = self._conn.execute(
                "SELECT audit_log FROM reminders WHERE id = ? AND sent_at IS NULL AND canceled_at IS NULL",
                (reminder_id,),
            ).fetchone()
            if not row:
                return False

            audit_log = _deserialize_list(row["audit_log"] if row else None)
            audit_log.append({
                "ts": canceled_at,
                "action": "canceled",
                "actor": actor,
                "details": details or "Reminder canceled",
            })

            cursor = self._conn.execute(
                """UPDATE reminders
                   SET canceled_at = ?, status = 'canceled', updated_at = ?, audit_log = ?
                   WHERE id = ? AND sent_at IS NULL AND canceled_at IS NULL""",
                (canceled_at, canceled_at, _serialize_list(audit_log), reminder_id),
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

    def claim_due_reminders(
        self, now_ts: Optional[int] = None, limit: int = 100
    ) -> list[Reminder]:
        """Atomically claim due reminders by marking them as fired.

        This method prevents double-firing by atomically updating reminders
        from scheduled to fired state. Only reminders successfully claimed
        by THIS call will be returned.

        Args:
            now_ts: Current timestamp (defaults to now)
            limit: Maximum number of reminders to claim (default: 100)

        Returns:
            List of Reminder objects that were successfully claimed
        """
        now_ts = now_ts or int(time.time())

        with self._lock, self._conn:
            # Step 1: Select IDs to claim within the transaction
            id_rows = list(
                self._conn.execute(
                    """
                    SELECT id FROM reminders
                    WHERE due_at <= ?
                      AND sent_at IS NULL
                      AND canceled_at IS NULL
                      AND status = 'scheduled'
                    ORDER BY due_at ASC, priority DESC
                    LIMIT ?
                    """,
                    (now_ts, limit),
                )
            )

            if not id_rows:
                return []

            # Extract IDs
            ids_to_claim = [row["id"] for row in id_rows]

            # Step 2: Atomically update those specific IDs
            placeholders = ",".join("?" for _ in ids_to_claim)
            self._conn.execute(
                f"""
                UPDATE reminders
                SET sent_at = ?,
                    status = 'fired',
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [now_ts, now_ts, *ids_to_claim],
            )

            # Step 3: Fetch and return the claimed reminders
            rows = list(
                self._conn.execute(
                    f"""
                    SELECT * FROM reminders
                    WHERE id IN ({placeholders})
                    ORDER BY due_at ASC, priority DESC
                    """,
                    ids_to_claim,
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
                f"UPDATE reminders SET sent_at = ?, status = 'fired', updated_at = ? WHERE id IN ({placeholders})",
                [sent_at, sent_at, *reminder_ids],
            )

    def mark_error(self, reminder_id: int, error: str) -> None:
        """Mark a reminder as having an error during delivery."""
        now_ts = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE reminders SET last_error = ?, updated_at = ? WHERE id = ?",
                (error, now_ts, reminder_id),
            )

    def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        """Get a single reminder by ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return self._row_to_reminder(row) if row else None

    def update_status(
        self,
        reminder_id: int,
        new_status: str,
        actor: str = "system",
        details: Optional[str] = None,
    ) -> bool:
        """Update reminder status with automatic audit log entry.

        Sets sent_at/canceled_at timestamps when appropriate.
        """
        if new_status not in REMINDER_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'")

        now_ts = int(time.time())
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT audit_log, status FROM reminders WHERE id = ?",
                (reminder_id,),
            ).fetchone()
            if not row:
                return False

            old_status = row["status"]
            audit_log = _deserialize_list(row["audit_log"])
            audit_log.append({
                "ts": now_ts,
                "action": f"status_change:{old_status}->{new_status}",
                "actor": actor,
                "details": details or f"Status changed to {new_status}",
            })

            # Determine timestamp updates based on new status
            sent_at_update = ""
            canceled_at_update = ""
            params: list[Any] = [new_status, now_ts, _serialize_list(audit_log)]

            if new_status == "fired":
                sent_at_update = ", sent_at = ?"
                params.append(now_ts)
            elif new_status == "canceled":
                canceled_at_update = ", canceled_at = ?"
                params.append(now_ts)

            params.append(reminder_id)
            cursor = self._conn.execute(
                f"""UPDATE reminders
                   SET status = ?, updated_at = ?, audit_log = ?{sent_at_update}{canceled_at_update}
                   WHERE id = ?""",
                params,
            )
            return cursor.rowcount > 0

    def snooze(
        self,
        reminder_id: int,
        minutes: int,
        actor: str = "system",
        details: Optional[str] = None,
    ) -> bool:
        """Snooze a reminder by delaying due_at.

        Sets status to 'snoozed' and resets sent_at.
        """
        now_ts = int(time.time())
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT due_at, audit_log FROM reminders WHERE id = ?",
                (reminder_id,),
            ).fetchone()
            if not row:
                return False

            old_due_at = row["due_at"]
            new_due_at = now_ts + (minutes * 60)
            audit_log = _deserialize_list(row["audit_log"])
            audit_log.append({
                "ts": now_ts,
                "action": f"snoozed:{minutes}min",
                "actor": actor,
                "details": details or f"Snoozed for {minutes} minutes (was due at {old_due_at})",
            })

            cursor = self._conn.execute(
                """UPDATE reminders
                   SET due_at = ?, status = 'snoozed', sent_at = NULL, updated_at = ?, audit_log = ?
                   WHERE id = ?""",
                (new_due_at, now_ts, _serialize_list(audit_log), reminder_id),
            )
            return cursor.rowcount > 0

    def acknowledge(
        self,
        reminder_id: int,
        actor: str = "system",
        details: Optional[str] = None,
    ) -> bool:
        """Mark a fired reminder as acknowledged.

        Wrapper around update_status for convenience.
        """
        return self.update_status(
            reminder_id,
            "acknowledged",
            actor=actor,
            details=details or "User acknowledged reminder",
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def set_metadata(self, key: str, value: str) -> None:
        """Set a metadata key-value pair with timestamp."""
        now_ts = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO scheduler_metadata (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, value, now_ts),
            )

    def get_metadata(self, key: str) -> Optional[tuple[str, int]]:
        """Get a metadata value and its update timestamp.
        
        Returns:
            Tuple of (value, updated_at) or None if key doesn't exist
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT value, updated_at FROM scheduler_metadata WHERE key = ?",
                (key,),
            ).fetchone()
        return (row["value"], row["updated_at"]) if row else None

    def get_health_stats(self) -> dict:
        """Get health statistics for the reminder system.
        
        Returns dict with:
        - scheduled_count: Number of pending reminders
        - next_due_at: Unix timestamp of next due reminder (None if none)
        - last_scheduler_heartbeat: Unix timestamp of last scheduler run (None if never)
        - heartbeat_age_sec: Seconds since last heartbeat (None if never)
        - last_ntfy_ok: Unix timestamp of last successful ntfy delivery (None if never)
        - last_error: Most recent error message from any reminder (None if no errors)
        """
        now_ts = int(time.time())
        
        with self._lock:
            # Get scheduled count
            scheduled_count = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM reminders WHERE sent_at IS NULL AND canceled_at IS NULL"
            ).fetchone()["cnt"]
            
            # Get next due reminder
            next_due = self._conn.execute(
                """SELECT due_at FROM reminders 
                   WHERE sent_at IS NULL AND canceled_at IS NULL 
                   ORDER BY due_at ASC LIMIT 1"""
            ).fetchone()
            next_due_at = next_due["due_at"] if next_due else None
            
            # Get last error from any reminder
            last_error_row = self._conn.execute(
                """SELECT last_error FROM reminders 
                   WHERE last_error IS NOT NULL 
                   ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
            last_error = last_error_row["last_error"] if last_error_row else None
        
        # Get metadata for heartbeat and ntfy
        heartbeat_meta = self.get_metadata("last_heartbeat")
        last_heartbeat = heartbeat_meta[0] if heartbeat_meta else None
        heartbeat_age = (now_ts - int(last_heartbeat)) if last_heartbeat else None
        
        ntfy_meta = self.get_metadata("last_ntfy_ok")
        last_ntfy_ok = int(ntfy_meta[0]) if ntfy_meta else None
        
        return {
            "scheduled_count": scheduled_count,
            "next_due_at": next_due_at,
            "last_scheduler_heartbeat": int(last_heartbeat) if last_heartbeat else None,
            "heartbeat_age_sec": heartbeat_age,
            "last_ntfy_ok": last_ntfy_ok,
            "last_error": last_error,
        }

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
            # Phase 0 fields
            channel=safe_get(row, "channel", "ntfy"),
            priority=safe_get(row, "priority", "med"),
            status=safe_get(row, "status", "scheduled"),
            actions=_deserialize_list(safe_get(row, "actions", "[]")) or list(DEFAULT_ACTIONS),
            source=safe_get(row, "source", "other"),
            updated_at=safe_get(row, "updated_at"),
            audit_log=_deserialize_list(safe_get(row, "audit_log", "[]")),
            # Phase 2C field
            context_ref=safe_get(row, "context_ref"),
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
        """Process one batch of due reminders with exactly-once semantics.

        Uses atomic claim mechanism to prevent double-firing even if multiple
        scheduler instances run concurrently.
        """
        now_ts = self.now_fn()
        
        # Record heartbeat
        self.store.set_metadata("last_heartbeat", str(now_ts))

        # Atomically claim due reminders (marks them as fired immediately)
        # This prevents double-firing even with concurrent scheduler instances
        claimed = self.store.claim_due_reminders(now_ts, limit=100)

        if not claimed:
            logger.debug(f"Scheduler heartbeat: no due reminders at {now_ts}")
            return

        logger.info(f"Claimed {len(claimed)} due reminder(s)")

        # Try to deliver each claimed reminder
        for reminder in claimed:
            message = reminder.message
            title = f"Milton Reminder ({reminder.kind})"

            try:
                success = self.publish_fn(message, title, reminder.id)
                if success:
                    logger.info(
                        f"Delivered reminder {reminder.id}: {message[:50]}..."
                    )
                    # Record successful ntfy delivery
                    self.store.set_metadata("last_ntfy_ok", str(now_ts))
                else:
                    # Delivery failed but reminder is already claimed (fired)
                    # Record error but do NOT revert to scheduled
                    # This ensures exactly-once: claimed = fired, no double-fire
                    error = "Delivery failed (ntfy returned false)"
                    logger.error(f"Reminder {reminder.id} delivery failed: {error}")
                    self.store.mark_error(reminder.id, error)
            except Exception as exc:
                # Exception during delivery, record error
                # Reminder stays in fired state (exactly-once semantics)
                error = f"Exception: {str(exc)[:200]}"
                logger.error(
                    f"Reminder {reminder.id} delivery exception: {exc}", exc_info=True
                )
                self.store.mark_error(reminder.id, error)

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


def deliver_ntfy(
    reminder: Reminder,
    *,
    ntfy_base_url: str,
    topic: str,
    public_base_url: Optional[str] = None,
) -> dict:
    """
    Deliver a reminder notification to ntfy with action buttons.

    Args:
        reminder: The Reminder to deliver
        ntfy_base_url: Base URL for ntfy server (e.g., https://ntfy.sh)
        topic: ntfy topic to publish to
        public_base_url: Base URL for callback actions (e.g., https://milton.tailnet.ts.net)

    Returns:
        dict with keys: ok (bool), status_code (int), response_snippet (str)
    """
    # Format timestamp in reminder's timezone
    due_str = format_timestamp_local(reminder.due_at, reminder.timezone)

    # Build message body
    action_labels = " | ".join(reminder.actions)
    body = f"""{reminder.message}

Due: {due_str}
ID: {reminder.id}
Actions: {action_labels}"""

    # Priority mapping: high→5, med→3, low→2
    priority_map = {"high": 5, "med": 3, "low": 2}
    priority = priority_map.get(reminder.priority, 3)

    # Build headers
    headers = {
        "Title": f"Milton Reminder ({reminder.kind})",
        "Priority": str(priority),
    }

    # Add action buttons if public_base_url is provided
    if public_base_url:
        # Build action buttons in ntfy format
        # Format: http, Label, POST, URL, body='{"key":"value"}'
        action_parts = []
        for action in reminder.actions:
            action_url = f"{public_base_url}/api/reminders/{reminder.id}/action"
            action_body = json.dumps({"action": action})
            action_parts.append(f"http, {action}, POST, {action_url}, body='{action_body}'")

        headers["Actions"] = "; ".join(action_parts)

    # Publish to ntfy
    url = f"{ntfy_base_url}/{topic}"
    try:
        response = requests.post(
            url,
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "response_snippet": response.text[:200],
        }
    except Exception as exc:
        error_msg = str(exc)[:200]
        logger.error(f"Failed to deliver ntfy notification: {exc}")
        return {
            "ok": False,
            "status_code": 0,
            "response_snippet": error_msg,
        }


def _split_time_and_message(text: str) -> tuple[str, Optional[str]]:
    if "|" in text:
        time_part, message = text.split("|", 1)
        return time_part.strip(), message.strip()
    return text.strip(), None


def _to_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())
