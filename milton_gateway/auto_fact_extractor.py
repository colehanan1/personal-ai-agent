"""Automatic fact extraction from conversation.

Analyzes assistant responses to detect when facts or reminders should be stored,
then automatically calls the appropriate storage APIs WITHOUT requiring slash commands.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def detect_storage_intent(assistant_response: str, user_message: str) -> List[Dict[str, Any]]:
    """Detect if assistant response indicates something should be stored.
    
    Args:
        assistant_response: What Milton said
        user_message: What user said
    
    Returns:
        List of storage actions to perform: [{"type": "memory|reminder", "data": {...}}]
    """
    actions = []
    response_lower = assistant_response.lower()
    
    # Pattern 1: "I'll store/remember/save that"
    if any(phrase in response_lower for phrase in [
        "i'll store", "i'll remember", "i'll save", "i've stored", 
        "i've remembered", "i've added", "i've updated"
    ]):
        # Extract what was supposedly stored
        facts = extract_mentioned_facts(assistant_response, user_message)
        for fact in facts:
            actions.append({
                "type": "memory",
                "data": fact
            })
    
    # Pattern 2: Reminder confirmation
    if any(phrase in response_lower for phrase in [
        "i'll remind you", "i'll set a reminder", "reminder set", "i've set a reminder"
    ]):
        reminder = extract_reminder_from_context(assistant_response, user_message)
        if reminder:
            actions.append({
                "type": "reminder",
                "data": reminder
            })
    
    return actions


def extract_mentioned_facts(assistant_response: str, user_message: str) -> List[Dict[str, str]]:
    """Extract key-value facts from assistant's response.
    
    Looks for patterns like:
    - "Your preferences: X"
    - "I've stored: X"
    - Bullet lists with categories
    
    Args:
        assistant_response: Milton's response
        user_message: User's original message
    
    Returns:
        List of {"key": "...", "value": "..."} dicts
    """
    facts = []
    
    # Pattern: Look for structured lists in response
    # "Health-related goals: High cholesterol"
    lines = assistant_response.split('\n')
    
    for line in lines:
        # Match patterns like "Key: Value" or "Category: Value"
        match = re.match(r'^[•\-\*]?\s*\*?\*?([^:]+):\*?\*?\s*(.+)$', line.strip())
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            
            # Clean up formatting
            key = key.replace('*', '').strip()
            value = value.replace('*', '').strip()
            
            # Skip if too generic or empty
            if len(key) > 3 and len(value) > 3 and key.lower() not in ['let', 'here', 'what', 'would']:
                facts.append({
                    "key": _normalize_key(key),
                    "value": value
                })
    
    # Also extract from user message directly if assistant mentions "stored"
    if not facts and ("stored" in assistant_response.lower() or "remember" in assistant_response.lower()):
        # Try to extract from user message
        facts.extend(_extract_facts_from_user_message(user_message))
    
    return facts


def _extract_facts_from_user_message(user_message: str) -> List[Dict[str, str]]:
    """Extract potential facts from user's message.
    
    Args:
        user_message: What the user said
    
    Returns:
        List of extracted facts
    """
    facts = []
    message_lower = user_message.lower()
    
    # Health conditions
    if re.search(r'\b(i have|i\'m|i am)\s+(high|low|severe|chronic)\s+\w+', message_lower):
        # Extract health condition
        match = re.search(r'\b(?:i have|i\'m|i am)\s+((?:high|low|severe|chronic)\s+\w+)', message_lower)
        if match:
            condition = match.group(1)
            facts.append({
                "key": "health_conditions",
                "value": condition.title()
            })
    
    # Preferences: "I like X"
    if re.search(r'\bi\s+(?:like|love|prefer|enjoy)\s+', message_lower):
        match = re.search(r'\bi\s+(?:like|love|prefer|enjoy)\s+(.+?)(?:[.!?]|$)', message_lower)
        if match:
            preference = match.group(1).strip()
            facts.append({
                "key": "preferences",
                "value": preference
            })
    
    # Habits: "I always/every X"
    if re.search(r'\b(?:i always|i usually|every|each)\s+\w+\s+i\s+', message_lower):
        match = re.search(r'((?:i always|i usually|every|each).+?)(?:[.!?]|$)', message_lower)
        if match:
            habit = match.group(1).strip()
            facts.append({
                "key": "habits",
                "value": habit
            })
    
    return facts


def extract_reminder_from_context(assistant_response: str, user_message: str) -> Optional[Dict[str, Any]]:
    """Extract reminder details from conversation context.
    
    Args:
        assistant_response: Milton's response
        user_message: User's message
    
    Returns:
        Reminder dict or None
    """
    # Look for time expressions in user message
    time_patterns = [
        r'\b(this|next|every)\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b',
        r'\b(tomorrow|today|tonight)\b',
        r'\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b',
        r'\bin\s+(\d+)\s+(minute|hour|day|week)s?\b',
    ]
    
    time_expr = None
    for pattern in time_patterns:
        match = re.search(pattern, user_message.lower())
        if match:
            time_expr = match.group(0)
            break
    
    # Look for what to remind about
    reminder_patterns = [
        r'remind\s+me\s+(?:to\s+)?(.+?)(?:\s+(?:this|next|tomorrow|today|at|in|on)|$)',
        r'(?:remember|don\'t forget)\s+(?:to\s+)?(.+?)(?:\s+(?:this|next|tomorrow|today|at|in|on)|$)',
    ]
    
    text = None
    for pattern in reminder_patterns:
        match = re.search(pattern, user_message.lower())
        if match:
            text = match.group(1).strip()
            break
    
    if text and time_expr:
        return {
            "text": text,
            "time_expression": time_expr,
            "original_message": user_message
        }
    
    return None


def _normalize_key(key: str) -> str:
    """Normalize a fact key to snake_case.
    
    Args:
        key: Raw key string
    
    Returns:
        Normalized snake_case key
    """
    # Convert to lowercase
    key = key.lower()
    # Replace spaces and special chars with underscore
    key = re.sub(r'[^a-z0-9]+', '_', key)
    # Remove leading/trailing underscores
    key = key.strip('_')
    return key
