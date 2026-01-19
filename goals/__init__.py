"""Goal tracking and capture for Milton."""

from .api import add_goal, complete_goal, defer_goal, list_goals
from .capture import (
    capture_goal,
    capture_goals_from_message,
    extract_goal_from_line,
    extract_goals_from_text,
    normalize_goal_text,
    goal_exists,
)

__all__ = [
    # API functions
    "add_goal",
    "complete_goal",
    "defer_goal",
    "list_goals",
    # Capture functions
    "capture_goal",
    "capture_goals_from_message",
    "extract_goal_from_line",
    "extract_goals_from_text",
    "normalize_goal_text",
    "goal_exists",
]
