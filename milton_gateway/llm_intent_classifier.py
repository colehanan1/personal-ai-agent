"""LLM-assisted intent classification fallback for Milton action planner.

This module provides a safety-critical fallback when rule-based intent detection
fails. It uses an LLM to classify intents but with strict constraints:
- Only triggered when NOOP + likely action request
- Strict JSON schema output (no prose)
- High confidence threshold (0.85+)
- All required fields must be present
- Comprehensive logging for audit
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Action request indicators that trigger fallback
ACTION_KEYWORDS = {
    "reminder": ["reminder", "remind", "set a reminder", "create a reminder", 
                 "add a reminder", "schedule a reminder", "schedule", "alert"],
    "goal": ["goal", "set a goal", "add a goal", "create a goal", "achieve", "accomplish"],
    "memory": ["remember", "save", "store", "note that", "keep track", "record"],
}

# Minimum confidence threshold for execution
MIN_CONFIDENCE_THRESHOLD = 0.85

# Schema for LLM classifier output
CLASSIFIER_SCHEMA = {
    "intent_type": ["reminder", "goal", "memory", "unknown"],
    "action": ["add", "list", "delete", "noop"],
    "payload": "dict",
    "confidence": "float (0.0-1.0)",
    "missing_fields": "list of str",
}


def should_use_fallback(text: str) -> bool:
    """Heuristic to determine if text likely requests an action despite NOOP.
    
    Returns True if text contains action-related keywords but the primary
    planner returned NOOP (suggesting a phrasing we haven't seen before).
    
    Args:
        text: User's input text
        
    Returns:
        True if fallback should be attempted
    """
    text_lower = text.lower()
    
    # Check for any action keywords
    for category, keywords in ACTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                logger.debug(f"Fallback trigger: found '{keyword}' in category '{category}'")
                return True
    
    # Check for imperative verbs that suggest action requests
    imperative_patterns = [
        r'\b(set|create|add|make|schedule|plan|track)\b',
        r'\b(help me|can you|could you|please)\b',
    ]
    
    for pattern in imperative_patterns:
        if re.search(pattern, text_lower):
            logger.debug(f"Fallback trigger: matched imperative pattern '{pattern}'")
            return True
    
    return False


async def classify_intent_with_llm(
    text: str, 
    llm_client,
    now_iso: str,
    timezone: str
) -> Optional[Dict[str, Any]]:
    """Use LLM to classify intent when regex patterns fail.
    
    This is a safety-critical function. It:
    1. Prompts LLM with strict schema requirements
    2. Validates output is single-line ASCII JSON
    3. Validates all fields match schema
    4. Returns None if any validation fails
    
    Args:
        text: User's input text
        llm_client: LLM client for making requests
        now_iso: Current time in ISO format
        timezone: User's timezone
        
    Returns:
        Validated classification dict or None if invalid
    """
    # Build strict classification prompt
    prompt = _build_classification_prompt(text, now_iso, timezone)
    
    try:
        # Call LLM with low temperature for deterministic output
        messages = [
            {"role": "system", "content": "You are a strict JSON classifier. Output ONLY valid JSON, no prose."},
            {"role": "user", "content": prompt}
        ]
        
        result = await llm_client.chat_completion(
            messages=messages,
            temperature=0.0,  # Deterministic
            max_tokens=512,
            stream=False,
        )
        
        response_text = result["choices"][0]["message"]["content"].strip()
        
        logger.info(f"📊 LLM classifier raw output: {response_text[:200]}")
        
        # Validate and parse response
        classification = _parse_and_validate_classification(response_text)
        
        if classification:
            logger.info(f"✅ LLM classifier validated: intent={classification.get('intent_type')}, "
                       f"confidence={classification.get('confidence')}")
        else:
            logger.warning(f"❌ LLM classifier output failed validation")
        
        return classification
        
    except Exception as e:
        logger.error(f"LLM classifier error: {e}")
        return None


def _build_classification_prompt(text: str, now_iso: str, timezone: str) -> str:
    """Build strict classification prompt for LLM.
    
    The prompt explicitly constrains the LLM to output only JSON matching
    our schema, with no additional commentary.
    """
    return f"""Classify this user request into a structured action plan.

User input: "{text}"
Current time: {now_iso}
Timezone: {timezone}

Output EXACTLY ONE LINE of ASCII-only JSON with this structure:
{{
  "intent_type": "reminder"|"goal"|"memory"|"unknown",
  "action": "add"|"list"|"delete"|"noop",
  "payload": {{
    // For reminder: {{"title": str, "when": str, "timezone": str}}
    // For goal: {{"title": str, "due": str}}
    // For memory: {{"key": str, "value": str, "text": str}}
  }},
  "confidence": 0.0-1.0,
  "missing_fields": [list of str if any required fields are missing]
}}

Rules:
1. If user wants to create/add a reminder/goal/memory: action="add"
2. If user wants to list items: action="list"
3. If user wants to delete: action="delete"
4. If unclear or not an action: action="noop", intent_type="unknown"
5. Confidence < 0.85 means uncertain - mark missing_fields or use action="noop"
6. For reminders: extract "when" from phrases like "tomorrow at 4:30 PM"
7. If time is vague (e.g., "tomorrow" without time), add "when" to missing_fields

Output JSON only, no explanation:"""


def _parse_and_validate_classification(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse and validate LLM classifier output.
    
    Performs strict validation:
    1. Must be valid JSON
    2. Must be single line (no markdown, no code blocks)
    3. Must match schema
    4. All fields must be correct types
    
    Args:
        response_text: Raw LLM output
        
    Returns:
        Validated dict or None if invalid
    """
    # Remove markdown code blocks if present (defensive)
    text = response_text.strip()
    if text.startswith("```"):
        # Extract JSON from code block
        lines = text.split("\n")
        json_lines = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or (not line.strip().startswith("```")):
                json_lines.append(line)
        text = "\n".join(json_lines).strip()
    
    # Remove any leading/trailing whitespace and newlines
    text = " ".join(text.split())
    
    # Validate ASCII-only
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        logger.warning("LLM classifier output contains non-ASCII characters")
        return None
    
    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"LLM classifier output is not valid JSON: {e}")
        return None
    
    # Validate schema
    if not isinstance(data, dict):
        logger.warning("LLM classifier output is not a dict")
        return None
    
    # Validate intent_type
    intent_type = data.get("intent_type")
    if intent_type not in CLASSIFIER_SCHEMA["intent_type"]:
        logger.warning(f"Invalid intent_type: {intent_type}")
        return None
    
    # Validate action
    action = data.get("action")
    if action not in CLASSIFIER_SCHEMA["action"]:
        logger.warning(f"Invalid action: {action}")
        return None
    
    # Validate payload
    payload = data.get("payload")
    if not isinstance(payload, dict):
        logger.warning("Payload is not a dict")
        return None
    
    # Validate confidence
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        logger.warning(f"Confidence is not a number: {confidence}")
        return None
    if not (0.0 <= confidence <= 1.0):
        logger.warning(f"Confidence out of range: {confidence}")
        return None
    
    # Validate missing_fields
    missing_fields = data.get("missing_fields")
    if not isinstance(missing_fields, list):
        logger.warning("missing_fields is not a list")
        return None
    
    # All validations passed
    return data


