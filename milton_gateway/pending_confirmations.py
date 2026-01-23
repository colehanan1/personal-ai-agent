"""Pending confirmation store for natural language command workflow.

Manages temporary state for commands requiring user confirmation (Yes/No/Edit).
Confirmations expire after a timeout period.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class PendingConfirmation:
    """A command awaiting user confirmation.
    
    Attributes:
        session_id: Unique session/thread identifier
        pending_id: Unique confirmation ID
        created_at: ISO8601 timestamp when created
        original_text: User's original natural language input
        candidate_json: Parsed intent as JSON (ready for execution)
        confidence: Parser confidence score (0.0-1.0)
        expiry: ISO8601 timestamp when this expires
    """
    session_id: str
    pending_id: str
    created_at: str
    original_text: str
    candidate_json: str
    confidence: float
    expiry: str


class PendingConfirmationStore:
    """SQLite-based store for pending confirmations."""
    
    def __init__(self, db_path: Path):
        """Initialize the store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    session_id TEXT NOT NULL,
                    pending_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    expiry TEXT NOT NULL
                )
            """)
            # Index for fast session lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_id 
                ON pending_confirmations(session_id)
            """)
            conn.commit()
    
    def store(self, confirmation: PendingConfirmation) -> None:
        """Store a pending confirmation.
        
        Args:
            confirmation: The confirmation to store
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pending_confirmations
                (session_id, pending_id, created_at, original_text, 
                 candidate_json, confidence, expiry)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                confirmation.session_id,
                confirmation.pending_id,
                confirmation.created_at,
                confirmation.original_text,
                confirmation.candidate_json,
                confirmation.confidence,
                confirmation.expiry
            ))
            conn.commit()
        logger.debug(f"Stored pending confirmation {confirmation.pending_id} for session {confirmation.session_id}")
    
    def get(self, session_id: str) -> Optional[PendingConfirmation]:
        """Get the most recent non-expired pending confirmation for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            PendingConfirmation if found and not expired, None otherwise
        """
        now = datetime.now(timezone.utc).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM pending_confirmations
                WHERE session_id = ? AND expiry > ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id, now))
            
            row = cursor.fetchone()
            if row:
                return PendingConfirmation(**dict(row))
            return None
    
    def clear(self, session_id: str) -> None:
        """Clear all pending confirmations for a session.
        
        Args:
            session_id: Session identifier
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM pending_confirmations
                WHERE session_id = ?
            """, (session_id,))
            conn.commit()
        logger.debug(f"Cleared pending confirmations for session {session_id}")
    
    def cleanup_expired(self) -> int:
        """Remove expired confirmations.
        
        Returns:
            Number of rows deleted
        """
        now = datetime.now(timezone.utc).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM pending_confirmations
                WHERE expiry <= ?
            """, (now,))
            conn.commit()
            deleted = cursor.rowcount
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired pending confirmations")
        
        return deleted
