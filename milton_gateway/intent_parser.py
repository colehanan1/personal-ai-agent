"""Natural-language intent parser for Milton Gateway.

Parses plain English messages and maps them to Milton command intents
(goal, briefing, reminder, memory) without requiring explicit slash commands.

This module provides plumbing for natural language understanding but does not
modify production routing. It's designed to be deterministic and testable.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, Any

import dateparser


class IntentType(Enum):
    """Supported intent types."""
    GOAL = "goal"
    BRIEFING = "briefing"
    REMINDER = "reminder"
    MEMORY = "memory"
    UNKNOWN = "unknown"


class IntentAction(Enum):
    """Supported actions for each intent type."""
    ADD = "add"
    LIST = "list"
    SHOW = "show"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of parsing a natural language message into a structured intent.
    
    Attributes:
        intent_type: The type of command (goal, briefing, reminder, memory)
        action: The action to perform (add, list, show)
        payload: Structured data for the command (text, time, scope, etc.)
        confidence: Confidence score 0.0-1.0 (1.0 = high confidence)
        needs_clarification: True if intent is ambiguous
        clarifying_question: Optional question to ask the user
    """
    intent_type: IntentType
    action: IntentAction
    payload: Dict[str, Any]
    confidence: float
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None


def parse_nl_intent(text: str, now: Optional[datetime] = None) -> IntentResult:
    """Parse a natural language message into a structured intent.
    
    Args:
        text: The user's message
        now: Current time for relative date parsing (defaults to UTC now)
        
    Returns:
        IntentResult with parsed intent, action, and payload
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    text = text.strip()
    text_lower = text.lower()
    
    # Skip slash commands - they should be handled by the existing command processor
    if text.startswith("/"):
        return IntentResult(
            intent_type=IntentType.UNKNOWN,
            action=IntentAction.UNKNOWN,
            payload={},
            confidence=0.0,
            needs_clarification=False
        )
    
    # Try to parse each intent type
    result = (
        _parse_goal_intent(text, text_lower, now) or
        _parse_briefing_intent(text, text_lower, now) or
        _parse_reminder_intent(text, text_lower, now) or
        _parse_memory_intent(text, text_lower, now)
    )
    
    if result:
        return result
    
    # No clear intent detected
    return IntentResult(
        intent_type=IntentType.UNKNOWN,
        action=IntentAction.UNKNOWN,
        payload={},
        confidence=0.0,
        needs_clarification=False
    )


def _parse_goal_intent(text: str, text_lower: str, now: datetime) -> Optional[IntentResult]:
    """Parse goal-related intents."""
    
    # List patterns
    list_patterns = [
        r'\b(list|show|what are|what\'s|whats)\b.*\bgoals?\b',
        r'\bgoals?\s+(list|show)\b',
    ]
    
    for pattern in list_patterns:
        if re.search(pattern, text_lower):
            # Detect scope
            scope = "daily"  # default
            if re.search(r'\b(weekly|week)\b', text_lower):
                scope = "weekly"
            elif re.search(r'\b(monthly|month)\b', text_lower):
                scope = "monthly"
            
            return IntentResult(
                intent_type=IntentType.GOAL,
                action=IntentAction.LIST,
                payload={"scope": scope},
                confidence=0.9
            )
    
    # Add patterns
    add_patterns = [
        r'\b(add|set|create|new)\b.*\bgoal\b',
        r'\bgoal\s*:\s*',
    ]
    
    for pattern in add_patterns:
        match = re.search(pattern, text_lower)
        if match:
            # Extract goal text
            goal_text = text
            
            # Try to extract text after the pattern
            if "goal:" in text_lower:
                goal_text = text.split(":", 1)[1].strip()
            elif match:
                # Remove the matched pattern from the beginning
                goal_text = text[match.end():].strip()
            
            # Detect scope
            scope = "daily"  # default
            if re.search(r'\b(weekly|week)\b', text_lower):
                scope = "weekly"
                goal_text = re.sub(r'\s*\|?\s*\b(weekly|week)\b', '', goal_text, flags=re.IGNORECASE)
            elif re.search(r'\b(monthly|month)\b', text_lower):
                scope = "monthly"
                goal_text = re.sub(r'\s*\|?\s*\b(monthly|month)\b', '', goal_text, flags=re.IGNORECASE)
            
            goal_text = goal_text.strip()
            
            if not goal_text or len(goal_text) < 3:
                return IntentResult(
                    intent_type=IntentType.GOAL,
                    action=IntentAction.ADD,
                    payload={},
                    confidence=0.5,
                    needs_clarification=True,
                    clarifying_question="What goal would you like to add?"
                )
            
            return IntentResult(
                intent_type=IntentType.GOAL,
                action=IntentAction.ADD,
                payload={"text": goal_text, "scope": scope},
                confidence=0.9
            )
    
    return None


def _parse_briefing_intent(text: str, text_lower: str, now: datetime) -> Optional[IntentResult]:
    """Parse briefing-related intents."""
    
    # List patterns
    list_patterns = [
        r'\b(briefing|morning briefing)\s+(list|show)\b',
        r'\b(list|show)\b.*\b(briefing|morning briefing)\b',
        r'^briefing$',
    ]
    
    for pattern in list_patterns:
        if re.search(pattern, text_lower):
            return IntentResult(
                intent_type=IntentType.BRIEFING,
                action=IntentAction.LIST,
                payload={},
                confidence=0.9
            )
    
    # Add patterns
    add_patterns = [
        r'\b(add to|add|put in)\b.*\b(briefing|morning briefing)\b',
        r'\b(briefing|morning briefing)\b\s*:\s*',
    ]
    
    for pattern in add_patterns:
        match = re.search(pattern, text_lower)
        if match:
            # Extract briefing text
            briefing_text = text
            
            # Try to extract text after the pattern
            if "briefing:" in text_lower or "morning briefing:" in text_lower:
                briefing_text = re.split(r'(?:briefing|morning briefing)\s*:\s*', text, flags=re.IGNORECASE)[1].strip()
            elif "add to" in text_lower or "put in" in text_lower:
                # Extract text after "add to briefing" or similar
                briefing_text = re.sub(
                    r'.*?\b(add to|put in)\b.*?\b(briefing|morning briefing)\b\s*:?\s*',
                    '',
                    text,
                    flags=re.IGNORECASE
                ).strip()
            
            # Parse priority if present
            priority = 0
            priority_match = re.search(r'\bpriority\s*[:\s]*(\d+)\b', text_lower)
            if priority_match:
                priority = int(priority_match.group(1))
                briefing_text = re.sub(r'\s*\|?\s*priority\s*[:\s]*\d+', '', briefing_text, flags=re.IGNORECASE)
            elif re.search(r'\b(urgent|important|high priority)\b', text_lower):
                priority = 5
                briefing_text = re.sub(r'\s*\|?\s*\b(urgent|important|high priority)\b', '', briefing_text, flags=re.IGNORECASE)
            
            briefing_text = briefing_text.strip()
            
            if not briefing_text or len(briefing_text) < 3:
                return IntentResult(
                    intent_type=IntentType.BRIEFING,
                    action=IntentAction.ADD,
                    payload={},
                    confidence=0.5,
                    needs_clarification=True,
                    clarifying_question="What would you like to add to your briefing?"
                )
            
            payload = {"text": briefing_text}
            if priority > 0:
                payload["priority"] = priority
            
            return IntentResult(
                intent_type=IntentType.BRIEFING,
                action=IntentAction.ADD,
                payload=payload,
                confidence=0.9
            )
    
    return None


def _parse_reminder_intent(text: str, text_lower: str, now: datetime) -> Optional[IntentResult]:
    """Parse reminder-related intents."""
    
    # List patterns
    list_patterns = [
        r'\b(list|show)\b.*\breminders?\b',
        r'\breminders?\s+(list|show)\b',
    ]
    
    for pattern in list_patterns:
        if re.search(pattern, text_lower):
            return IntentResult(
                intent_type=IntentType.REMINDER,
                action=IntentAction.LIST,
                payload={},
                confidence=0.9
            )
    
    # Add patterns
    add_pattern = r'\b(remind me|set a reminder|reminder)\b'
    match = re.search(add_pattern, text_lower)
    
    if match:
        # Extract reminder text and time
        remainder = text[match.end():].strip()
        
        # Try to parse time expressions
        time_result = _extract_time_from_text(remainder, now)
        
        if not time_result["text"] or len(time_result["text"]) < 3:
            return IntentResult(
                intent_type=IntentType.REMINDER,
                action=IntentAction.ADD,
                payload={},
                confidence=0.5,
                needs_clarification=True,
                clarifying_question="What would you like to be reminded about, and when?"
            )
        
        payload = {
            "text": time_result["text"],
        }
        
        if time_result.get("timestamp"):
            payload["timestamp"] = time_result["timestamp"]
            payload["due_timestamp"] = time_result["timestamp"]  # For compatibility
        
        if time_result.get("time_str"):
            payload["time_str"] = time_result["time_str"]
        
        # Lower confidence if we couldn't parse a time
        confidence = 0.9 if time_result.get("timestamp") else 0.7
        
        return IntentResult(
            intent_type=IntentType.REMINDER,
            action=IntentAction.ADD,
            payload=payload,
            confidence=confidence
        )
    
    return None


def _parse_memory_intent(text: str, text_lower: str, now: datetime) -> Optional[IntentResult]:
    """Parse memory-related intents."""
    
    # Show/list patterns
    show_patterns = [
        r'\b(show|display|what do you|what\'s in|whats in)\b.*\bmemory\b',
        r'\b(what do you|what\'s|whats)\b.*\bremember\b',
        r'^memory$',
    ]
    
    for pattern in show_patterns:
        if re.search(pattern, text_lower):
            return IntentResult(
                intent_type=IntentType.MEMORY,
                action=IntentAction.SHOW,
                payload={},
                confidence=0.9
            )
    
    # Remember patterns (add to memory)
    remember_pattern = r'^remember\s*:\s*'
    match = re.search(remember_pattern, text_lower)
    
    if match:
        memory_text = text[match.end():].strip()
        
        if not memory_text or len(memory_text) < 3:
            return IntentResult(
                intent_type=IntentType.MEMORY,
                action=IntentAction.ADD,
                payload={},
                confidence=0.5,
                needs_clarification=True,
                clarifying_question="What would you like me to remember?"
            )
        
        return IntentResult(
            intent_type=IntentType.MEMORY,
            action=IntentAction.ADD,
            payload={"text": memory_text},
            confidence=0.9
        )
    
    return None


def _extract_time_from_text(text: str, now: datetime) -> Dict[str, Any]:
    """Extract time information and remaining text from a reminder string.
    
    Returns:
        dict with keys: text (remaining text), timestamp (Unix timestamp or None),
        time_str (original time expression or None)
    """
    text_lower = text.lower()
    
    # Pattern 1: "tomorrow [at] HH:MM" (check before generic "at HH:MM")
    tomorrow_pattern = r'\btomorrow(?:\s+at)?\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b'
    match = re.search(tomorrow_pattern, text_lower)
    if match:
        time_str = match.group(1)
        # Remove the entire match including "tomorrow"
        remaining_text = text[:match.start()] + text[match.end():]
        remaining_text = remaining_text.replace(" to ", " ").strip()
        
        parsed = dateparser.parse(f"tomorrow at {time_str}", settings={
            'PREFER_DATES_FROM': 'future',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'TIMEZONE': 'America/Chicago'
        })
        
        if parsed:
            return {
                "text": remaining_text.strip(),
                "timestamp": int(parsed.timestamp()),
                "time_str": f"tomorrow {time_str}"
            }
    
    # Pattern 2: Day of week with time (check before generic "at HH:MM")
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for day in days:
        day_pattern = rf'\b{day}(?:\s+at)?\s+(\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)?)\b'
        match = re.search(day_pattern, text_lower)
        if match:
            time_str = match.group(1)
            # Remove the entire match including day of week
            remaining_text = text[:match.start()] + text[match.end():]
            remaining_text = remaining_text.replace(" to ", " ").strip()
            
            parsed = dateparser.parse(f"{day} at {time_str}", settings={
                'PREFER_DATES_FROM': 'future',
                'RETURN_AS_TIMEZONE_AWARE': True,
                'TIMEZONE': 'America/Chicago'
            })
            
            if parsed:
                return {
                    "text": remaining_text.strip(),
                    "timestamp": int(parsed.timestamp()),
                    "time_str": f"{day} {time_str}"
                }
    
    # Pattern 3: "at HH:MM" or "at Hpm/am"
    at_time_pattern = r'\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b'
    match = re.search(at_time_pattern, text_lower)
    if match:
        time_str = match.group(1)
        remaining_text = text[:match.start()] + text[match.end():]
        remaining_text = remaining_text.replace(" to ", " ").strip()
        
        # Parse time using dateparser
        parsed = dateparser.parse(f"today at {time_str}", settings={
            'PREFER_DATES_FROM': 'future',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'TIMEZONE': 'America/Chicago'
        })
        
        if parsed:
            # If the time is in the past today, assume tomorrow
            if parsed < now:
                parsed = parsed + timedelta(days=1)
            
            return {
                "text": remaining_text.strip(),
                "timestamp": int(parsed.timestamp()),
                "time_str": time_str
            }
    
    # Pattern 4: "in X minutes/hours"
    in_duration_pattern = r'\bin\s+(\d+)\s*(minute|min|hour|hr)s?\b'
    match = re.search(in_duration_pattern, text_lower)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        remaining_text = text[:match.start()] + text[match.end():]
        remaining_text = remaining_text.replace(" to ", " ").strip()
        
        if unit.startswith('min'):
            delta = timedelta(minutes=value)
        else:  # hour
            delta = timedelta(hours=value)
        
        target_time = now + delta
        
        return {
            "text": remaining_text.strip(),
            "timestamp": int(target_time.timestamp()),
            "time_str": f"in {value} {unit}"
        }
    
    # Pattern 5: "tomorrow" alone
    if 'tomorrow' in text_lower:
        remaining_text = re.sub(r'\btomorrow\b', '', text, flags=re.IGNORECASE).strip()
        remaining_text = remaining_text.replace(" to ", " ").strip()
        
        # Default to 9am tomorrow
        parsed = dateparser.parse("tomorrow at 9am", settings={
            'PREFER_DATES_FROM': 'future',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'TIMEZONE': 'America/Chicago'
        })
        
        if parsed:
            return {
                "text": remaining_text,
                "timestamp": int(parsed.timestamp()),
                "time_str": "tomorrow"
            }
    
    # No time found - return text as-is
    return {"text": text, "timestamp": None, "time_str": None}
