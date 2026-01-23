"""Activity snapshot storage for device context tracking."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Device type enum constants
DEVICE_TYPES = frozenset({"mac", "pc", "pi", "phone"})


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
class ActivitySnapshot:
    """Stored activity snapshot record."""

    id: str
    device_id: str
    device_type: str
    captured_at: int
    active_app: Optional[str]
    window_title: Optional[str]
    project_path: Optional[str]
    git_branch: Optional[str]
    recent_files: list
    notes: Optional[str]
    created_at: int

    def __post_init__(self):
        """Validate fields."""
        if self.device_type not in DEVICE_TYPES:
            raise ValueError(
                f"Invalid device_type '{self.device_type}', must be one of {sorted(DEVICE_TYPES)}"
            )
        if not isinstance(self.recent_files, list):
            raise ValueError("recent_files must be a list")


class ActivitySnapshotStore:
    """SQLite-backed activity snapshot storage."""

    def __init__(
        self, 
        db_path: Path, 
        retention_days: Optional[int] = None,
        max_per_device: Optional[int] = None,
    ):
        """
        Initialize activity snapshot store.
        
        Args:
            db_path: Path to SQLite database
            retention_days: Optional days to retain snapshots (default: no age-based cleanup)
            max_per_device: Optional max snapshots per device (default: no count-based cleanup)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.max_per_device = max_per_device
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_snapshots (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    captured_at INTEGER NOT NULL,
                    active_app TEXT,
                    window_title TEXT,
                    project_path TEXT,
                    git_branch TEXT,
                    recent_files TEXT,
                    notes TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            # Create indexes for common queries
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_device_captured 
                ON activity_snapshots(device_id, captured_at DESC)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_captured 
                ON activity_snapshots(captured_at DESC)
                """
            )

    def add_snapshot(
        self,
        device_id: str,
        device_type: str,
        captured_at: int,
        active_app: Optional[str] = None,
        window_title: Optional[str] = None,
        project_path: Optional[str] = None,
        git_branch: Optional[str] = None,
        recent_files: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> str:
        """
        Add a new activity snapshot.

        Args:
            device_id: Device identifier
            device_type: Device type (mac|pc|pi|phone)
            captured_at: Unix timestamp when snapshot was captured
            active_app: Optional active application name
            window_title: Optional window title
            project_path: Optional project folder path
            git_branch: Optional git branch name
            recent_files: Optional list of recent file paths
            notes: Optional notes

        Returns:
            Snapshot ID (UUID string)

        Raises:
            ValueError: If validation fails
        """
        if device_type not in DEVICE_TYPES:
            raise ValueError(
                f"Invalid device_type '{device_type}', must be one of {sorted(DEVICE_TYPES)}"
            )

        snapshot_id = str(uuid.uuid4())
        now_ts = int(time.time())
        recent_files_json = _serialize_list(recent_files or [])

        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO activity_snapshots 
                (id, device_id, device_type, captured_at, active_app, window_title, 
                 project_path, git_branch, recent_files, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    device_id,
                    device_type,
                    captured_at,
                    active_app,
                    window_title,
                    project_path,
                    git_branch,
                    recent_files_json,
                    notes,
                    now_ts,
                ),
            )

        logger.info(
            f"Added activity snapshot {snapshot_id} for device {device_id} "
            f"(app: {active_app}, captured: {captured_at})"
        )
        return snapshot_id

    def get_recent(
        self,
        device_id: Optional[str] = None,
        minutes: Optional[int] = None,
        limit: int = 100,
    ) -> list[ActivitySnapshot]:
        """
        Get recent activity snapshots.

        Args:
            device_id: Optional device ID filter
            minutes: Optional time range in minutes (from now)
            limit: Maximum number of results (default 100)

        Returns:
            List of ActivitySnapshot objects, newest first
        """
        clauses = []
        params = []

        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)

        if minutes:
            cutoff = int(time.time()) - (minutes * 60)
            clauses.append("captured_at >= ?")
            params.append(cutoff)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            cursor = self._conn.execute(
                f"""
                SELECT * FROM activity_snapshots 
                {where_clause}
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                params + [limit],
            )
            rows = cursor.fetchall()
            return [self._row_to_snapshot(row) for row in rows]

    def search(
        self,
        query: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ActivitySnapshot]:
        """
        Search activity snapshots by content.

        Args:
            query: Optional keyword to search in text fields
            device_id: Optional device ID filter
            limit: Maximum number of results (default 100)

        Returns:
            List of matching ActivitySnapshot objects, newest first
        """
        clauses = []
        params = []

        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)

        if query:
            # Search across all text fields
            search_fields = [
                "active_app",
                "window_title",
                "project_path",
                "git_branch",
                "notes",
            ]
            search_conditions = [f"{field} LIKE ?" for field in search_fields]
            clauses.append(f"({' OR '.join(search_conditions)})")
            params.extend([f"%{query}%"] * len(search_fields))

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            cursor = self._conn.execute(
                f"""
                SELECT * FROM activity_snapshots 
                {where_clause}
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                params + [limit],
            )
            rows = cursor.fetchall()
            return [self._row_to_snapshot(row) for row in rows]

    def cleanup_old(self) -> int:
        """
        Clean up old snapshots based on retention policy.

        Returns:
            Number of snapshots deleted
        """
        deleted = 0

        with self._lock, self._conn:
            # Age-based cleanup
            if self.retention_days:
                cutoff = int(time.time()) - (self.retention_days * 86400)
                cursor = self._conn.execute(
                    "DELETE FROM activity_snapshots WHERE captured_at < ?",
                    (cutoff,),
                )
                deleted += cursor.rowcount
                if cursor.rowcount > 0:
                    logger.info(
                        f"Deleted {cursor.rowcount} snapshots older than {self.retention_days} days"
                    )

            # Count-based cleanup per device
            if self.max_per_device:
                # Get all devices
                devices = [
                    row[0]
                    for row in self._conn.execute(
                        "SELECT DISTINCT device_id FROM activity_snapshots"
                    ).fetchall()
                ]

                for device_id in devices:
                    # Keep only the most recent N snapshots per device
                    cursor = self._conn.execute(
                        """
                        DELETE FROM activity_snapshots 
                        WHERE device_id = ? AND id NOT IN (
                            SELECT id FROM activity_snapshots 
                            WHERE device_id = ?
                            ORDER BY captured_at DESC 
                            LIMIT ?
                        )
                        """,
                        (device_id, device_id, self.max_per_device),
                    )
                    deleted += cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(
                            f"Deleted {cursor.rowcount} old snapshots for device {device_id}"
                        )

        return deleted

    def get_devices(self) -> list[str]:
        """
        Get list of all device IDs that have snapshots.

        Returns:
            List of device ID strings
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT DISTINCT device_id FROM activity_snapshots ORDER BY device_id"
            )
            return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> ActivitySnapshot:
        """Convert a database row to an ActivitySnapshot object."""
        return ActivitySnapshot(
            id=row["id"],
            device_id=row["device_id"],
            device_type=row["device_type"],
            captured_at=row["captured_at"],
            active_app=row["active_app"],
            window_title=row["window_title"],
            project_path=row["project_path"],
            git_branch=row["git_branch"],
            recent_files=_deserialize_list(row["recent_files"]),
            notes=row["notes"],
            created_at=row["created_at"],
        )
