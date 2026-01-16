"""SQLite-backed storage for custom morning briefing items.

This module provides persistence for user-created briefing items that can be
added via the API and later consumed by the morning briefing generator.

Usage:
    from storage.briefing_store import BriefingStore

    store = BriefingStore(Path("~/.local/state/milton/briefing.sqlite3"))
    item_id = store.add_item("Review AI resources", priority=1, source="api")
    items = store.list_items(status="active")
    store.mark_done(item_id)
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    """Return current UTC time as ISO8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BriefingItem:
    """A custom briefing item record."""

    id: int
    content: str
    priority: int
    source: str
    status: str  # "active", "done", "dismissed"
    created_at: str  # ISO8601 UTC
    due_at: Optional[str]  # ISO8601 UTC
    expires_at: Optional[str]  # ISO8601 UTC
    completed_at: Optional[str]  # ISO8601 UTC
    dismissed_at: Optional[str]  # ISO8601 UTC

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "priority": self.priority,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at,
            "due_at": self.due_at,
            "expires_at": self.expires_at,
            "completed_at": self.completed_at,
            "dismissed_at": self.dismissed_at,
        }


class BriefingStore:
    """SQLite-backed storage for custom briefing items.

    Thread-safe storage following the same patterns as ReminderStore.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path):
        """Initialize the briefing store.

        Args:
            db_path: Path to SQLite database file. Parent directories
                     will be created if they don't exist.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS briefing_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    due_at TEXT,
                    expires_at TEXT,
                    completed_at TEXT,
                    dismissed_at TEXT
                )
                """
            )
            # Index for efficient status filtering
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_briefing_items_status
                ON briefing_items(status)
                """
            )

    def add_item(
        self,
        content: str,
        priority: int = 0,
        source: str = "manual",
        due_at: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> int:
        """Add a new briefing item.

        Args:
            content: The item text/description (required).
            priority: Priority level (0=normal, higher=more important).
            source: Origin of the item (e.g., "manual", "api", "chat").
            due_at: Optional due date/time (ISO8601 UTC string).
            expires_at: Optional expiration date/time (ISO8601 UTC string).

        Returns:
            The ID of the newly created item.

        Raises:
            ValueError: If content is empty.
        """
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")

        created_at = _now_utc_iso()

        with self._lock, self._conn:
            cursor = self._conn.execute(
                """INSERT INTO briefing_items
                   (content, priority, source, status, created_at, due_at, expires_at)
                   VALUES (?, ?, ?, 'active', ?, ?, ?)""",
                (content.strip(), priority, source, created_at, due_at, expires_at),
            )
            item_id = int(cursor.lastrowid)
            logger.info(f"Created briefing item {item_id}: {content[:50]}...")
            return item_id

    def list_items(
        self,
        status: Optional[str] = None,
        include_expired: bool = False,
    ) -> list[BriefingItem]:
        """List briefing items with optional filtering.

        Args:
            status: Filter by status ("active", "done", "dismissed").
                   If None, returns all statuses.
            include_expired: If False (default), excludes items where
                            expires_at < current time.

        Returns:
            List of BriefingItem objects, ordered by priority (desc), created_at (asc).
        """
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if not include_expired:
            now = _now_utc_iso()
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT * FROM briefing_items
            {where_clause}
            ORDER BY priority DESC, created_at ASC
        """

        with self._lock:
            rows = list(self._conn.execute(query, params))

        return [self._row_to_item(row) for row in rows]

    def get_item(self, item_id: int) -> Optional[BriefingItem]:
        """Get a single item by ID.

        Args:
            item_id: The item ID to retrieve.

        Returns:
            BriefingItem if found, None otherwise.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM briefing_items WHERE id = ?", (item_id,)
            ).fetchone()

        return self._row_to_item(row) if row else None

    def mark_done(self, item_id: int) -> bool:
        """Mark an item as done.

        Args:
            item_id: The item ID to mark done.

        Returns:
            True if the item was updated, False if not found or already done.
        """
        completed_at = _now_utc_iso()

        with self._lock, self._conn:
            cursor = self._conn.execute(
                """UPDATE briefing_items
                   SET status = 'done', completed_at = ?
                   WHERE id = ? AND status = 'active'""",
                (completed_at, item_id),
            )
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Marked briefing item {item_id} as done")
        return updated

    def mark_dismissed(self, item_id: int) -> bool:
        """Mark an item as dismissed (not done, just hidden).

        Args:
            item_id: The item ID to dismiss.

        Returns:
            True if the item was updated, False if not found or already dismissed.
        """
        dismissed_at = _now_utc_iso()

        with self._lock, self._conn:
            cursor = self._conn.execute(
                """UPDATE briefing_items
                   SET status = 'dismissed', dismissed_at = ?
                   WHERE id = ? AND status = 'active'""",
                (dismissed_at, item_id),
            )
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Dismissed briefing item {item_id}")
        return updated

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> BriefingItem:
        """Convert a database row to a BriefingItem."""
        return BriefingItem(
            id=int(row["id"]),
            content=row["content"],
            priority=int(row["priority"]),
            source=row["source"],
            status=row["status"],
            created_at=row["created_at"],
            due_at=row["due_at"],
            expires_at=row["expires_at"],
            completed_at=row["completed_at"],
            dismissed_at=row["dismissed_at"],
        )
