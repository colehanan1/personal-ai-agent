"""Time validation for scheduling (prevent past-time errors)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple
import pytz


class TimeValidationResult:
    """Result of time validation."""
    
    def __init__(
        self,
        is_valid: bool,
        message: str,
        suggested_time: Optional[datetime] = None
    ):
        self.is_valid = is_valid
        self.message = message
        self.suggested_time = suggested_time


def validate_schedule(
    due_at: datetime,
    now: datetime,
    timezone_str: str = "America/Chicago"
) -> TimeValidationResult:
    """Validate a scheduled time and provide suggestions if invalid.
    
    Args:
        due_at: Proposed due/scheduled time
        now: Current time
        timezone_str: Timezone name for local time calculations
    
    Returns:
        TimeValidationResult with validation status and suggestions
    """
    # Ensure both times are timezone-aware
    tz = pytz.timezone(timezone_str)
    
    if due_at.tzinfo is None:
        due_at = tz.localize(due_at)
    if now.tzinfo is None:
        now = tz.localize(now)
    
    # Check if time is in the past
    if due_at < now:
        # Calculate suggested alternative
        suggested = _suggest_next_occurrence(due_at, now, tz)
        
        suggested_str = suggested.strftime("%A, %B %d at %I:%M %p")
        
        return TimeValidationResult(
            is_valid=False,
            message=f"That time is in the past. Did you mean **{suggested_str}**?",
            suggested_time=suggested
        )
    
    # Check if time is too far in future (more than 1 year)
    one_year_ahead = now + timedelta(days=365)
    if due_at > one_year_ahead:
        year = due_at.year
        return TimeValidationResult(
            is_valid=False,
            message=f"That's far in the future ({year}). Did you mean a different year?",
            suggested_time=None
        )
    
    # Time is valid
    return TimeValidationResult(
        is_valid=True,
        message="Time is valid",
        suggested_time=None
    )


def _suggest_next_occurrence(past_time: datetime, now: datetime, tz) -> datetime:
    """Suggest the next occurrence of a past time.
    
    Args:
        past_time: Time that is in the past
        now: Current time
        tz: Timezone
    
    Returns:
        Suggested future time
    """
    # Extract time components
    hour = past_time.hour
    minute = past_time.minute
    
    # Try tomorrow at the same time
    tomorrow = now + timedelta(days=1)
    suggested = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If tomorrow is still in the past (edge case), use day after
    if suggested < now:
        suggested = suggested + timedelta(days=1)
    
    return suggested
