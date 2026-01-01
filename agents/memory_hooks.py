"""Agent hooks for deterministic memory retrieval and storage."""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

from memory.retrieve import query_relevant
from memory.schema import MemoryItem
from memory.store import add_memory, get_user_profile


load_dotenv()

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def memory_enabled() -> bool:
    return _env_bool("MILTON_MEMORY_ENABLED", True)


def _profile_lines(profile_limit: int) -> list[str]:
    profile = get_user_profile()
    lines: list[str] = []
    if profile.preferences:
        lines.append(
            "User preferences: "
            + "; ".join(profile.preferences[:profile_limit])
        )
    if profile.stable_facts:
        lines.append(
            "User facts: "
            + "; ".join(profile.stable_facts[:profile_limit])
        )
    if profile.do_not_assume:
        lines.append(
            "Do not assume: "
            + "; ".join(profile.do_not_assume[:profile_limit])
        )
    return lines


def build_memory_context(agent_name: str, prompt: str) -> str:
    """Build a deterministic memory context block for LLM prompts."""
    if not memory_enabled():
        return ""
    if not prompt.strip():
        return ""

    limit = _env_int("MILTON_MEMORY_CONTEXT_LIMIT", 6)
    recency_bias = _env_float("MILTON_MEMORY_RECENCY_BIAS", 0.35)
    profile_limit = _env_int("MILTON_MEMORY_PROFILE_LIMIT", 5)
    max_chars = _env_int("MILTON_MEMORY_CONTEXT_MAX_CHARS", 2000)

    relevant = query_relevant(prompt, limit=limit, recency_bias=recency_bias)

    lines: list[str] = []
    lines.append("MEMORY CONTEXT (deterministic; optional for grounding)")

    for line in _profile_lines(profile_limit):
        if _safe_append(lines, line, max_chars):
            continue
        return "\n".join(lines)

    if relevant:
        if not _safe_append(lines, "Relevant memories:", max_chars):
            return "\n".join(lines)
        for item in relevant:
            summary = _format_item(item)
            if not _safe_append(lines, summary, max_chars):
                break
    else:
        _safe_append(lines, "Relevant memories: none", max_chars)

    return "\n".join(lines)


def _format_item(item: MemoryItem) -> str:
    tag_text = ", ".join(item.tags) if item.tags else "none"
    return (
        f"- [{item.id}] type={item.type} importance={item.importance:.2f} "
        f"tags={tag_text} :: {item.content}"
    )


def _safe_append(lines: list[str], line: str, max_chars: int) -> bool:
    candidate = "\n".join(lines + [line])
    if len(candidate) > max_chars:
        return False
    lines.append(line)
    return True


def record_memory(
    agent_name: str,
    content: str,
    *,
    memory_type: str = "crumb",
    tags: Optional[list[str]] = None,
    importance: Optional[float] = None,
    source: str = "user",
    request_id: Optional[str] = None,
) -> Optional[str]:
    """Store a short-term memory item; errors are logged and ignored."""
    if not memory_enabled():
        return None
    if not content.strip():
        return None

    base_tags = [f"agent:{agent_name.lower()}"]
    if tags:
        base_tags.extend(tags)

    memory_item = MemoryItem(
        agent=agent_name,
        type=memory_type,
        content=content.strip(),
        tags=base_tags,
        importance=importance if importance is not None else 0.2,
        source=source,
        request_id=request_id,
    )

    try:
        return add_memory(memory_item)
    except Exception as exc:
        logger.warning("Failed to record memory: %s", exc)
        return None


def should_store_responses() -> bool:
    return _env_bool("MILTON_MEMORY_STORE_RESPONSES", False)
