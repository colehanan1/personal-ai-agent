"""Action executor for Milton action plans.

Executes validated action plans by calling canonical, existing handlers or
underlying storage APIs. No new business logic is introduced here.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from goals.capture import capture_goal
from milton_orchestrator.reminders import ReminderStore, parse_time_expression
from milton_orchestrator.state_paths import resolve_reminders_db_path, resolve_state_dir
from storage.chat_memory import ChatMemoryStore

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {
    "CREATE_MEMORY",
    "CREATE_REMINDER",
    "CREATE_GOAL",
}


def execute_action_plan(plan: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute a validated action plan.

    Returns:
        dict with keys: status, executed, errors, artifacts
    """
    context = context or {}
    action = plan.get("action")
    payload = plan.get("payload")

    if action not in ALLOWED_ACTIONS:
        return _result(
            status="error",
            errors=[f"unsupported_action:{action}"],
        )
    if not isinstance(payload, dict):
        return _result(
            status="error",
            errors=["invalid_payload"],
        )

    state_dir = _resolve_state_dir(context)

    if action == "CREATE_MEMORY":
        return _execute_memory(payload, state_dir)
    if action == "CREATE_REMINDER":
        return _execute_reminder(payload, state_dir, context)
    if action == "CREATE_GOAL":
        return _execute_goal(payload, state_dir)

    return _result(status="error", errors=["unsupported_action"])


def _execute_memory(payload: Dict[str, Any], state_dir: Path) -> Dict[str, Any]:
    key = _clean_text(payload.get("key") or "")
    value = _clean_text(payload.get("value") or "")
    text = _clean_text(payload.get("text") or "")

    if not key and text:
        key, value = _parse_key_value(text)

    if not key:
        key = _derive_key(text or value)
    if not value:
        value = text

    if not key or not value:
        return _result(status="error", errors=["memory_missing_key_or_value"])

    db_path = state_dir / "chat_memory.sqlite3"
    store = ChatMemoryStore(db_path)
    try:
        fact_id = store.upsert_fact(key, value)
    finally:
        store.close()

    logger.info(
        "action_executor.memory",
        extra={"action": "CREATE_MEMORY", "key": key, "fact_id": fact_id},
    )
    return _result(
        status="ok",
        executed=[{"action": "CREATE_MEMORY", "key": key, "id": fact_id}],
        artifacts={"memory_id": fact_id},
    )


def _execute_reminder(
    payload: Dict[str, Any],
    state_dir: Path,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    title = _clean_text(payload.get("title") or "")
    when = _clean_text(payload.get("when") or "")
    timezone_name = _clean_text(payload.get("timezone") or "") or _context_timezone(context)

    if not title or not when:
        return _result(status="error", errors=["reminder_missing_title_or_when"])

    due_at = parse_time_expression(when, timezone=timezone_name)
    if due_at is None:
        return _result(status="error", errors=["reminder_unparsable_time"])

    db_path = resolve_reminders_db_path(base_dir=state_dir)
    store = ReminderStore(db_path)
    try:
        existing_id = _find_existing_reminder(store, title, due_at)
        if existing_id is not None:
            logger.info(
                "action_executor.reminder",
                extra={"action": "CREATE_REMINDER", "id": existing_id, "deduped": True},
            )
            return _result(
                status="ok",
                executed=[{"action": "CREATE_REMINDER", "id": existing_id, "deduped": True}],
                artifacts={"reminder_id": existing_id, "deduped": True},
            )

        reminder_id = store.add_reminder(
            kind="REMIND",
            due_at=due_at,
            message=title,
            timezone=timezone_name,
        )
    finally:
        store._conn.close()

    logger.info(
        "action_executor.reminder",
        extra={"action": "CREATE_REMINDER", "id": reminder_id},
    )
    return _result(
        status="ok",
        executed=[{"action": "CREATE_REMINDER", "id": reminder_id}],
        artifacts={"reminder_id": reminder_id},
    )


def _execute_goal(payload: Dict[str, Any], state_dir: Path) -> Dict[str, Any]:
    title = _clean_text(payload.get("title") or "")
    if not title:
        return _result(status="error", errors=["goal_missing_title"])

    result = capture_goal(title, scope="daily", tags=["from-action-plan"], base_dir=state_dir)
    goal_id = result.get("id")
    status = result.get("status")

    logger.info(
        "action_executor.goal",
        extra={"action": "CREATE_GOAL", "id": goal_id, "status": status},
    )
    return _result(
        status="ok",
        executed=[{"action": "CREATE_GOAL", "id": goal_id, "status": status}],
        artifacts={"goal_id": goal_id, "status": status},
    )


def _find_existing_reminder(store: ReminderStore, message: str, due_at: int) -> Optional[int]:
    for reminder in store.list_reminders(include_sent=False, include_canceled=False):
        if reminder.message == message and reminder.due_at == due_at:
            return reminder.id
    return None


def _resolve_state_dir(context: Dict[str, Any]) -> Path:
    state_dir = context.get("state_dir")
    if state_dir:
        return resolve_state_dir(Path(state_dir))
    return resolve_state_dir()


def _context_timezone(context: Dict[str, Any]) -> str:
    tz = _clean_text(context.get("timezone") or "")
    return tz or "America/Chicago"


def _parse_key_value(text: str) -> tuple[str, str]:
    if ":" in text:
        key, value = text.split(":", 1)
        return _clean_text(key), _clean_text(value)
    if "=" in text:
        key, value = text.split("=", 1)
        return _clean_text(key), _clean_text(value)
    return "", ""


def _derive_key(text: str) -> str:
    cleaned = _clean_text(text).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    if not cleaned:
        return ""
    return cleaned[:60]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.encode("ascii", "ignore").decode("ascii")


def _result(
    status: str,
    executed: Optional[list] = None,
    errors: Optional[list] = None,
    artifacts: Optional[dict] = None,
) -> Dict[str, Any]:
    return {
        "status": status,
        "executed": executed or [],
        "errors": errors or [],
        "artifacts": artifacts or {},
    }
