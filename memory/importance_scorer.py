"""
Importance Scoring for Milton Memory

Computes importance scores (0.0-1.0) for memory items based on:
- User flags and explicit importance markers
- Memory type (facts/decisions more important than crumbs)
- Task success/failure indicators
- Tag-based signals (blockers, goals, urgent)
"""
from __future__ import annotations

import logging
from typing import Optional

from .schema import MemoryItem

logger = logging.getLogger(__name__)

# Base importance by memory type
TYPE_WEIGHTS = {
    "fact": 0.8,
    "preference": 0.7,
    "decision": 0.75,
    "project": 0.7,
    "result": 0.6,
    "request": 0.5,
    "crumb": 0.2,
}

# Tag-based importance modifiers
TAG_MODIFIERS = {
    "important": 0.3,
    "urgent": 0.25,
    "blocker": 0.3,
    "goal": 0.2,
    "milestone": 0.2,
    "critical": 0.35,
    "success": 0.1,
    "failure": 0.15,
    "do_not_assume": 0.2,
}


def score(memory_item: MemoryItem) -> float:
    """
    Compute importance score for a memory item.

    Args:
        memory_item: The memory item to score

    Returns:
        Importance score from 0.0 (trivial) to 1.0 (critical)

    Example:
        >>> item = MemoryItem(type="fact", content="User prefers Python", tags=["important"])
        >>> score(item)
        0.95
    """
    # Start with type-based base score
    base_score = TYPE_WEIGHTS.get(memory_item.type, 0.3)

    # If item already has explicit importance, blend with computed score
    if memory_item.importance is not None and memory_item.importance > 0.0:
        # Take max of explicit and base score to respect user intent
        base_score = max(base_score, memory_item.importance)

    # Apply tag modifiers
    tag_boost = 0.0
    for tag in memory_item.tags:
        tag_lower = tag.lower()
        for tag_key, modifier in TAG_MODIFIERS.items():
            if tag_key in tag_lower:
                tag_boost += modifier
                break  # Only apply one modifier per tag

    # Compute final score (capped at 1.0)
    final_score = min(1.0, base_score + tag_boost)

    logger.debug(
        f"Scored memory {memory_item.id}: "
        f"type={memory_item.type} base={base_score:.2f} "
        f"tag_boost={tag_boost:.2f} final={final_score:.2f}"
    )

    return final_score


def update_importance(memory_item: MemoryItem) -> MemoryItem:
    """
    Update memory item importance based on scoring algorithm.

    Args:
        memory_item: The memory item to update

    Returns:
        Updated memory item with new importance score
    """
    computed_score = score(memory_item)
    memory_item.importance = computed_score
    return memory_item


def filter_by_importance(
    items: list[MemoryItem],
    min_importance: float = 0.5,
) -> list[MemoryItem]:
    """
    Filter memory items by minimum importance threshold.

    Args:
        items: List of memory items
        min_importance: Minimum importance score (0.0-1.0)

    Returns:
        Filtered list containing only items meeting threshold

    Example:
        >>> items = [
        ...     MemoryItem(type="fact", importance=0.8, ...),
        ...     MemoryItem(type="crumb", importance=0.2, ...)
        ... ]
        >>> important = filter_by_importance(items, min_importance=0.5)
        >>> len(important)
        1
    """
    threshold = max(0.0, min(1.0, min_importance))
    return [item for item in items if item.importance >= threshold]


def rank_by_importance(
    items: list[MemoryItem],
    reverse: bool = True,
) -> list[MemoryItem]:
    """
    Sort memory items by importance score.

    Args:
        items: List of memory items
        reverse: If True, sort descending (most important first)

    Returns:
        Sorted list of memory items
    """
    return sorted(items, key=lambda item: item.importance, reverse=reverse)


if __name__ == "__main__":
    # Test the importance scorer
    from datetime import datetime, timezone

    print("Testing importance scorer...")

    # Test different memory types
    test_items = [
        MemoryItem(
            agent="NEXUS",
            type="fact",
            content="User is pursuing PhD in AI",
            tags=["important"],
            importance=0.0,
            source="chat",
        ),
        MemoryItem(
            agent="CORTEX",
            type="decision",
            content="Decided to use Python for project",
            tags=["project:milton"],
            importance=0.0,
            source="chat",
        ),
        MemoryItem(
            agent="CORTEX",
            type="crumb",
            content="Random conversation message",
            tags=["agent:cortex"],
            importance=0.0,
            source="chat",
        ),
        MemoryItem(
            agent="NEXUS",
            type="project",
            content="Critical blocker in deployment",
            tags=["blocker", "urgent", "project:deployment"],
            importance=0.0,
            source="chat",
        ),
    ]

    print("\nScoring memory items:")
    for item in test_items:
        computed = score(item)
        item.importance = computed  # Update item importance
        print(f"  {item.type:12} | tags={', '.join(item.tags[:2]):30} | score={computed:.2f}")

    # Test filtering
    print(f"\nFiltering for importance >= 0.5:")
    important = filter_by_importance(test_items, min_importance=0.5)
    print(f"  Found {len(important)}/{len(test_items)} important items")

    # Test ranking
    print("\nRanking by importance:")
    ranked = rank_by_importance(test_items)
    for item in ranked:
        print(f"  {score(item):.2f} | {item.type:12} | {item.content[:40]}")
