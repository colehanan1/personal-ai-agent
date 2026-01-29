"""Unified reminder intent normalization for Milton Gateway.

Maps multiple natural language surface forms to a single internal reminder.create intent.
Supports draft → confirm flow for ambiguous timing.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Canonical timezone
DEFAULT_TIMEZONE = "America/Chicago"


@dataclass
class ReminderIntent:
    """Unified reminder creation intent.
    
    All reminder requests (via "remind me", "in briefing help me", etc.) 
    normalize to this structure for consistent downstream processing.
    """
    intent_type: str = "reminder.create"  # Canonical intent type
    task: str = ""  # What to remind about
    due_at: Optional[int] = None  # Unix timestamp (None if ambiguous)
    recurrence: Optional[str] = None  # e.g., "weekday_mornings", "every_friday"
    channel: str = "ntfy"  # Default channel ("ntfy", "morning_briefing", etc.)
    priority: str = "med"  # "low", "med", "high"
    timezone: str = DEFAULT_TIMEZONE
    
    # Ambiguity handling
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0
    
    # Metadata for auditing
    surface_form: str = ""  # Original pattern matched
    time_expression: Optional[str] = None  # Extracted time phrase
    parsed_partial: Dict[str, Any] = field(default_factory=dict)  # Partial parse metadata


class ReminderIntentNormalizer:
    """Normalize various reminder phrasings to unified ReminderIntent."""
    
    # Pattern definitions with priorities (higher = checked first)
    PATTERNS = [
        # === EXPLICIT TIME PATTERNS (high confidence) ===
        
        # "set/create/add/schedule a reminder for me to X at 9am tomorrow"
        {
            "pattern": r'\b(set|create|add|schedule)\s+a\s+reminder\s+(?:for me\s+)?to\s+(.+?)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(tomorrow|today|tonight)',
            "type": "explicit_time",
            "surface_form": "set_reminder_explicit",
            "confidence": 0.95,
            "priority": 13,
        },
        
        # "set/create/add/schedule a reminder for me to X tomorrow at 9am"
        {
            "pattern": r'\b(set|create|add|schedule)\s+a\s+reminder\s+(?:for me\s+)?to\s+(.+?)\s+(tomorrow|today|tonight)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b',
            "type": "explicit_time",
            "surface_form": "set_reminder_explicit",
            "confidence": 0.95,
            "priority": 12,
        },
        
        # "remind me to X at 9am tomorrow" - More specific before general
        {
            "pattern": r'\b(remind me|reminder)\s+to\s+(.+?)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(tomorrow|today|tonight)',
            "type": "explicit_time",
            "surface_form": "remind_me_explicit",
            "confidence": 0.95,
            "priority": 11,
        },
        
        # "remind me to X tomorrow at 9am"
        {
            "pattern": r'\b(remind me|reminder)\s+to\s+(.+?)\s+(tomorrow|today|tonight)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b',
            "type": "explicit_time",
            "surface_form": "remind_me_explicit",
            "confidence": 0.95,
            "priority": 10,
        },
        
        # "at 9am tomorrow remind me to X"
        {
            "pattern": r'\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(tomorrow|today)\s+(remind me|reminder)\s+(?:to\s+)?(.+)',
            "type": "explicit_time_prefix",
            "surface_form": "explicit_time_remind_me",
            "confidence": 0.95,
            "priority": 9,
        },
        
        # === BRIEFING PATTERNS ===
        
        # "every weekday in my morning briefing help me X"
        {
            "pattern": r'\bevery\s+(weekday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+in\s+(?:my\s+)?(?:the\s+)?(morning|afternoon|evening)\s+br[ie]+f?i[ne]g\s+(help me|remind me|give me)\s+(.+)',
            "type": "recurring_briefing",
            "surface_form": "recurring_briefing_help",
            "confidence": 0.9,
            "priority": 8,
            "channel": "morning_briefing",
            "needs_clarification": True,  # No explicit time, needs schedule
            "clarifying_question": "What time {timeofday} on {day}? (e.g., '9:00 AM')",
        },
        
        # "in my morning briefing help me X" or "in my briefing help me X" (with or without time-of-day)
        {
            "pattern": r'\bin\s+(?:my\s+)?(?:the\s+)?(?:(morning|afternoon|evening)\s+)?br[ie]+f?i[ne]g\s+(help me|remind me|give me)\s+(.+)',
            "type": "briefing_oneshot",
            "surface_form": "briefing_help",
            "confidence": 0.85,
            "priority": 7,
            "channel": "morning_briefing",
            "needs_clarification": True,  # No explicit time
            "clarifying_question": "What day and time for this briefing reminder? (e.g., 'tomorrow 8am', 'every weekday 9am')",
        },
        
        # "add to my briefing: X"
        {
            "pattern": r'\b(add to|put in)\s+(?:my\s+)?(?:the\s+)?(morning|afternoon|evening)?\s*br[ie]+f?i[ne]g\s*:?\s*(.+)',
            "type": "briefing_add",
            "surface_form": "add_to_briefing",
            "confidence": 0.9,
            "priority": 6,
            "channel": "morning_briefing",
            "needs_clarification": True,
            "clarifying_question": "When should this appear in your briefing? (e.g., 'tomorrow morning', 'every weekday')",
        },
        
        # === RELATIVE TIME PATTERNS ===
        
        # "set/create/add/schedule a reminder for me to X in 2 hours"
        {
            "pattern": r'\b(set|create|add|schedule)\s+a\s+reminder\s+(?:for me\s+)?to\s+(.+?)\s+in\s+(\d+)\s*(hour|hr|h|minute|min|m|day|d)s?\b',
            "type": "relative_time",
            "surface_form": "set_reminder_relative",
            "confidence": 0.9,
            "priority": 6,
        },
        
        # "remind me to X in 2 hours"
        {
            "pattern": r'\b(remind me|reminder)\s+to\s+(.+?)\s+in\s+(\d+)\s*(hour|hr|h|minute|min|m|day|d)s?\b',
            "type": "relative_time",
            "surface_form": "remind_me_relative",
            "confidence": 0.9,
            "priority": 5,
        },
        
        # "set/create/add/schedule a reminder for me to X tomorrow morning"
        {
            "pattern": r'\b(set|create|add|schedule)\s+a\s+reminder\s+(?:for me\s+)?to\s+(.+?)\s+(tomorrow|today|tonight)\s+(morning|afternoon|evening)\b',
            "type": "relative_timeofday",
            "surface_form": "set_reminder_relative_timeofday",
            "confidence": 0.7,
            "priority": 4,
            "needs_clarification": True,
            "clarifying_question": "What time {timeofday}? (e.g., '9:00 AM')",
        },
        
        # "remind me to X tomorrow morning"
        {
            "pattern": r'\b(remind me|reminder)\s+to\s+(.+?)\s+(tomorrow|today|tonight)\s+(morning|afternoon|evening)\b',
            "type": "relative_timeofday",
            "surface_form": "remind_me_relative_timeofday",
            "confidence": 0.7,
            "priority": 4,
            "needs_clarification": True,
            "clarifying_question": "What time {timeofday}? (e.g., '9:00 AM')",
        },
        
        # "every X help me Y" - BEFORE simple remind_me pattern
        {
            "pattern": r'\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday)\s+(help me|remind me|give me)\s+(.+)',
            "type": "recurring_simple",
            "surface_form": "every_day_help",
            "confidence": 0.75,
            "priority": 4,  # Higher priority than simple remind_me
            "needs_clarification": True,
            "clarifying_question": "What time on {day}? (e.g., '9:00 AM')",
        },
        
        # === SIMPLE PATTERNS (lower confidence) ===
        
        # "set/create/add/schedule a reminder for me to X" (no time specified)
        {
            "pattern": r'\b(set|create|add|schedule)\s+a\s+reminder\s+(?:for me\s+)?to\s+(.+)',
            "type": "simple_remind",
            "surface_form": "set_reminder_simple",
            "confidence": 0.6,
            "priority": 3,
            "needs_clarification": True,
            "clarifying_question": "When would you like to be reminded? (e.g., 'tomorrow at 9am', 'in 2 hours')",
        },
        
        # "remind me to X"
        {
            "pattern": r'\b(remind me|reminder)\s+to\s+(.+)',
            "type": "simple_remind",
            "surface_form": "remind_me_simple",
            "confidence": 0.6,
            "priority": 3,
            "needs_clarification": True,
            "clarifying_question": "When would you like to be reminded? (e.g., 'tomorrow at 9am', 'in 2 hours')",
        },
    ]
    
    def __init__(self):
        # Sort patterns by priority (highest first)
        self.patterns = sorted(self.PATTERNS, key=lambda p: p.get("priority", 0), reverse=True)
    
    def normalize(self, text: str, now: Optional[datetime] = None) -> Optional[ReminderIntent]:
        """Normalize text to ReminderIntent.
        
        Args:
            text: User's natural language input
            now: Current time for relative date parsing
            
        Returns:
            ReminderIntent if reminder detected, None otherwise
        """
        if now is None:
            now = datetime.now()
        
        text = text.strip()
        
        # Skip slash commands - handled by command processor
        if text.startswith("/"):
            return None
        
        text_lower = text.lower()
        
        # Try each pattern in priority order
        for pattern_def in self.patterns:
            match = re.search(pattern_def["pattern"], text_lower, re.IGNORECASE)
            
            if match:
                logger.debug(f"Matched pattern: {pattern_def['surface_form']}")
                return self._build_intent(match, pattern_def, text, now)
        
        return None
    
    def _build_intent(
        self, 
        match: re.Match, 
        pattern_def: Dict[str, Any],
        original_text: str,
        now: datetime
    ) -> ReminderIntent:
        """Build ReminderIntent from regex match and pattern definition."""
        
        intent = ReminderIntent(
            surface_form=pattern_def["surface_form"],
            confidence=pattern_def.get("confidence", 0.5),
            channel=pattern_def.get("channel", "ntfy"),
            needs_clarification=pattern_def.get("needs_clarification", False),
            clarifying_question=pattern_def.get("clarifying_question"),
            timezone=DEFAULT_TIMEZONE,
        )
        
        pattern_type = pattern_def["type"]
        
        # === EXPLICIT TIME PATTERNS ===
        if pattern_type == "explicit_time":
            # Groups: (remind_phrase, task, day, time)
            intent.task = match.group(2).strip()
            day_str = match.group(3)
            time_str = match.group(4)
            intent.time_expression = f"{day_str} at {time_str}"
            intent.due_at = self._parse_explicit_time(day_str, time_str, now)
            intent.needs_clarification = (intent.due_at is None)
            
        elif pattern_type == "explicit_time_prefix":
            # Groups: (time, day, remind_phrase, task)
            time_str = match.group(1)
            day_str = match.group(2)
            intent.task = match.group(4).strip()
            intent.time_expression = f"{day_str} at {time_str}"
            intent.due_at = self._parse_explicit_time(day_str, time_str, now)
            intent.needs_clarification = (intent.due_at is None)
        
        # === BRIEFING PATTERNS ===
        elif pattern_type == "recurring_briefing":
            # Groups: (day, timeofday, action_verb, task)
            day = match.group(1)
            timeofday = match.group(2)
            intent.task = match.group(4).strip()
            intent.recurrence = f"{day}_{timeofday}"
            intent.time_expression = f"every {day} {timeofday}"
            intent.parsed_partial = {"day": day, "timeofday": timeofday}
            # Explicitly set clarification need and question
            intent.needs_clarification = True
            if "{timeofday}" in pattern_def.get("clarifying_question", ""):
                intent.clarifying_question = pattern_def["clarifying_question"].format(
                    timeofday=timeofday, day=day
                )
            
        elif pattern_type == "briefing_oneshot":
            # Groups: (timeofday?, action_verb, task)
            timeofday = match.group(1) if match.lastindex >= 1 and match.group(1) else "morning"
            intent.task = match.group(3).strip()
            intent.time_expression = f"{timeofday} briefing"
            intent.parsed_partial = {"timeofday": timeofday}
            
        elif pattern_type == "briefing_add":
            # Groups: (action_verb, timeofday?, task)
            timeofday = match.group(2) if match.lastindex >= 2 else "morning"
            intent.task = match.group(3).strip()
            intent.time_expression = f"{timeofday} briefing"
            intent.parsed_partial = {"timeofday": timeofday}
        
        # === RELATIVE TIME PATTERNS ===
        elif pattern_type == "relative_time":
            # Groups: (remind_phrase, task, quantity, unit)
            intent.task = match.group(2).strip()
            quantity = int(match.group(3))
            unit = match.group(4).lower()
            intent.time_expression = f"in {quantity} {unit}"
            intent.due_at = self._parse_relative_time(quantity, unit, now)
            intent.needs_clarification = (intent.due_at is None)
            
        elif pattern_type == "relative_timeofday":
            # Groups: (remind_phrase, task, day, timeofday)
            intent.task = match.group(2).strip()
            day = match.group(3)
            timeofday = match.group(4)
            intent.time_expression = f"{day} {timeofday}"
            intent.parsed_partial = {"day": day, "timeofday": timeofday}
            if intent.clarifying_question:
                intent.clarifying_question = intent.clarifying_question.format(timeofday=timeofday)
        
        # === SIMPLE PATTERNS ===
        elif pattern_type == "simple_remind":
            # Groups: (remind_phrase, task)
            intent.task = match.group(2).strip()
            
        elif pattern_type == "recurring_simple":
            # Groups: (day, action_verb, task)
            day = match.group(1)
            intent.task = match.group(3).strip()
            intent.recurrence = f"every_{day}"
            intent.time_expression = f"every {day}"
            intent.parsed_partial = {"day": day}
            if intent.clarifying_question:
                intent.clarifying_question = intent.clarifying_question.format(day=day)
        
        return intent
    
    def _parse_explicit_time(self, day_str: str, time_str: str, now: datetime) -> Optional[int]:
        """Parse explicit time like 'tomorrow at 9am' into Unix timestamp.
        
        Returns None if parsing fails.
        """
        try:
            import dateparser
            combined = f"{day_str} at {time_str}"
            parsed = dateparser.parse(
                combined,
                settings={
                    'TIMEZONE': DEFAULT_TIMEZONE,
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future',
                }
            )
            if parsed:
                return int(parsed.timestamp())
        except Exception as e:
            logger.warning(f"Failed to parse time '{day_str} at {time_str}': {e}")
        
        return None
    
    def _parse_relative_time(self, quantity: int, unit: str, now: datetime) -> Optional[int]:
        """Parse relative time like '2 hours' into Unix timestamp from now."""
        unit = unit.lower()
        unit_map = {
            "hour": 3600, "hr": 3600, "h": 3600,
            "minute": 60, "min": 60, "m": 60,
            "day": 86400, "d": 86400,
        }
        
        seconds_per_unit = unit_map.get(unit)
        if seconds_per_unit:
            return int(now.timestamp()) + (quantity * seconds_per_unit)
        
        return None
