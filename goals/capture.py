"""
Unified goal capture module for deterministic goal extraction.

Provides a single source of truth for goal intent patterns and capture logic.
Used by API server, phone/ntfy ingestion, and chat gateway.
"""

from __future__ import annotations

import re
from typing import Optional
from pathlib import Path

from goals.api import add_goal, list_goals
from milton_orchestrator.state_paths import resolve_state_dir


# Deterministic goal intent patterns
# These patterns detect explicit user intents like "goal: text" or "/goal add text"
GOAL_INTENT_PATTERNS = [
    re.compile(r"^goal:\s*(?P<goal>.+)", re.I),
    re.compile(r"^/goal\s+add\s+(?P<goal>.+)", re.I),
    re.compile(r"^/goal\s+(?P<goal>.+)", re.I),
    re.compile(r"^(?:my\s+)?goal\s+(?:is|for\s+today|today)\s*:\s*(?P<goal>.+)", re.I),
    re.compile(r"^(?:today's\s+)?goal\s*:\s*(?P<goal>.+)", re.I),
    re.compile(r"^(?:add|set|create)\s+goal\s*:\s*(?P<goal>.+)", re.I),
    re.compile(r"^-\s*goal\s*:\s*(?P<goal>.+)", re.I),
    re.compile(r"^\*\s*goal\s*:\s*(?P<goal>.+)", re.I),
    re.compile(r"^\d+[\.)]\s*goal\s*:\s*(?P<goal>.+)", re.I),
]


def normalize_goal_text(text: str) -> str:
    """
    Normalize goal text for consistency.
    
    - Strips whitespace
    - Removes markdown bullets/numbers
    - Removes extra spaces
    - Removes quotes
    """
    if not text:
        return ""
    
    cleaned = str(text).strip()
    
    # Remove markdown bullets/numbers from start
    cleaned = re.sub(r"^[-*•]\s*", "", cleaned)
    cleaned = re.sub(r"^\d+[\.)]\s*", "", cleaned)
    
    # Remove quotes
    cleaned = re.sub(r'^["\']|["\']$', "", cleaned)
    
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    return cleaned


def extract_goal_from_line(line: str) -> Optional[str]:
    """
    Extract goal text from a single line using deterministic patterns.
    
    Returns:
        Goal text if found, None otherwise
    """
    stripped = line.strip()
    if not stripped:
        return None
    
    for pattern in GOAL_INTENT_PATTERNS:
        match = pattern.match(stripped)
        if match:
            goal_text = normalize_goal_text(match.group("goal"))
            if goal_text and len(goal_text) >= 3:
                return goal_text
    
    return None


def extract_goals_from_text(text: str) -> list[str]:
    """
    Extract all goals from multi-line text.
    
    Handles:
    - Multiple goal: lines
    - Bulleted goal lists
    - Mixed content with embedded goals
    
    Returns:
        List of normalized goal texts
    """
    goals: list[str] = []
    
    for line in text.splitlines():
        goal_text = extract_goal_from_line(line)
        if goal_text:
            goals.append(goal_text)
    
    return goals


def goal_exists(goal_text: str, base_dir: Optional[Path] = None) -> Optional[str]:
    """
    Check if a goal already exists across all scopes.
    
    Args:
        goal_text: Goal text to check
        base_dir: Optional state directory override
    
    Returns:
        Goal ID if exists, None otherwise
    """
    base = resolve_state_dir(base_dir)
    normalized = normalize_goal_text(goal_text).lower()
    
    for scope in ("daily", "weekly", "monthly"):
        for goal in list_goals(scope, base_dir=base):
            existing = normalize_goal_text(str(goal.get("text", ""))).lower()
            if existing == normalized and goal.get("id"):
                return str(goal["id"])
    
    return None


def capture_goal(
    goal_text: str,
    scope: str = "daily",
    tags: Optional[list[str]] = None,
    base_dir: Optional[Path] = None,
) -> dict[str, str]:
    """
    Capture a single goal, avoiding duplicates.
    
    Args:
        goal_text: Goal text to capture
        scope: Goal scope (daily/weekly/monthly)
        tags: Optional tags to add
        base_dir: Optional state directory override
    
    Returns:
        Dict with keys:
            - id: Goal ID
            - text: Normalized goal text
            - status: "added" or "existing"
    """
    normalized_text = normalize_goal_text(goal_text)
    if not normalized_text or len(normalized_text) < 3:
        raise ValueError("Goal text must be at least 3 characters")
    
    base = resolve_state_dir(base_dir)
    
    # Check for duplicates
    existing_id = goal_exists(normalized_text, base_dir=base)
    if existing_id:
        return {
            "id": existing_id,
            "text": normalized_text,
            "status": "existing",
        }
    
    # Add new goal
    goal_id = add_goal(
        scope,
        normalized_text,
        tags=tags or ["captured"],
        base_dir=base,
    )
    
    return {
        "id": goal_id,
        "text": normalized_text,
        "status": "added",
    }


def capture_goals_from_message(
    message: str,
    scope: str = "daily",
    tags: Optional[list[str]] = None,
    base_dir: Optional[Path] = None,
) -> list[dict[str, str]]:
    """
    Extract and capture all goals from a message.
    
    Args:
        message: User message text
        scope: Default scope for captured goals
        tags: Default tags to add
        base_dir: Optional state directory override
    
    Returns:
        List of dicts with keys:
            - id: Goal ID
            - text: Goal text
            - status: "added" or "existing"
    """
    goal_texts = extract_goals_from_text(message)
    captured = []
    
    for goal_text in goal_texts:
        try:
            result = capture_goal(goal_text, scope=scope, tags=tags, base_dir=base_dir)
            captured.append(result)
        except Exception:
            # Skip invalid goals silently
            continue
    
    return captured
