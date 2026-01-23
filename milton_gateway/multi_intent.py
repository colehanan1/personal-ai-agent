"""Multi-intent message splitting.

Detects and splits messages containing multiple actionable intents.
Example: "Add a goal to finish chapter 3 and remind me tomorrow at 9am"
         -> ["Add a goal to finish chapter 3", "remind me tomorrow at 9am"]
"""

from __future__ import annotations

import re
from typing import List, Optional


MAX_INTENTS_PER_MESSAGE = 3  # Safety limit


def split_message(text: str) -> List[str]:
    """Split a message into multiple intent segments if applicable.
    
    Args:
        text: User message text
    
    Returns:
        List of intent segments (single item if no splitting needed)
    """
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Check for multi-intent patterns
    segments = _split_by_conjunctions(text)
    
    # Safety limit
    if len(segments) > MAX_INTENTS_PER_MESSAGE:
        segments = segments[:MAX_INTENTS_PER_MESSAGE]
    
    return segments


def _split_by_conjunctions(text: str) -> List[str]:
    """Split text by conjunctions that indicate separate intents.
    
    Args:
        text: Text to split
    
    Returns:
        List of segments
    """
    # Patterns that indicate separate intents
    # Use word boundaries and context to avoid false positives
    patterns = [
        r'\s+and\s+(?:also\s+)?(?:add|set|create|remind|remember|show|list|make)',
        r'\s+also\s+(?:add|set|create|remind|remember|show|list|make)',
        r'\s+then\s+(?:add|set|create|remind|remember|show|list|make)',
        r',\s+and\s+(?:also\s+)?(?:add|set|create|remind|remember|show|list|make)',
    ]
    
    # Try each pattern
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            # Split at the conjunction
            segments = []
            last_end = 0
            
            for match in matches:
                # Include text before the conjunction
                segment = text[last_end:match.start()].strip()
                if segment:
                    segments.append(segment)
                
                # Start next segment after the conjunction (but include the action verb)
                last_end = match.start()
                # Remove leading "and", "also", "then", commas
                next_segment_start = text[last_end:match.end()]
                next_segment_start = re.sub(r'^[,\s]*(and|also|then)\s+', '', next_segment_start, flags=re.IGNORECASE)
                last_end = match.end() - len(next_segment_start)
            
            # Add final segment
            segment = text[last_end:].strip()
            if segment:
                segments.append(segment)
            
            if len(segments) > 1:
                return segments
    
    # No split needed
    return [text]


def is_multi_intent(text: str) -> bool:
    """Check if a message contains multiple intents.
    
    Args:
        text: Message text
    
    Returns:
        True if multiple intents detected
    """
    segments = split_message(text)
    return len(segments) > 1


def format_multi_intent_confirmation(segments: List[str], candidates: List[dict]) -> str:
    """Format a confirmation prompt for multiple intents.
    
    Args:
        segments: List of text segments
        candidates: List of intent candidate dicts
    
    Returns:
        Formatted confirmation prompt
    """
    if len(segments) != len(candidates):
        raise ValueError("Segments and candidates must have same length")
    
    lines = ["I detected **multiple actions** in your message:\n"]
    
    labels = ['A', 'B', 'C', 'D', 'E']
    for i, (segment, candidate) in enumerate(zip(segments, candidates)):
        label = labels[i] if i < len(labels) else str(i+1)
        intent_type = candidate.get('intent_type', 'action')
        action = candidate.get('action', 'unknown')
        
        # Format candidate summary
        summary = _format_candidate_summary(candidate)
        
        lines.append(f"**{label})** {intent_type.capitalize()} {action}: {summary}")
    
    lines.append("\n**Reply with:**")
    lines.append(f"- `Yes A` or `Yes B` etc. to confirm individual actions")
    lines.append(f"- `Yes All` to confirm all {len(segments)} actions")
    lines.append(f"- `Edit A: <correction>` to modify an action")
    lines.append(f"- `No` to cancel all")
    
    return "\n".join(lines)


def _format_candidate_summary(candidate: dict) -> str:
    """Format a brief summary of a candidate intent.
    
    Args:
        candidate: Candidate dictionary
    
    Returns:
        Summary string
    """
    intent_type = candidate.get('intent_type', 'unknown')
    payload = candidate.get('payload', {})
    
    if intent_type == 'goal':
        text = payload.get('text', payload.get('description', '(no text)'))
        cadence = payload.get('cadence', 'daily')
        return f'"{text}" ({cadence})'
    
    elif intent_type == 'reminder':
        text = payload.get('text', payload.get('title', '(no text)'))
        due_at = payload.get('due_at', '')
        if due_at:
            # Extract date/time portion
            if 'T' in due_at:
                date_part, time_part = due_at.split('T')
                return f'"{text}" at {time_part[:5]} on {date_part}'
            return f'"{text}" due {due_at}'
        return f'"{text}"'
    
    elif intent_type == 'briefing':
        text = payload.get('text', payload.get('content', '(no text)'))
        return f'"{text}"'
    
    elif intent_type == 'memory':
        key = payload.get('key', '')
        value = payload.get('value', '')
        return f'{key} = {value}'
    
    return str(payload)
