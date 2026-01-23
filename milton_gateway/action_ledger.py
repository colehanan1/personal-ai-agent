"""Action Ledger for undo/rollback and audit logging.

Tracks all state-changing actions (create/update/delete) for goals, reminders,
briefings, and memory. Provides:
- Undo functionality with time-bounded expiry (30 minutes default)
- Action receipts with undo tokens
- Audit log for "what changed?" queries
"""

from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import string
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Entity types that can be tracked in the ledger."""
    GOAL = "goal"
    REMINDER = "reminder"
    BRIEFING = "briefing"
    MEMORY = "memory"


class Operation(str, Enum):
    """Operations that can be performed on entities."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    UNDO = "undo"


@dataclass
class ActionReceipt:
    """Receipt returned after committing an action."""
    action_id: str
    undo_token: str
    entity_type: str
    entity_id: str
    operation: str
    summary: str
    timestamp: str
    undo_expires_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert receipt to dictionary."""
        return asdict(self)
    
    def to_markdown(self) -> str:
        """Format receipt as markdown for display."""
        return f"""✅ **{self.operation.upper()}** {self.entity_type}

{self.summary}

**Action ID**: `{self.action_id}`
**Undo Token**: `{self.undo_token}` (expires {self.undo_expires_at})

_To undo this action, say: "undo" or "undo {self.undo_token}"_"""


@dataclass
class ActionRecord:
    """Internal representation of an action in the ledger."""
    action_id: str
    session_id: str
    timestamp: str
    entity_type: str
    entity_id: str
    operation: str
    before_snapshot: Optional[str]  # JSON
    after_snapshot: str  # JSON
    undo_expiry: str
    undo_token: str
    undone_at: Optional[str]
    created_at: str


class ActionLedger:
    """SQLite-backed action ledger for undo and audit logging."""
    
    # Default undo expiry: 30 minutes
    DEFAULT_UNDO_EXPIRY_MINUTES = 30
    
    def __init__(self, db_path: Path, undo_expiry_minutes: int = DEFAULT_UNDO_EXPIRY_MINUTES):
        """Initialize the action ledger.
        
        Args:
            db_path: Path to SQLite database
            undo_expiry_minutes: How long undo tokens are valid (default: 30)
        """
        self.db_path = db_path
        self.undo_expiry_minutes = undo_expiry_minutes
        self._init_db()
    
    def _init_db(self):
        """Create the action_ledger table if it doesn't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_ledger (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    before_snapshot TEXT,
                    after_snapshot TEXT NOT NULL,
                    undo_expiry TEXT NOT NULL,
                    undo_token TEXT NOT NULL,
                    undone_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_time 
                ON action_ledger(session_id, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_undo_token 
                ON action_ledger(undo_token)
            """)
            conn.commit()
    
    def _generate_action_id(self) -> str:
        """Generate a unique action ID."""
        return f"act_{secrets.token_hex(8)}"
    
    def _generate_undo_token(self) -> str:
        """Generate a readable 8-character undo token."""
        # Use uppercase letters and numbers, avoiding ambiguous characters (0, O, 1, I)
        alphabet = string.ascii_uppercase.replace('O', '').replace('I', '') + '23456789'
        return ''.join(secrets.choice(alphabet) for _ in range(8))
    
    def record(
        self,
        session_id: str,
        entity_type: EntityType | str,
        entity_id: str,
        operation: Operation | str,
        before_snapshot: Optional[Dict[str, Any]],
        after_snapshot: Dict[str, Any],
        now: Optional[datetime] = None
    ) -> ActionReceipt:
        """Record an action in the ledger.
        
        Args:
            session_id: Session/user identifier
            entity_type: Type of entity (goal/reminder/briefing/memory)
            entity_id: ID of the entity
            operation: Operation performed (create/update/delete)
            before_snapshot: Entity state before action (None for creates)
            after_snapshot: Entity state after action
            now: Current time (for testing; defaults to now)
        
        Returns:
            ActionReceipt with undo token
        """
        if now is None:
            now = datetime.now()
        
        action_id = self._generate_action_id()
        undo_token = self._generate_undo_token()
        undo_expiry = now + timedelta(minutes=self.undo_expiry_minutes)
        
        timestamp = now.isoformat()
        undo_expiry_str = undo_expiry.isoformat()
        
        # Convert entity type and operation to strings
        entity_type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type
        operation_str = operation.value if isinstance(operation, Operation) else operation
        
        # Serialize snapshots to JSON
        before_json = json.dumps(before_snapshot) if before_snapshot else None
        after_json = json.dumps(after_snapshot)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO action_ledger (
                    action_id, session_id, timestamp, entity_type, entity_id,
                    operation, before_snapshot, after_snapshot, undo_expiry,
                    undo_token, undone_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_id, session_id, timestamp, entity_type_str, entity_id,
                operation_str, before_json, after_json, undo_expiry_str,
                undo_token, None, timestamp
            ))
            conn.commit()
        
        logger.info(f"Recorded action {action_id} ({operation_str} {entity_type_str} {entity_id})")
        
        return self.generate_receipt(action_id)
    
    def generate_receipt(self, action_id: str) -> ActionReceipt:
        """Generate a receipt for an action.
        
        Args:
            action_id: Action ID to generate receipt for
        
        Returns:
            ActionReceipt
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM action_ledger WHERE action_id = ?
            """, (action_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Action {action_id} not found")
            
            # Parse after_snapshot to generate summary
            after = json.loads(row['after_snapshot'])
            summary = self._generate_summary(
                row['operation'],
                row['entity_type'],
                after
            )
            
            return ActionReceipt(
                action_id=row['action_id'],
                undo_token=row['undo_token'],
                entity_type=row['entity_type'],
                entity_id=row['entity_id'],
                operation=row['operation'],
                summary=summary,
                timestamp=row['timestamp'],
                undo_expires_at=row['undo_expiry']
            )
    
    def _generate_summary(self, operation: str, entity_type: str, snapshot: Dict[str, Any]) -> str:
        """Generate a human-readable summary of an action."""
        if entity_type == "reminder":
            text = snapshot.get('text', snapshot.get('title', 'reminder'))
            due = snapshot.get('due_at', snapshot.get('due_date', ''))
            if due:
                due_str = due.split('T')[0] if 'T' in due else due
                return f"{operation.capitalize()} reminder: \"{text}\" due {due_str}"
            return f"{operation.capitalize()} reminder: \"{text}\""
        
        elif entity_type == "goal":
            text = snapshot.get('text', snapshot.get('description', 'goal'))
            cadence = snapshot.get('cadence', 'daily')
            return f"{operation.capitalize()} {cadence} goal: \"{text}\""
        
        elif entity_type == "briefing":
            text = snapshot.get('text', snapshot.get('content', 'briefing item'))
            return f"{operation.capitalize()} briefing item: \"{text}\""
        
        elif entity_type == "memory":
            key = snapshot.get('key', 'memory')
            value = snapshot.get('value', '')
            return f"{operation.capitalize()} memory: {key} = {value}"
        
        return f"{operation.capitalize()} {entity_type}"
    
    def undo(self, session_id: str, token: Optional[str] = None, now: Optional[datetime] = None) -> tuple[bool, str]:
        """Undo an action by token or the most recent action.
        
        Args:
            session_id: Session/user identifier
            token: Undo token (if None, undoes last action)
            now: Current time (for testing; defaults to now)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if now is None:
            now = datetime.now()
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            
            if token:
                # Find action by token
                cursor = conn.execute("""
                    SELECT * FROM action_ledger 
                    WHERE undo_token = ? AND session_id = ? AND undone_at IS NULL
                """, (token, session_id))
            else:
                # Find most recent undoable action
                cursor = conn.execute("""
                    SELECT * FROM action_ledger 
                    WHERE session_id = ? AND undone_at IS NULL AND operation != 'undo'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (session_id,))
            
            row = cursor.fetchone()
            
            if not row:
                if token:
                    return False, f"No undoable action found with token '{token}'."
                return False, "No recent action to undo."
            
            # Check expiry
            undo_expiry = datetime.fromisoformat(row['undo_expiry'])
            if now > undo_expiry:
                return False, f"Undo expired (was valid until {row['undo_expiry']})."
            
            # Mark as undone
            conn.execute("""
                UPDATE action_ledger SET undone_at = ? WHERE action_id = ?
            """, (now.isoformat(), row['action_id']))
            conn.commit()
            
            # Return undo instructions
            operation = row['operation']
            entity_type = row['entity_type']
            entity_id = row['entity_id']
            before_json = row['before_snapshot']
            
            if operation == 'create':
                instruction = f"delete_{entity_type}:{entity_id}"
            elif operation == 'delete':
                instruction = f"restore_{entity_type}:{entity_id}:{before_json}"
            elif operation == 'update':
                instruction = f"restore_{entity_type}:{entity_id}:{before_json}"
            else:
                instruction = None
            
            logger.info(f"Undone action {row['action_id']} for session {session_id}")
            
            return True, instruction
    
    def get_last_action(self, session_id: str) -> Optional[ActionRecord]:
        """Get the most recent action for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            ActionRecord or None
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM action_ledger 
                WHERE session_id = ? AND undone_at IS NULL
                ORDER BY timestamp DESC
                LIMIT 1
            """, (session_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return ActionRecord(
                action_id=row['action_id'],
                session_id=row['session_id'],
                timestamp=row['timestamp'],
                entity_type=row['entity_type'],
                entity_id=row['entity_id'],
                operation=row['operation'],
                before_snapshot=row['before_snapshot'],
                after_snapshot=row['after_snapshot'],
                undo_expiry=row['undo_expiry'],
                undo_token=row['undo_token'],
                undone_at=row['undone_at'],
                created_at=row['created_at']
            )
    
    def get_actions_by_date(
        self,
        session_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[ActionRecord]:
        """Get all actions within a date range.
        
        Args:
            session_id: Session identifier
            start_date: Start of range (inclusive)
            end_date: End of range (exclusive)
        
        Returns:
            List of ActionRecord
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM action_ledger 
                WHERE session_id = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC
            """, (session_id, start_date.isoformat(), end_date.isoformat()))
            
            records = []
            for row in cursor:
                records.append(ActionRecord(
                    action_id=row['action_id'],
                    session_id=row['session_id'],
                    timestamp=row['timestamp'],
                    entity_type=row['entity_type'],
                    entity_id=row['entity_id'],
                    operation=row['operation'],
                    before_snapshot=row['before_snapshot'],
                    after_snapshot=row['after_snapshot'],
                    undo_expiry=row['undo_expiry'],
                    undo_token=row['undo_token'],
                    undone_at=row['undone_at'],
                    created_at=row['created_at']
                ))
            
            return records