def should_execute_classification(classification: Dict[str, Any]) -> bool:
    """Determine if classification is safe to execute.
    
    Safety gates:
    1. intent_type != "unknown"
    2. action != "noop"
    3. confidence >= MIN_CONFIDENCE_THRESHOLD
    4. missing_fields is empty
    
    Args:
        classification: Validated classification dict
        
    Returns:
        True if safe to execute, False otherwise
    """
    intent_type = classification.get("intent_type")
    action = classification.get("action")
    confidence = classification.get("confidence", 0.0)
    missing_fields = classification.get("missing_fields", [])
    
    # Check each safety gate
    if intent_type == "unknown":
        logger.info(f"🚫 Cannot execute: intent_type is 'unknown'")
        return False
    
    if action == "noop":
        logger.info(f"🚫 Cannot execute: action is 'noop'")
        return False
    
    if confidence < MIN_CONFIDENCE_THRESHOLD:
        logger.info(f"🚫 Cannot execute: confidence {confidence} < {MIN_CONFIDENCE_THRESHOLD}")
        return False
    
    if missing_fields:
        logger.info(f"🚫 Cannot execute: missing fields {missing_fields}")
        return False
    
    logger.info(f"✅ Safe to execute: intent={intent_type}, action={action}, confidence={confidence}")
    return True


def convert_classification_to_plan(
    classification: Dict[str, Any],
    timezone: str
) -> Dict[str, Any]:
    """Convert LLM classification to action planner format.
    
    Maps from classifier schema to action planner schema:
    - intent_type + action -> ACTION_TYPES (CREATE_REMINDER, etc.)
    - payload -> payload (with normalization)
    - confidence -> confidence
    
    Args:
        classification: Validated classification dict
        timezone: User's timezone
        
    Returns:
        Action plan dict compatible with execute_action_plan
    """
    intent_type = classification["intent_type"]
    action = classification["action"]
    payload = classification["payload"].copy()
    confidence = classification["confidence"]
    
    # Map to action planner format
    if intent_type == "reminder" and action == "add":
        action_type = "CREATE_REMINDER"
        # Ensure timezone is set
        if "timezone" not in payload:
            payload["timezone"] = timezone
    elif intent_type == "goal" and action == "add":
        action_type = "CREATE_GOAL"
    elif intent_type == "memory" and action == "add":
        action_type = "CREATE_MEMORY"
    else:
        # Shouldn't reach here due to should_execute_classification checks
        return {
            "action": "NOOP",
            "confidence": 0.0,
            "payload": {"reason": "invalid_classification"},
            "rationale_short": "LLM classification could not be mapped to action",
        }
    
    return {
        "action": action_type,
        "confidence": round(confidence, 2),
        "payload": payload,
        "rationale_short": f"LLM-classified as {intent_type}.{action}",
        "source": "llm_fallback",  # Mark as fallback for audit
    }
