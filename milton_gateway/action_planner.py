"""Deterministic action planner for Milton chat inputs.

Converts free-form user text into a strict, machine-parseable action plan
without executing any side effects.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from milton_gateway.reminder_intent_normalizer import ReminderIntentNormalizer
from milton_gateway.smart_fact_extractor import SmartFactExtractor

DEFAULT_TIMEZONE = "America/Chicago"

ACTION_TYPES = {
    "CREATE_MEMORY",
    "CREATE_REMINDER",
    "CREATE_GOAL",
    "CLARIFY",
    "NOOP",
}

REQUIRED_FIELDS = {
    "CREATE_MEMORY": ("text",),
    "CREATE_REMINDER": ("title", "when", "timezone"),
    "CREATE_GOAL": ("title",),
    "CLARIFY": ("question",),
    "NOOP": ("reason",),
}


def extract_action_plan(user_text: str, now_iso: str, timezone: str) -> Dict[str, Any]:
    """Extract a strict action plan from user text.

    Returns a dict with shape:
      {"action": "<TYPE>", "payload": {...}}
    
    Note: This function returns NOOP for unrecognized patterns.
    The caller can check should_use_llm_fallback() and invoke the async
    LLM classifier if appropriate.
    """
    text = _clean_text(user_text)
    if not text:
        return _noop("empty_input")

    tz = _clean_text(timezone) or DEFAULT_TIMEZONE
    now = _parse_now(now_iso) or datetime.utcnow()

    reminder_payload, reminder_clarify, reminder_conf = _parse_explicit_reminder(text)
    if reminder_payload:
        reminder_payload["timezone"] = tz
        return _validated_or_fallback(
            "CREATE_REMINDER", reminder_payload, reminder_conf,
            "User requested reminder with explicit time"
        )
    if reminder_clarify:
        return _clarify(reminder_clarify)

    reminder_payload, reminder_clarify, reminder_conf = _parse_normalized_reminder(text, now, tz)
    if reminder_payload:
        return _validated_or_fallback(
            "CREATE_REMINDER", reminder_payload, reminder_conf,
            "User requested reminder via natural language"
        )
    if reminder_clarify:
        return _clarify(reminder_clarify)

    goal_payload, goal_clarify, goal_conf = _parse_goal(text)
    if goal_payload:
        return _validated_or_fallback(
            "CREATE_GOAL", goal_payload, goal_conf,
            "User defined a goal"
        )
    if goal_clarify:
        return _clarify(goal_clarify)

    memory_payload, memory_clarify, memory_conf = _parse_memory(text)
    if memory_payload:
        return _validated_or_fallback(
            "CREATE_MEMORY", memory_payload, memory_conf,
            "User asked to store information"
        )
    if memory_clarify:
        return _clarify(memory_clarify)

    return _noop("no_action_detected")


def should_use_llm_fallback(plan: Dict[str, Any], user_text: str) -> bool:
    """Check if LLM fallback should be attempted for this plan.
    
    Returns True if:
    - Plan is NOOP (primary detection failed)
    - Text contains action-indicating keywords
    
    This is a heuristic gate before expensive LLM classification.
    
    Args:
        plan: Result from extract_action_plan
        user_text: Original user text
        
    Returns:
        True if LLM fallback should be attempted
    """
    # Only fallback if primary planner returned NOOP
    if plan.get("action") != "NOOP":
        return False
    
    # Import here to avoid circular dependency
    from milton_gateway.llm_intent_classifier import should_use_fallback
    
    return should_use_fallback(user_text)


def _parse_explicit_reminder(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """Handle reminder phrasings not covered by the normalizer.

    Returns: (payload, clarify_question, confidence)
    """
    patterns = [
        (
            r"\bremind me\s+(tomorrow|today|tonight)\s+at\s+"
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+to\s+(.+)",
            "relative_explicit",
            0.95,
        ),
        (
            r"\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday)s?\s+at\s+"
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(?:remind me\s+(?:to\s+)?)?(.+)",
            "recurring_explicit",
            0.9,
        ),
        # "remind me in 10 minutes to X" - inverted form
        (
            r"\bremind me\s+in\s+(\d+)\s*(minutes?|mins?|m|hours?|hrs?|h)\s+to\s+(.+)",
            "relative_duration",
            0.95,
        ),
    ]
    for pattern, _label, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        if _label == "relative_explicit":
            day_str = match.group(1)
            time_str = match.group(2)
            task = match.group(3)
            when = f"{day_str} at {time_str}"
        elif _label == "relative_duration":
            amount = match.group(1)
            unit = match.group(2).lower()
            task = match.group(3)
            # Normalize unit
            if unit.startswith("h"):
                unit_str = "hour" if amount == "1" else "hours"
            else:
                unit_str = "minute" if amount == "1" else "minutes"
            when = f"in {amount} {unit_str}"
        else:
            day_str = match.group(1)
            time_str = match.group(2)
            task = match.group(3)
            when = f"every {day_str} at {time_str}"
        title = _clean_text(task)
        if not title:
            return None, "What should the reminder be about?", 0.0
        return {
            "title": title,
            "when": _clean_text(when),
            "priority": "med",
            "channel": "ntfy",
        }, None, confidence
    return None, None, 0.0


def _parse_normalized_reminder(
    text: str, now: datetime, timezone: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """Parse reminder using the intent normalizer.

    Returns: (payload, clarify_question, confidence)
    """
    normalizer = ReminderIntentNormalizer()
    intent = normalizer.normalize(text, now=now)
    if not intent:
        return None, None, 0.0

    if intent.needs_clarification or not intent.task:
        question = intent.clarifying_question or "When should I set the reminder?"
        return None, _clean_text(question), intent.confidence

    when = intent.time_expression
    if not when and intent.due_at:
        when = _iso_from_timestamp(intent.due_at)
    if not when:
        return None, "When should I set the reminder?", intent.confidence

    payload: Dict[str, Any] = {
        "title": _clean_text(intent.task),
        "when": _clean_text(when),
        "timezone": _clean_text(timezone) or DEFAULT_TIMEZONE,
        "priority": intent.priority or "med",
        "channel": intent.channel or "ntfy",
    }
    if intent.recurrence:
        payload["notes"] = _clean_text(f"recurrence: {intent.recurrence}")
    return payload, None, intent.confidence


def _parse_goal(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """Parse goal intent from text.

    Returns: (payload, clarify_question, confidence)
    """
    goal_prompt = re.search(
        r"\b(add|set|create)\s+(?:a\s+)?goal(?:\s+(?:to\s+)?(.+))?$",
        text,
        re.IGNORECASE,
    )
    if goal_prompt:
        title = (goal_prompt.group(2) or "").strip()
        if not title:
            return None, "What goal should I set?", 0.5
        title = _clean_text(title)
        if not title or len(title) < 3:
            return None, "What goal should I set?", 0.5
        return {"title": title}, None, 0.9

    patterns = [
        (
            r"\bmy goal\s+(?:this|for this)?\s*(week|month|today|day)\s+is\s+(.+)",
            "scoped_goal",
            0.9,
        ),
        (r"\bmy goal is\s+(.+)", "simple_goal", 0.85),
        (r"\bgoal\s*:\s*(.+)", "colon_goal", 0.9),
        (r"\b(i need to|i want to|i have to)\s+(.+?)\s+by\s+(.+)", "due_goal", 0.85),
    ]
    for pattern, label, confidence in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        if label == "scoped_goal":
            scope = match.group(1).strip()
            title = match.group(2).strip()
            due = f"this {scope}"
        elif label == "due_goal":
            title = match.group(2).strip()
            due = match.group(3).strip()
            if not due:
                return None, "What is the due date for this goal?", 0.5
        else:
            title = match.group(1).strip()
            due = None

        title = _clean_text(title)
        if not title or len(title) < 3:
            return None, "What goal should I set?", 0.5
        payload: Dict[str, Any] = {"title": title}
        if due:
            payload["due"] = _clean_text(due)
        return payload, None, confidence
    return None, None, 0.0


def _parse_memory(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """Parse memory storage intent from text.

    Returns: (payload, clarify_question, confidence)
    """
    explicit_patterns = [
        (r"^(?:please\s+)?remember(?:\s+that)?\s+my\s+(.+?)\s+is\s+(.+)$", 0.95),
        (r"^(?:please\s+)?remember(?:\s+that)?\s+([^:=]+?)\s*[:=]\s*(.+)$", 0.95),
        (r"^(?:please\s+)?remember(?:\s+that)?\s+(.+)$", 0.9),
    ]
    for pattern, confidence in explicit_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        if match.lastindex >= 2:
            key_raw = match.group(1).strip()
            value_raw = match.group(2).strip()
            if not value_raw:
                return None, "What should I remember?", 0.5
            key = _normalize_key(key_raw)
            value = _clean_text(value_raw)
            payload = {
                "text": _clean_text(f"{key}: {value}") if key else value,
                "key": key or None,
                "value": value,
            }
            return _strip_none(payload), None, confidence
        elif match.lastindex == 1:
            memory_text = _clean_text(match.group(1).strip())
            if not memory_text:
                return None, "What should I remember?", 0.5
            return {"text": memory_text}, None, confidence

    extractor = SmartFactExtractor()
    facts = extractor.extract_facts(text)
    if facts:
        fact = facts[0]
        key = _normalize_key(fact.get("key", ""))
        value = _clean_text(fact.get("value", ""))
        if not value:
            return None, "What should I remember?", 0.5
        payload = {
            "text": _clean_text(f"{key}: {value}") if key else value,
            "key": key or None,
            "value": value,
        }
        category = _clean_text(fact.get("category", ""))
        if category:
            payload["tags"] = [category]
        return _strip_none(payload), None, 0.8  # Implicit fact extraction = lower confidence

    return None, None, 0.0


def _validated_or_fallback(
    action: str, payload: Dict[str, Any], confidence: float = 0.9, rationale: str = ""
) -> Dict[str, Any]:
    plan = {
        "action": action,
        "confidence": round(min(1.0, max(0.0, confidence)), 2),
        "payload": _sanitize_payload(payload),
        "rationale_short": _clean_text(rationale)[:160] if rationale else _default_rationale(action),
    }
    ok, _reason = _validate_action_plan(plan)
    if ok:
        return plan
    if action in ("CREATE_MEMORY", "CREATE_REMINDER", "CREATE_GOAL"):
        return _clarify("Could you clarify what you want me to do?")
    return _noop("invalid_plan")


def _default_rationale(action: str) -> str:
    """Return a default rationale for an action type."""
    rationales = {
        "CREATE_MEMORY": "User explicitly asked to remember information",
        "CREATE_REMINDER": "User requested a reminder with time",
        "CREATE_GOAL": "User defined a goal to track",
        "CLARIFY": "Need more information to proceed",
        "NOOP": "No actionable intent detected",
    }
    return rationales.get(action, "Action detected")


def _validate_action_plan(plan: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(plan, dict):
        return False, "plan_not_dict"
    action = plan.get("action")
    payload = plan.get("payload")
    if action not in ACTION_TYPES:
        return False, "unknown_action"
    if not isinstance(payload, dict):
        return False, "payload_not_dict"
    required = REQUIRED_FIELDS.get(action, ())
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, f"missing_{field}"
    return True, "ok"


def _clarify(question: str, confidence: float = 0.5) -> Dict[str, Any]:
    return {
        "action": "CLARIFY",
        "confidence": round(min(1.0, max(0.0, confidence)), 2),
        "payload": {"question": _clean_text(question)},
        "rationale_short": "Need more information to proceed",
    }


def _noop(reason: str) -> Dict[str, Any]:
    return {
        "action": "NOOP",
        "confidence": 1.0,
        "payload": {"reason": _clean_text(reason)},
        "rationale_short": "No actionable intent detected",
    }


def _parse_now(now_iso: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(now_iso)
    except Exception:
        return None


def _iso_from_timestamp(timestamp: int) -> str:
    try:
        return datetime.utcfromtimestamp(int(timestamp)).isoformat() + "Z"
    except Exception:
        return ""


def _normalize_key(value: str) -> str:
    key = _clean_text(value)
    if key.lower().startswith("my "):
        key = key[3:]
    key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return key


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.encode("ascii", "ignore").decode("ascii")


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            sanitized[key] = _sanitize_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [_clean_text(v) for v in value if _clean_text(v)]
        elif isinstance(value, str):
            cleaned = _clean_text(value)
            if cleaned:
                sanitized[key] = cleaned
        elif value is not None:
            sanitized[key] = value
    return sanitized


def _strip_none(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
