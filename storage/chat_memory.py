"""SQLite-backed storage for chat conversation history and memory facts.

This module provides persistence for conversation history and explicit memory facts
that Milton can recall across sessions. Supports per-thread conversation history
and user-defined memory facts via /remember command.

Usage:
    from storage.chat_memory import ChatMemoryStore
    
    store = ChatMemoryStore(Path("~/.local/state/milton/chat_memory.sqlite3"))
    
    # Store conversation turns
    store.append_turn(thread_id="thread-123", role="user", content="Hello Milton")
    store.append_turn(thread_id="thread-123", role="assistant", content="Hi! How can I help?")
    
    # Retrieve recent history
    history = store.get_recent_turns(thread_id="thread-123", limit=10)
    
    # Store explicit memory facts
    store.upsert_fact(key="user_name", value="Cole")
    facts = store.get_all_facts()
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
class ConversationTurn:
    """A single turn in a conversation."""
    
    id: int
    thread_id: str
    role: str  # "user", "assistant", "system"
    content: str
    created_at: str  # ISO8601 UTC
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


@dataclass
class MemoryFact:
    """An explicit memory fact stored via /remember command."""
    
    id: int
    key: str
    value: str
    created_at: str  # ISO8601 UTC
    updated_at: str  # ISO8601 UTC
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ChatMemoryStore:
    """SQLite-backed storage for chat conversation history and memory facts.
    
    Thread-safe storage following the same patterns as BriefingStore.
    
    Attributes:
        db_path: Path to the SQLite database file.
    """
    
    def __init__(self, db_path: Path):
        """Initialize the chat memory store.
        
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
            # Conversation turns table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Index for efficient thread_id + time-ordered retrieval
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_turns_thread_time
                ON conversation_turns(thread_id, created_at DESC)
                """
            )
            
            # Memory facts table (key-value store)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Index for fast key lookups
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_facts_key
                ON memory_facts(key)
                """
            )
    
    def append_turn(
        self,
        thread_id: str,
        role: str,
        content: str,
    ) -> int:
        """Append a conversation turn to the history.
        
        Args:
            thread_id: Conversation thread identifier (e.g., from Open WebUI chat_id).
            role: Speaker role ("user", "assistant", "system").
            content: Message content.
        
        Returns:
            The ID of the newly created turn.
        
        Raises:
            ValueError: If role is not valid or content is empty.
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role: {role}")
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
        
        created_at = _now_utc_iso()
        
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """INSERT INTO conversation_turns
                   (thread_id, role, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (thread_id, role, content.strip(), created_at),
            )
            turn_id = int(cursor.lastrowid)
            logger.debug(f"Stored conversation turn {turn_id} for thread {thread_id}: {role}")
            return turn_id
    
    def get_recent_turns(
        self,
        thread_id: str,
        limit: int = 20,
    ) -> list[ConversationTurn]:
        """Retrieve recent conversation turns for a thread.
        
        Args:
            thread_id: Conversation thread identifier.
            limit: Maximum number of turns to retrieve (default: 20).
        
        Returns:
            List of ConversationTurn objects, ordered chronologically (oldest first).
        """
        with self._lock:
            cursor = self._conn.execute(
                """SELECT id, thread_id, role, content, created_at
                   FROM conversation_turns
                   WHERE thread_id = ?
                   ORDER BY created_at DESC, id DESC
                   LIMIT ?""",
                (thread_id, limit),
            )
            rows = cursor.fetchall()
        
        # Reverse to get chronological order (oldest first)
        turns = [
            ConversationTurn(
                id=row["id"],
                thread_id=row["thread_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]
        
        logger.debug(f"Retrieved {len(turns)} turns for thread {thread_id}")
        return turns
    
    def upsert_fact(self, key: str, value: str) -> int:
        """Store or update a memory fact.
        
        Args:
            key: Fact key/name (will be lowercased and stripped).
            value: Fact value.
        
        Returns:
            The ID of the fact record.
        
        Raises:
            ValueError: If key or value is empty.
        """
        if not key or not key.strip():
            raise ValueError("Key cannot be empty")
        if not value or not value.strip():
            raise ValueError("Value cannot be empty")
        
        key = key.strip().lower()
        value = value.strip()
        now = _now_utc_iso()
        
        with self._lock, self._conn:
            # Try insert first, update on conflict
            cursor = self._conn.execute(
                """INSERT INTO memory_facts (key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   updated_at = excluded.updated_at""",
                (key, value, now, now),
            )
            fact_id = int(cursor.lastrowid)
            logger.info(f"Stored memory fact: {key} = {value[:50]}...")
            return fact_id
    
    def get_fact(self, key: str) -> Optional[MemoryFact]:
        """Retrieve a single memory fact by key.
        
        Args:
            key: Fact key (case-insensitive).
        
        Returns:
            MemoryFact if found, None otherwise.
        """
        key = key.strip().lower()
        
        with self._lock:
            cursor = self._conn.execute(
                """SELECT id, key, value, created_at, updated_at
                   FROM memory_facts
                   WHERE key = ?""",
                (key,),
            )
            row = cursor.fetchone()
        
        if not row:
            return None
        
        return MemoryFact(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    def get_all_facts(self) -> list[MemoryFact]:
        """Retrieve all memory facts.
        
        Returns:
            List of MemoryFact objects, ordered by key.
        """
        with self._lock:
            cursor = self._conn.execute(
                """SELECT id, key, value, created_at, updated_at
                   FROM memory_facts
                   ORDER BY key ASC"""
            )
            rows = cursor.fetchall()
        
        facts = [
            MemoryFact(
                id=row["id"],
                key=row["key"],
                value=row["value"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(facts)} memory facts")
        return facts
    
    def delete_fact(self, key: str) -> bool:
        """Delete a memory fact.
        
        Args:
            key: Fact key (case-insensitive).
        
        Returns:
            True if fact was deleted, False if not found.
        """
        key = key.strip().lower()
        
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """DELETE FROM memory_facts WHERE key = ?""",
                (key,),
            )
            deleted = cursor.rowcount > 0
        
        if deleted:
            logger.info(f"Deleted memory fact: {key}")
        return deleted
    
    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
        logger.debug(f"Closed chat memory store: {self.db_path}")
