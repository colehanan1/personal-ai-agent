"""Smart fact extraction from natural conversation.

Automatically detects and stores facts from user messages WITHOUT requiring
explicit /remember commands or "I want to remember" statements.

Patterns detected:
- "I love X" → preferences: X
- "I'm from X" / "My X is from Y" → heritage/location facts
- "I have X" (medical) → health_conditions: X
- "I always/usually do X" → habits: X
- "My favorite X is Y" → favorites: Y
"""

from __future__ import annotations

import logging
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class SmartFactExtractor:
    """Extract facts from natural conversation."""
    
    # Patterns that indicate storable facts
    FACT_PATTERNS = [
        # Preferences: "I love/like/prefer X"
        (r'\bi\s+(?:love|like|prefer|enjoy)\s+([^,\.!?]+)', 'preferences', 'love_pattern'),
        
        # Heritage/Location: "I'm from X", "My grandfather is from X"
        (r'\b(?:i\'m|i am)\s+from\s+([^,\.!?]+)', 'location', 'from_pattern'),
        (r'\bmy\s+(\w+)\s+is\s+from\s+([^,\.!?]+)', 'family_heritage', 'family_from_pattern'),
        
        # Health: "I have high/chronic X"
        (r'\bi\s+have\s+(?:high|low|chronic|severe)\s+(\w+(?:\s+\w+)?)', 'health_conditions', 'health_pattern'),
        
        # Favorites: "My favorite X is Y"
        (r'\bmy\s+favorite\s+(\w+)\s+is\s+([^,\.!?]+)', 'favorites', 'favorite_pattern'),
        
        # Habits: "I always/usually X", "Every X I do Y"
        (r'\bi\s+(?:always|usually|typically)\s+([^,\.!?]+)', 'habits', 'habit_pattern'),
        (r'\bevery\s+(\w+)\s+i\s+([^,\.!?]+)', 'routines', 'routine_pattern'),
        
        # Meal prep routines: capture detailed cooking/prep descriptions
        (r'(?:the\s+)?(?:protein|protien)\s+is\s+(?:always\s+)?([a-z\s]+?)(?:\s+and\s+|\s*,|\.|$)', 'meal_prep', 'protein_pattern'),
        (r'(?:the\s+)?grain\s+is\s+([a-z\s,or]+?)(?:\s+and\s+|\s+i\s+|\.|$)', 'meal_prep', 'grain_pattern'),
        (r'\bi\s+want\s+to\s+add\s+([a-z\s]+?)(?:\s+to\s+them)', 'meal_prep', 'meal_goal_add_pattern'),
        (r'\bwant\s+to\s+make\s+sure\s+(?:that\s+)?(?:my\s+)?([a-z\s]+?)\s+is\s+([a-z\s,and]+?)(?:\s+but|\s+and\s+|$)', 'meal_prep', 'meal_goal_ensure_pattern'),
        (r'\bevery\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s+(?:i\s+)?([a-z\s]{10,50}?)(?:\s+for\s+the\s+week|\s+\d+\s+meals|\s+the\s+protein)', 'routines', 'weekly_routine_pattern'),
        
        # Dietary: "I'm trying to avoid/eat X"
        (r'\bi\'m\s+trying\s+to\s+(?:avoid|eat|do|not\s+eat)\s+([^,\.!?]+)', 'dietary_goals', 'dietary_pattern'),
        
        # Personal info: "My name is X"
        (r'\bmy\s+name\s+is\s+(\w+)', 'personal_info', 'name_pattern'),
    ]
    
    def extract_facts(self, message: str) -> List[Dict[str, str]]:
        """Extract all detectable facts from a message.
        
        Args:
            message: User's message text
        
        Returns:
            List of {"key": "...", "value": "...", "category": "..."} dicts
        """
        facts = []
        message_lower = message.lower()
        
        for pattern, category, pattern_name in self.FACT_PATTERNS:
            matches = re.finditer(pattern, message_lower, re.IGNORECASE)
            
            for match in matches:
                fact = self._process_match(match, category, pattern_name, message)
                if fact:
                    facts.append(fact)
        
        # Deduplicate facts (same key)
        seen_keys = set()
        unique_facts = []
        for fact in facts:
            if fact["key"] not in seen_keys:
                seen_keys.add(fact["key"])
                unique_facts.append(fact)
        
        return unique_facts
    
    def _process_match(
        self, 
        match: re.Match, 
        category: str, 
        pattern_name: str,
        original_message: str
    ) -> Optional[Dict[str, str]]:
        """Process a regex match into a fact.
        
        Args:
            match: Regex match object
            category: Fact category
            pattern_name: Name of pattern that matched
            original_message: Original message (for context)
        
        Returns:
            Fact dict or None
        """
        try:
            if pattern_name == 'love_pattern':
                value = match.group(1).strip()
                # Filter out too generic or context-specific phrases
                if len(value) > 3 and not self._is_too_generic(value):
                    return {
                        "key": f"{category}_{self._slugify(value[:20])}",
                        "value": value,
                        "category": category
                    }
            
            elif pattern_name == 'from_pattern':
                location = match.group(1).strip()
                return {
                    "key": "home_location",
                    "value": location,
                    "category": category
                }
            
            elif pattern_name == 'family_from_pattern':
                relation = match.group(1).strip()  # grandfather, mother, etc
                location = match.group(2).strip().title()  # Capitalize properly
                return {
                    "key": f"family_{relation}_heritage",
                    "value": location,
                    "category": category
                }
            
            elif pattern_name == 'health_pattern':
                condition = match.group(1).strip()
                return {
                    "key": "health_conditions",
                    "value": f"Has {condition}",
                    "category": category
                }
            
            elif pattern_name == 'favorite_pattern':
                thing = match.group(1).strip()  # food, color, etc
                value = match.group(2).strip()
                return {
                    "key": f"favorite_{thing}",
                    "value": value,
                    "category": category
                }
            
            elif pattern_name == 'habit_pattern':
                habit = match.group(1).strip()
                if len(habit) > 5:
                    return {
                        "key": f"habit_{self._slugify(habit[:20])}",
                        "value": habit,
                        "category": category
                    }
            
            elif pattern_name == 'routine_pattern':
                frequency = match.group(1).strip()  # sunday, day, week
                activity = match.group(2).strip()
                return {
                    "key": f"routine_{frequency}",
                    "value": activity,
                    "category": category
                }
            
            elif pattern_name == 'dietary_pattern':
                goal = match.group(1).strip()
                return {
                    "key": "dietary_goals",
                    "value": goal,
                    "category": category
                }
            
            elif pattern_name == 'protein_pattern':
                protein = match.group(1).strip()
                return {
                    "key": "meal_prep_protein",
                    "value": protein,
                    "category": category
                }
            
            elif pattern_name == 'grain_pattern':
                grain = match.group(1).strip()
                return {
                    "key": "meal_prep_grain",
                    "value": grain,
                    "category": category
                }
            
            elif pattern_name == 'meal_goal_add_pattern':
                goal = match.group(1).strip()
                if len(goal) > 5 and not self._is_too_generic(goal):
                    return {
                        "key": f"meal_prep_goal_{self._slugify(goal[:30])}",
                        "value": f"Add {goal}",
                        "category": category
                    }
            
            elif pattern_name == 'meal_goal_ensure_pattern':
                item = match.group(1).strip()
                quality = match.group(2).strip()
                return {
                    "key": f"meal_prep_{self._slugify(item)}",
                    "value": f"{item.title()} should be {quality}",
                    "category": category
                }
            
            elif pattern_name == 'weekly_routine_pattern':
                day = match.group(1).strip().title()  # Sunday
                activity = match.group(2).strip()
                return {
                    "key": f"routine_{day.lower()}",
                    "value": activity,
                    "category": category
                }
            
            elif pattern_name == 'name_pattern':
                name = match.group(1).strip()
                return {
                    "key": "name",
                    "value": name,
                    "category": category
                }
            
        except (IndexError, AttributeError) as e:
            logger.debug(f"Failed to process match for {pattern_name}: {e}")
        
        return None
    
    def _is_too_generic(self, text: str) -> bool:
        """Check if text is too generic to store.
        
        Args:
            text: Text to check
        
        Returns:
            True if too generic
        """
        generic_phrases = [
            'to', 'that', 'this', 'it', 'doing', 'things', 'stuff',
            'the', 'a', 'an', 'some', 'any', 'all', 'to do that'
        ]
        
        text_lower = text.lower().strip()
        
        # Exact matches
        if text_lower in generic_phrases:
            return True
        
        # Too short
        if len(text_lower) < 4:
            return True
        
        # Starts with generic words
        if text_lower.startswith(('to ', 'the ', 'a ', 'an ')):
            return True
        
        return False
    
    def _slugify(self, text: str) -> str:
        """Convert text to slug format.
        
        Args:
            text: Text to slugify
        
        Returns:
            Slugified text
        """
        # Remove special chars, lowercase, replace spaces with underscore
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[-\s]+', '_', slug)
        return slug.strip('_')
    
    def should_extract(self, message: str) -> bool:
        """Quick check if message likely contains facts.
        
        Args:
            message: User message
        
        Returns:
            True if message might contain facts
        """
        indicators = [
            r'\bi\s+(?:love|like|prefer|have|am|always|usually)',
            r'\bmy\s+(?:favorite|name|grandfather)',
            r'\bevery\s+\w+\s+i\b',
            r'\bi\'m\s+(?:from|trying)',
        ]
        
        message_lower = message.lower()
        for indicator in indicators:
            if re.search(indicator, message_lower):
                return True
        
        return False


# Global instance
_extractor = SmartFactExtractor()


def extract_facts_from_message(message: str) -> List[Dict[str, str]]:
    """Extract facts from a user message.
    
    Args:
        message: User's message
    
    Returns:
        List of extracted facts
    """
    if not _extractor.should_extract(message):
        return []
    
    return _extractor.extract_facts(message)
