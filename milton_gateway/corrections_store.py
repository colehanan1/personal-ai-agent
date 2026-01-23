"""Corrections store for learning from user feedback.

Tracks user corrections (Edit, rephrases, confirmations) to improve
intent selection and confidence over time.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from milton_gateway.phrase_normalization import normalize_phrase, jaccard_similarity

logger = logging.getLogger(__name__)


@dataclass
class Correction:
    """A user correction that Milton can learn from.
    
    Attributes:
        id: Unique correction ID
        created_at: ISO8601 timestamp when created
        updated_at: ISO8601 timestamp when last updated
        phrase_original: Raw user utterance
        phrase_normalized: Normalized fingerprint for matching
        intent_before_json: Original parser output (JSON string)
        intent_after_json: Corrected intent after user feedback (JSON string)
        outcome: How this correction was created (edited/rephrased/confirmed)
        times_seen: Number of times this correction has been referenced
        last_seen_at: ISO8601 timestamp of last reference
    """
    id: int
    created_at: str
    updated_at: str
    phrase_original: str
    phrase_normalized: str
    intent_before_json: str
    intent_after_json: str
    outcome: str  # "edited", "rephrased", "confirmed"
    times_seen: int
    last_seen_at: str


class CorrectionsStore:
    """SQLite-based store for learning from user corrections."""
    
    def __init__(self, db_path: Path, enabled: bool = True):
        """Initialize the corrections store.
        
        Args:
            db_path: Path to SQLite database file
            enabled: Whether learning is enabled (LEARN_FROM_CORRECTIONS)
        """
        self.db_path = db_path
        self.enabled = enabled
        
        if enabled:
            self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    phrase_original TEXT NOT NULL,
                    phrase_normalized TEXT NOT NULL,
                    intent_before_json TEXT NOT NULL,
                    intent_after_json TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    times_seen INTEGER DEFAULT 1,
                    last_seen_at TEXT NOT NULL
                )
            """)
            
            # Index for fast normalized phrase lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_phrase_normalized
                ON corrections(phrase_normalized)
            """)
            
            # Index for outcome filtering
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcome
                ON corrections(outcome)
            """)
            
            conn.commit()
        
        logger.info(f"Initialized corrections store at {self.db_path}")
    
    def store(self, correction: Correction) -> int:
        """Store or update a correction.
        
        Args:
            correction: The correction to store
            
        Returns:
            The correction ID
        """
        if not self.enabled:
            return -1
        
        with sqlite3.connect(self.db_path) as conn:
            # Check if similar correction already exists
            existing = self.find_similar(correction.phrase_original, limit=1)
            
            if existing:
                # Update existing correction
                existing_correction = existing[0]
                conn.execute("""
                    UPDATE corrections
                    SET updated_at = ?,
                        intent_after_json = ?,
                        times_seen = times_seen + 1,
                        last_seen_at = ?
                    WHERE id = ?
                """, (
                    correction.updated_at,
                    correction.intent_after_json,
                    correction.last_seen_at,
                    existing_correction.id
                ))
                logger.info(f"Updated existing correction {existing_correction.id}")
                return existing_correction.id
            else:
                # Insert new correction
                cursor = conn.execute("""
                    INSERT INTO corrections
                    (created_at, updated_at, phrase_original, phrase_normalized,
                     intent_before_json, intent_after_json, outcome, times_seen, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    correction.created_at,
                    correction.updated_at,
                    correction.phrase_original,
                    correction.phrase_normalized,
                    correction.intent_before_json,
                    correction.intent_after_json,
                    correction.outcome,
                    correction.times_seen,
                    correction.last_seen_at
                ))
                conn.commit()
                correction_id = cursor.lastrowid
                logger.info(f"Stored new correction {correction_id} from {correction.outcome}")
                return correction_id
    
    def find_similar(self, phrase: str, limit: int = 5, threshold: float = 0.55) -> List[Correction]:
        """Find corrections similar to the given phrase.
        
        Args:
            phrase: User utterance to match against
            limit: Maximum number of results
            threshold: Jaccard similarity threshold (default 0.55)
            
        Returns:
            List of similar corrections, sorted by similarity (descending)
        """
        if not self.enabled:
            return []
        
        normalized = normalize_phrase(phrase)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get all corrections (we'll filter by similarity in Python)
            # In production, could add embeddings or more sophisticated indexing
            cursor = conn.execute("""
                SELECT * FROM corrections
                ORDER BY times_seen DESC, last_seen_at DESC
                LIMIT 100
            """)
            
            candidates = []
            for row in cursor:
                correction = Correction(**dict(row))
                similarity = jaccard_similarity(normalized, correction.phrase_normalized)
                
                if similarity >= threshold:
                    candidates.append((similarity, correction))
            
            # Sort by similarity descending, then by times_seen
            candidates.sort(key=lambda x: (x[0], x[1].times_seen), reverse=True)
            
            return [corr for _, corr in candidates[:limit]]
    
    def get_by_id(self, correction_id: int) -> Optional[Correction]:
        """Get a correction by ID.
        
        Args:
            correction_id: Correction ID
            
        Returns:
            Correction if found, None otherwise
        """
        if not self.enabled:
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM corrections
                WHERE id = ?
            """, (correction_id,))
            
            row = cursor.fetchone()
            if row:
                return Correction(**dict(row))
            return None
    
    def increment_seen(self, correction_id: int) -> None:
        """Increment the times_seen counter for a correction.
        
        Args:
            correction_id: Correction ID
        """
        if not self.enabled:
            return
        
        now = datetime.now(timezone.utc).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE corrections
                SET times_seen = times_seen + 1,
                    last_seen_at = ?
                WHERE id = ?
            """, (now, correction_id))
            conn.commit()
        
        logger.debug(f"Incremented seen count for correction {correction_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the corrections store.
        
        Returns:
            Dictionary with stats (total, by_outcome, avg_times_seen)
        """
        if not self.enabled:
            return {"enabled": False}
        
        with sqlite3.connect(self.db_path) as conn:
            # Total corrections
            cursor = conn.execute("SELECT COUNT(*) FROM corrections")
            total = cursor.fetchone()[0]
            
            # By outcome
            cursor = conn.execute("""
                SELECT outcome, COUNT(*) as count
                FROM corrections
                GROUP BY outcome
            """)
            by_outcome = {row[0]: row[1] for row in cursor}
            
            # Average times seen
            cursor = conn.execute("SELECT AVG(times_seen) FROM corrections")
            avg_times_seen = cursor.fetchone()[0] or 0
            
            return {
                "enabled": True,
                "total": total,
                "by_outcome": by_outcome,
                "avg_times_seen": round(avg_times_seen, 2)
            }
