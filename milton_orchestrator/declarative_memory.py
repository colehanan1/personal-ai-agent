"""Declarative memory storage for user-stated facts and intents."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Source enum constants
MEMORY_SOURCES = frozenset({"webui", "phone", "voice", "api"})


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
class DeclarativeMemory:
    """Stored declarative memory record."""

    id: str
    content: str
    tags: list
    source: str
    confidence: Optional[float]
    context_ref: Optional[str]
    created_at: int
    updated_at: int

    def __post_init__(self):
        """Validate fields."""
        if self.source not in MEMORY_SOURCES:
            raise ValueError(
                f"Invalid source '{self.source}', must be one of {sorted(MEMORY_SOURCES)}"
            )
        if not isinstance(self.tags, list):
            raise ValueError("tags must be a list")
        if not self.content or not self.content.strip():
            raise ValueError("Content cannot be empty")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")


class DeclarativeMemoryStore:
    """SQLite-backed declarative memory storage."""

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
                CREATE TABLE IF NOT EXISTS declarative_memory (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    tags TEXT,
                    source TEXT NOT NULL,
                    confidence REAL,
                    context_ref TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            # Create index for search performance
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_created_at 
                ON declarative_memory(created_at DESC)
                """
            )

    def add_memory(
        self,
        content: str,
        tags: list[str],
        source: str,
        confidence: Optional[float] = None,
        context_ref: Optional[str] = None,
        created_at: Optional[int] = None,
    ) -> str:
        """
        Add a new declarative memory.

        Args:
            content: The memory content/fact
            tags: List of tags for categorization
            source: Source of the memory (webui|phone|voice|api)
            confidence: Optional confidence score (0.0-1.0)
            context_ref: Optional reference to related context (e.g., "reminder:42")
            created_at: Optional creation timestamp (defaults to now)

        Returns:
            Memory ID (UUID string)

        Raises:
            ValueError: If validation fails
        """
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
        if source not in MEMORY_SOURCES:
            raise ValueError(
                f"Invalid source '{source}', must be one of {sorted(MEMORY_SOURCES)}"
            )
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")

        memory_id = str(uuid.uuid4())
        now_ts = created_at or int(time.time())
        tags_json = _serialize_list(tags)

        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO declarative_memory 
                (id, content, tags, source, confidence, context_ref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (memory_id, content, tags_json, source, confidence, context_ref, now_ts, now_ts),
            )
        
        logger.info(f"Added declarative memory {memory_id}: {content[:50]}...")
        return memory_id

    def get_memory(self, memory_id: str) -> Optional[DeclarativeMemory]:
        """
        Get a single memory by ID.

        Args:
            memory_id: The memory ID

        Returns:
            DeclarativeMemory or None if not found
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM declarative_memory WHERE id = ?", (memory_id,)
            )
            row = cursor.fetchone()
            return self._row_to_memory(row) if row else None

    def search_memory(
        self,
        query: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[DeclarativeMemory]:
        """
        Search memories by content and/or tags.

        Args:
            query: Optional keyword to search in content (case-insensitive)
            tags: Optional list of tags to filter by (OR match)
            limit: Maximum number of results (default 100)

        Returns:
            List of matching DeclarativeMemory objects, newest first
        """
        clauses = []
        params = []

        if query:
            clauses.append("content LIKE ?")
            params.append(f"%{query}%")

        if tags:
            # Match any of the provided tags
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            if tag_conditions:
                clauses.append(f"({' OR '.join(tag_conditions)})")

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        
        with self._lock:
            cursor = self._conn.execute(
                f"""
                SELECT * FROM declarative_memory 
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit],
            )
            rows = cursor.fetchall()
            return [self._row_to_memory(row) for row in rows]

    def list_memories(self, limit: int = 100) -> list[DeclarativeMemory]:
        """
        List all memories, newest first.

        Args:
            limit: Maximum number of results (default 100)

        Returns:
            List of DeclarativeMemory objects
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT * FROM declarative_memory 
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [self._row_to_memory(row) for row in rows]

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
        confidence: Optional[float] = None,
        context_ref: Optional[str] = None,
    ) -> bool:
        """
        Update an existing memory.

        Args:
            memory_id: The memory ID to update
            content: Optional new content
            tags: Optional new tags
            confidence: Optional new confidence score
            context_ref: Optional new context reference

        Returns:
            True if updated, False if memory not found

        Raises:
            ValueError: If validation fails
        """
        # Get existing memory
        existing = self.get_memory(memory_id)
        if not existing:
            return False

        # Build update query dynamically
        updates = []
        params = []

        if content is not None:
            if not content.strip():
                raise ValueError("Content cannot be empty")
            updates.append("content = ?")
            params.append(content)

        if tags is not None:
            updates.append("tags = ?")
            params.append(_serialize_list(tags))

        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                raise ValueError("Confidence must be between 0.0 and 1.0")
            updates.append("confidence = ?")
            params.append(confidence)

        if context_ref is not None:
            updates.append("context_ref = ?")
            params.append(context_ref)

        # Always update updated_at
        updates.append("updated_at = ?")
        params.append(int(time.time()))

        if not updates:
            return True  # No changes requested

        params.append(memory_id)

        with self._lock, self._conn:
            cursor = self._conn.execute(
                f"""
                UPDATE declarative_memory 
                SET {', '.join(updates)}
                WHERE id = ?
                """,
                params,
            )
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated declarative memory {memory_id}")
        return updated

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if memory not found
        """
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM declarative_memory WHERE id = ?", (memory_id,)
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted declarative memory {memory_id}")
        return deleted

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> DeclarativeMemory:
        """Convert a database row to a DeclarativeMemory object."""
        return DeclarativeMemory(
            id=row["id"],
            content=row["content"],
            tags=_deserialize_list(row["tags"]),
            source=row["source"],
            confidence=row["confidence"],
            context_ref=row["context_ref"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
