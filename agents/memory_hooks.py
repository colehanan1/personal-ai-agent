"""Agent hooks for deterministic memory retrieval and storage."""

from __future__ import annotations

import logging
import os
from typing import Optional, Literal

from dotenv import load_dotenv

from memory.retrieve import query_relevant, query_relevant_hybrid
from memory.schema import MemoryItem
from memory.store import add_memory, get_user_profile
from memory.embeddings import is_available as embeddings_available


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
    """
    Build a deterministic memory context block for LLM prompts.
    
    Legacy function - preserved for backward compatibility.
    New code should use MemoryContextHook.build_context() instead.
    """
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


class MemoryContextHook:
    """
    Enhanced memory context builder using semantic embeddings.
    
    Provides semantic search capabilities when embeddings are available,
    with graceful fallback to deterministic retrieval.
    
    Attributes:
        agent: Agent name (NEXUS, CORTEX, etc.)
        use_semantic: Whether to use semantic search (if available)
        semantic_weight: Weight for semantic similarity (0.0-1.0)
        recency_bias: Weight for recency in scoring (0.0-1.0)
    
    Example:
        >>> hook = MemoryContextHook(agent="CORTEX")
        >>> context = hook.build_context("machine learning project", agent="CORTEX")
        >>> print(context)
    """
    
    def __init__(
        self,
        agent: str = "SYSTEM",
        use_semantic: bool = True,
        semantic_weight: float = 0.5,
        recency_bias: float = 0.35,
    ):
        """
        Initialize MemoryContextHook.
        
        Args:
            agent: Agent name for context generation
            use_semantic: Enable semantic search (falls back if unavailable)
            semantic_weight: Semantic similarity weight (0.0=deterministic, 1.0=pure semantic)
            recency_bias: Recency weight in deterministic scoring
        """
        self.agent = agent
        self.use_semantic = use_semantic
        self.semantic_weight = semantic_weight
        self.recency_bias = recency_bias
        
        # Check if semantic embeddings are available
        self._semantic_available = embeddings_available() if use_semantic else False
        
        if use_semantic and not self._semantic_available:
            logger.info(
                f"Semantic embeddings not available for {agent}. "
                "Install sentence-transformers for semantic search. Falling back to deterministic mode."
            )
    
    def build_context(self, user_message: str, agent: Optional[str] = None) -> str:
        """
        Fetch top-K relevant memories and return formatted context.
        
        Uses hybrid retrieval (semantic + deterministic) when embeddings available,
        otherwise falls back to pure deterministic retrieval.
        
        Args:
            user_message: User's message/query
            agent: Override agent name (uses self.agent if not provided)
            
        Returns:
            Formatted context string ready for LLM injection
            
        Example:
            >>> hook = MemoryContextHook(agent="CORTEX")
            >>> context = hook.build_context("Tell me about my Python projects")
            >>> # Returns formatted memory context with relevant items
        """
        if not memory_enabled():
            return ""
        
        if not user_message.strip():
            return ""
        
        agent_name = agent or self.agent
        
        # Get config from environment
        limit = _env_int("MILTON_MEMORY_CONTEXT_LIMIT", 6)
        profile_limit = _env_int("MILTON_MEMORY_PROFILE_LIMIT", 5)
        max_chars = _env_int("MILTON_MEMORY_CONTEXT_MAX_CHARS", 2000)
        
        # Choose retrieval mode
        if self.use_semantic and self._semantic_available:
            # Use hybrid retrieval with semantic embeddings
            retrieval_mode = "hybrid"
            relevant = query_relevant_hybrid(
                user_message,
                limit=limit,
                recency_bias=self.recency_bias,
                semantic_weight=self.semantic_weight,
                mode=retrieval_mode,
            )
            mode_label = f"hybrid (semantic={self.semantic_weight:.1f})"
        else:
            # Fallback to deterministic
            relevant = query_relevant(
                user_message,
                limit=limit,
                recency_bias=self.recency_bias,
            )
            mode_label = "deterministic"
        
        # Build context lines
        lines: list[str] = []
        lines.append(f"MEMORY CONTEXT ({mode_label}; optional for grounding)")
        
        # Add user profile
        for line in _profile_lines(profile_limit):
            if not _safe_append(lines, line, max_chars):
                return "\n".join(lines)
        
        # Add relevant memories
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
    
    def is_semantic_available(self) -> bool:
        """Check if semantic search is available."""
        return self._semantic_available
