"""User preferences and defaults for Milton.

Stores per-session/per-user preferences including:
- Default reminder channel, priority, topic
- Default times (later, briefing)
- Per-category learning toggles
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UserPreferences:
    """User preference settings."""
    session_id: str
    reminder_channel: str = "ntfy"
    reminder_priority: int = 5
    reminder_topic: Optional[str] = None
    default_later_time: str = "18:00"
    briefing_time: str = "08:00"
    learn_goals: bool = True
    learn_reminders: bool = True
    learn_briefings: bool = True
    learn_memory: bool = False  # More sensitive, default off
    updated_at: Optional[str] = None


class Preferences:
    """SQLite-backed user preferences store."""
    
    def __init__(self, db_path: Path):
        """Initialize preferences store.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Create the preferences table if it doesn't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    session_id TEXT PRIMARY KEY,
                    reminder_channel TEXT DEFAULT 'ntfy',
                    reminder_priority INTEGER DEFAULT 5,
                    reminder_topic TEXT,
                    default_later_time TEXT DEFAULT '18:00',
                    briefing_time TEXT DEFAULT '08:00',
                    learn_goals INTEGER DEFAULT 1,
                    learn_reminders INTEGER DEFAULT 1,
                    learn_briefings INTEGER DEFAULT 1,
                    learn_memory INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
    
    def get(self, session_id: str) -> UserPreferences:
        """Get preferences for a session, creating defaults if needed.
        
        Args:
            session_id: Session/user identifier
        
        Returns:
            UserPreferences
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM preferences WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            
            if not row:
                # Create defaults
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT INTO preferences (
                        session_id, updated_at
                    ) VALUES (?, ?)
                """, (session_id, now))
                conn.commit()
                
                return UserPreferences(session_id=session_id, updated_at=now)
            
            return UserPreferences(
                session_id=row['session_id'],
                reminder_channel=row['reminder_channel'],
                reminder_priority=row['reminder_priority'],
                reminder_topic=row['reminder_topic'],
                default_later_time=row['default_later_time'],
                briefing_time=row['briefing_time'],
                learn_goals=bool(row['learn_goals']),
                learn_reminders=bool(row['learn_reminders']),
                learn_briefings=bool(row['learn_briefings']),
                learn_memory=bool(row['learn_memory']),
                updated_at=row['updated_at']
            )
    
    def set_reminder_channel(self, session_id: str, channel: str):
        """Set default reminder channel.
        
        Args:
            session_id: Session identifier
            channel: Channel name (e.g., "ntfy", "voice")
        """
        self._update_field(session_id, "reminder_channel", channel)
    
    def set_reminder_priority(self, session_id: str, priority: int):
        """Set default reminder priority.
        
        Args:
            session_id: Session identifier
            priority: Priority level (1-10)
        """
        if not 1 <= priority <= 10:
            raise ValueError("Priority must be between 1 and 10")
        self._update_field(session_id, "reminder_priority", priority)
    
    def set_reminder_topic(self, session_id: str, topic: str):
        """Set default reminder ntfy topic.
        
        Args:
            session_id: Session identifier
            topic: ntfy topic name
        """
        self._update_field(session_id, "reminder_topic", topic)
    
    def set_default_later_time(self, session_id: str, time_str: str):
        """Set default 'later' time.
        
        Args:
            session_id: Session identifier
            time_str: Time in HH:MM format (e.g., "18:00")
        """
        self._update_field(session_id, "default_later_time", time_str)
    
    def set_briefing_time(self, session_id: str, time_str: str):
        """Set default briefing time.
        
        Args:
            session_id: Session identifier
            time_str: Time in HH:MM format (e.g., "08:00")
        """
        self._update_field(session_id, "briefing_time", time_str)
    
    def set_learning_enabled(self, session_id: str, category: str, enabled: bool):
        """Set learning enabled/disabled for a category.
        
        Args:
            session_id: Session identifier
            category: One of "goals", "reminders", "briefings", "memory"
            enabled: True to enable learning, False to disable
        """
        field_map = {
            "goals": "learn_goals",
            "reminders": "learn_reminders",
            "briefings": "learn_briefings",
            "memory": "learn_memory"
        }
        
        if category not in field_map:
            raise ValueError(f"Invalid category: {category}. Must be one of {list(field_map.keys())}")
        
        self._update_field(session_id, field_map[category], 1 if enabled else 0)
    
    def get_learning_enabled(self, session_id: str, category: str) -> bool:
        """Check if learning is enabled for a category.
        
        Args:
            session_id: Session identifier
            category: One of "goal", "reminder", "briefing", "memory" (entity type)
        
        Returns:
            True if learning enabled, False otherwise
        """
        prefs = self.get(session_id)
        
        # Map entity types to preference fields
        if category in ("goal", "goals"):
            return prefs.learn_goals
        elif category in ("reminder", "reminders"):
            return prefs.learn_reminders
        elif category in ("briefing", "briefings"):
            return prefs.learn_briefings
        elif category in ("memory",):
            return prefs.learn_memory
        else:
            # Unknown category, default to disabled for safety
            return False
    
    def _update_field(self, session_id: str, field: str, value):
        """Update a single preference field.
        
        Args:
            session_id: Session identifier
            field: Field name
            value: New value
        """
        # Ensure preferences exist
        self.get(session_id)
        
        now = datetime.now().isoformat()
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(f"""
                UPDATE preferences 
                SET {field} = ?, updated_at = ?
                WHERE session_id = ?
            """, (value, now, session_id))
            conn.commit()
        
        logger.info(f"Updated preference {field}={value} for session {session_id}")
    
    def get_all_preferences_text(self, session_id: str) -> str:
        """Get formatted text of all preferences.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Formatted text string
        """
        prefs = self.get(session_id)
        
        return f"""**Your Current Preferences**

**Reminders:**
- Default channel: {prefs.reminder_channel}
- Default priority: {prefs.reminder_priority}
- Default topic: {prefs.reminder_topic or "(none)"}

**Times:**
- Default 'later' time: {prefs.default_later_time}
- Briefing time: {prefs.briefing_time}

**Learning (per category):**
- Goals: {"✅ enabled" if prefs.learn_goals else "❌ disabled"}
- Reminders: {"✅ enabled" if prefs.learn_reminders else "❌ disabled"}
- Briefings: {"✅ enabled" if prefs.learn_briefings else "❌ disabled"}
- Memory: {"✅ enabled" if prefs.learn_memory else "❌ disabled"}

_To change preferences, say: "Set default reminder priority to 8" or "Disable learning for reminders"_
"""
