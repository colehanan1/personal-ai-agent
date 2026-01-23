"""Context tracker for cross-message linking.

Tracks recent entities and pending confirmations so follow-up messages
like "make that weekly" can modify the correct draft or committed entity.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass


CONTEXT_EXPIRY_MINUTES = 10  # How long context is remembered


@dataclass
class SessionContext:
    """Context for a session (recent entities and actions)."""
    session_id: str
    last_pending_id: Optional[str] = None
    last_entity_type: Optional[str] = None
    last_entity_id: Optional[str] = None
    last_action_id: Optional[str] = None
    last_entity_snapshot: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class ContextTracker:
    """In-memory tracker for session context."""
    
    def __init__(self):
        """Initialize context tracker."""
        self._contexts: Dict[str, SessionContext] = {}
    
    def update_pending(self, session_id: str, pending_id: str, candidate: Dict[str, Any]):
        """Update context when a pending confirmation is created.
        
        Args:
            session_id: Session identifier
            pending_id: Pending confirmation ID
            candidate: Candidate intent dictionary
        """
        if session_id not in self._contexts:
            self._contexts[session_id] = SessionContext(session_id=session_id)
        
        ctx = self._contexts[session_id]
        ctx.last_pending_id = pending_id
        ctx.last_entity_type = candidate.get('intent_type')
        ctx.last_entity_snapshot = candidate.get('payload', {})
        ctx.timestamp = datetime.now()
    
    def update_committed(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        action_id: str,
        snapshot: Dict[str, Any]
    ):
        """Update context when an action is committed.
        
        Args:
            session_id: Session identifier
            entity_type: Type of entity (goal/reminder/etc)
            entity_id: Entity ID
            action_id: Action ID from ledger
            snapshot: Entity snapshot
        """
        if session_id not in self._contexts:
            self._contexts[session_id] = SessionContext(session_id=session_id)
        
        ctx = self._contexts[session_id]
        ctx.last_pending_id = None  # Clear pending since it's committed
        ctx.last_entity_type = entity_type
        ctx.last_entity_id = entity_id
        ctx.last_action_id = action_id
        ctx.last_entity_snapshot = snapshot
        ctx.timestamp = datetime.now()
    
    def get_context(self, session_id: str) -> Optional[SessionContext]:
        """Get context for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            SessionContext or None if expired/not found
        """
        if session_id not in self._contexts:
            return None
        
        ctx = self._contexts[session_id]
        
        # Check expiry
        if ctx.timestamp:
            age = datetime.now() - ctx.timestamp
            if age > timedelta(minutes=CONTEXT_EXPIRY_MINUTES):
                # Expired, clear context
                del self._contexts[session_id]
                return None
        
        return ctx
    
    def clear_context(self, session_id: str):
        """Clear context for a session.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._contexts:
            del self._contexts[session_id]


class AnaphoraResolver:
    """Resolve anaphoric references like 'that', 'it', 'make X'."""
    
    @staticmethod
    def is_anaphoric_reference(text: str) -> bool:
        """Check if text contains anaphoric reference.
        
        Args:
            text: User message
        
        Returns:
            True if anaphoric reference detected
        """
        text_lower = text.lower().strip()
        
        # Patterns indicating reference to previous entity
        patterns = [
            r'^(make|change|set)\s+(that|it)\s+',
            r'^(update|modify|edit)\s+(that|it)\b',
            r'^rename\s+(that|it)\s+to\b',
            r'^change\s+(that|it)\s+to\b',
            r'^make\s+(that|it)\s+\w+',
            r'^\w+\s+that\s+(to|at)\b',  # "schedule that at", "move that to"
        ]
        
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    @staticmethod
    def extract_modification(text: str) -> Optional[Dict[str, Any]]:
        """Extract modification intent from anaphoric reference.
        
        Args:
            text: User message (e.g., "make that weekly", "change it to 9am")
        
        Returns:
            Dictionary of field modifications or None
        """
        text_lower = text.lower().strip()
        modifications = {}
        
        # Cadence changes: "make that weekly/daily/monthly"
        cadence_match = re.search(r'\b(make|change|set).*\b(daily|weekly|monthly)\b', text_lower)
        if cadence_match:
            modifications['cadence'] = cadence_match.group(2)
        
        # Time changes: "change it to 9am", "move that to 3pm"
        time_match = re.search(r'\b(change|set|move|schedule).*\b(to|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b', text_lower)
        if time_match:
            modifications['time'] = time_match.group(3).strip()
        
        # Priority changes: "make that high priority", "set priority to 8"
        priority_match = re.search(r'\b(priority|pri)\s*(?:to)?\s*(\d+|high|medium|low)\b', text_lower)
        if priority_match:
            priority_val = priority_match.group(2)
            if priority_val.isdigit():
                modifications['priority'] = int(priority_val)
            else:
                # Map words to numbers
                priority_map = {'low': 3, 'medium': 5, 'med': 5, 'high': 8}
                modifications['priority'] = priority_map.get(priority_val, 5)
        
        # Rename: "rename it to X", "change that to Y"
        rename_match = re.search(r'\b(rename|change).*\bto\s+(.+)$', text_lower)
        if rename_match and 'cadence' not in modifications and 'time' not in modifications:
            new_text = rename_match.group(2).strip()
            # Clean up quotes
            new_text = new_text.strip('"\'')
            modifications['text'] = new_text
        
        return modifications if modifications else None
    
    @staticmethod
    def format_disambiguation_prompt(contexts: list) -> str:
        """Format a prompt when multiple entities could be referenced.
        
        Args:
            contexts: List of possible entity contexts
        
        Returns:
            Formatted prompt
        """
        lines = ["I found multiple recent items. Which one did you mean?\n"]
        
        for i, ctx in enumerate(contexts, 1):
            entity_type = ctx.get('entity_type', 'item')
            snapshot = ctx.get('snapshot', {})
            
            if entity_type == 'goal':
                text = snapshot.get('text', snapshot.get('description', '(no text)'))
                cadence = snapshot.get('cadence', 'daily')
                lines.append(f"{i}. Goal ({cadence}): \"{text}\"")
            
            elif entity_type == 'reminder':
                text = snapshot.get('text', snapshot.get('title', '(no text)'))
                due = snapshot.get('due_at', '')
                lines.append(f"{i}. Reminder: \"{text}\" due {due}")
            
            elif entity_type == 'briefing':
                text = snapshot.get('text', snapshot.get('content', '(no text)'))
                lines.append(f"{i}. Briefing: \"{text}\"")
            
            else:
                lines.append(f"{i}. {entity_type.capitalize()}")
        
        lines.append("\nReply with the number (1, 2, etc.) or rephrase your request.")
        
        return "\n".join(lines)
