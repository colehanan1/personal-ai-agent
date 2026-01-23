"""Natural language reminder detection for Milton Gateway."""

import re
from typing import Optional, Dict


class ReminderDetector:
    """Detects reminder requests from natural language."""
    
    # Patterns that indicate reminder requests
    REMINDER_PATTERNS = [
        # "every sunday in morning briefing help me X" (handles typo "breifing")
        (r'every\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s+in\s+(?:the\s+)?(?:morning|afternoon|evening)\s+br[ie]+f?i[ne]g\s+([^\.!?]{10,150})', 'weekly_briefing_reminder'),
        # "every sunday help me X"
        (r'every\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s+(?:help me|remind me|give me)\s+([^\.!?]{10,100})', 'weekly_reminder'),
    ]
    
    def detect_reminder_request(self, message: str) -> Optional[Dict[str, str]]:
        """Detect if message contains a reminder request.
        
        Args:
            message: User's message text
            
        Returns:
            Dict with reminder details or None if no reminder detected
            {
                "type": "weekly",
                "day": "sunday",
                "time": "morning",
                "task": "help me come up with a grocery list..."
            }
        """
        message_lower = message.lower()
        
        for pattern, reminder_type in self.REMINDER_PATTERNS:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            
            if match:
                if reminder_type in ('weekly_reminder', 'weekly_briefing_reminder'):
                    day = match.group(1).strip()
                    task = match.group(2).strip()
                    
                    # Extract time if present in original match
                    time_match = re.search(r'\b(morning|afternoon|evening)\b', message_lower)
                    time = time_match.group(1) if time_match else "morning"
                    
                    return {
                        "type": "weekly",
                        "day": day,
                        "time": time,
                        "task": task,
                        "raw_pattern": reminder_type
                    }
        
        return None
