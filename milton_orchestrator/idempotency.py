"""Idempotency tracking for ntfy message processing.

Prevents duplicate processing of the same ntfy message, even across restarts.
Uses a simple SQLite database to track processed message IDs.
"""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class IdempotencyTracker:
    """Track processed ntfy messages to prevent duplicates."""

    def __init__(self, db_path: Path, ttl_seconds: int = 86400 * 7):
        """
        Initialize idempotency tracker.

        Args:
            db_path: Path to SQLite database file
            ttl_seconds: Time to keep processed records (default: 7 days)
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    dedupe_key TEXT PRIMARY KEY,
                    message_id TEXT,
                    topic TEXT,
                    request_id TEXT,
                    processed_at INTEGER NOT NULL,
                    message_hash TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at 
                ON processed_messages(processed_at)
            """)
            conn.commit()
            
        logger.info(f"Idempotency tracker initialized: {self.db_path}")

    def make_dedupe_key(
        self,
        message_id: Optional[str],
        topic: str,
        message: str,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Generate a stable deduplication key for a message.

        Priority:
        1. If message_id provided (from ntfy), use it
        2. Otherwise, hash topic + message + timestamp_bucket

        Args:
            message_id: ntfy message ID (if available)
            topic: ntfy topic
            message: message content
            timestamp: message timestamp (seconds since epoch)

        Returns:
            Stable dedupe key
        """
        if message_id:
            # Prefer explicit message ID from ntfy
            return f"ntfy_msg_{message_id}"

        # Fallback: hash-based key with 5-minute bucketing
        # This handles cases where same message arrives multiple times
        # within a short window (network retries, etc.)
        timestamp = timestamp or int(time.time())
        bucket = timestamp // 300  # 5-minute buckets
        
        content = f"{topic}:{bucket}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return f"ntfy_hash_{hash_val}"

    def has_processed(self, dedupe_key: str) -> bool:
        """
        Check if a message has already been processed.

        Args:
            dedupe_key: Deduplication key

        Returns:
            True if already processed, False otherwise
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_messages WHERE dedupe_key = ?",
                (dedupe_key,)
            )
            result = cursor.fetchone()
            return result is not None

    def mark_processed(
        self,
        dedupe_key: str,
        message_id: Optional[str] = None,
        topic: Optional[str] = None,
        request_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """
        Mark a message as processed.

        Args:
            dedupe_key: Deduplication key
            message_id: ntfy message ID (optional)
            topic: ntfy topic (optional)
            request_id: Milton request ID (optional)
            message: message content for hash (optional)
        """
        message_hash = None
        if message:
            message_hash = hashlib.sha256(message.encode()).hexdigest()[:16]

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_messages
                (dedupe_key, message_id, topic, request_id, processed_at, message_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (dedupe_key, message_id, topic, request_id, int(time.time()), message_hash)
            )
            conn.commit()

        logger.debug(f"Marked as processed: {dedupe_key}")

    def cleanup_old_records(self) -> int:
        """
        Remove old processed records beyond TTL.

        Returns:
            Number of records deleted
        """
        cutoff = int(time.time()) - self.ttl_seconds
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM processed_messages WHERE processed_at < ?",
                (cutoff,)
            )
            conn.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old idempotency records")
        
        return deleted

    def get_stats(self) -> dict:
        """Get statistics about processed messages."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*), MIN(processed_at), MAX(processed_at) FROM processed_messages"
            )
            count, min_ts, max_ts = cursor.fetchone()
            
        return {
            "total_processed": count or 0,
            "oldest_record": min_ts,
            "newest_record": max_ts,
            "ttl_seconds": self.ttl_seconds,
        }
