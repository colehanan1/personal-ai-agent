"""Memory system status and retrieval tracking.

Provides observable metrics for memory backend state and retrieval activity.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalStats:
    """Statistics from the last memory retrieval."""

    query: str
    count: int  # Number of items retrieved
    timestamp: datetime
    mode: str  # "weaviate" | "jsonl" | "hybrid"
    duration_ms: Optional[float] = None


@dataclass
class MemoryStatus:
    """Complete memory system status."""

    mode: str  # "weaviate" | "jsonl" | "off"
    backend_available: bool  # Is configured backend reachable?
    degraded: bool  # Is system using fallback?
    detail: str  # Human-readable status message
    last_retrieval: Optional[RetrievalStats] = None
    warnings: list[str] = field(default_factory=list)


class MemoryStatusTracker:
    """
    Thread-safe tracker for memory system status and retrieval stats.

    Singleton pattern ensures all components share the same tracker.
    """

    _instance: Optional[MemoryStatusTracker] = None
    _lock = threading.Lock()

    def __init__(self):
        self._retrieval_lock = threading.Lock()
        self._last_retrieval: Optional[RetrievalStats] = None

    @classmethod
    def get_instance(cls) -> MemoryStatusTracker:
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record_retrieval(
        self,
        query: str,
        count: int,
        mode: str = "unknown",
        duration_ms: Optional[float] = None,
    ) -> None:
        """Record a memory retrieval event."""
        with self._retrieval_lock:
            self._last_retrieval = RetrievalStats(
                query=query,
                count=count,
                timestamp=datetime.now(timezone.utc),
                mode=mode,
                duration_ms=duration_ms,
            )
            logger.debug(
                f"Memory retrieval recorded: query='{query[:50]}...', "
                f"count={count}, mode={mode}"
            )

    def get_last_retrieval(self) -> Optional[RetrievalStats]:
        """Get statistics from the last retrieval."""
        with self._retrieval_lock:
            return self._last_retrieval

    def clear(self) -> None:
        """Clear tracked stats (useful for testing)."""
        with self._retrieval_lock:
            self._last_retrieval = None


# Global singleton instance
_tracker = MemoryStatusTracker.get_instance()


def record_retrieval(
    query: str,
    count: int,
    mode: str = "unknown",
    duration_ms: Optional[float] = None,
) -> None:
    """Record a memory retrieval event (convenience function)."""
    _tracker.record_retrieval(query, count, mode, duration_ms)


def get_last_retrieval() -> Optional[RetrievalStats]:
    """Get statistics from the last retrieval (convenience function)."""
    return _tracker.get_last_retrieval()


def get_memory_status() -> MemoryStatus:
    """
    Get complete memory system status.

    Returns current backend mode, availability, degradation state,
    and last retrieval statistics.
    """
    from memory.backends import backend_status

    backend = backend_status()
    warnings: list[str] = []

    # Detect degraded state and add warnings
    if backend.degraded:
        warnings.append(
            "Weaviate configured but unreachable; using local JSONL fallback"
        )

    # Check if memory is effectively disabled
    backend_available = True
    if backend.mode == "off":
        backend_available = False
        warnings.append("Memory system is disabled")
    elif backend.mode == "jsonl" and not backend.degraded:
        # JSONL is intentional, not a fallback
        backend_available = True
    elif backend.mode == "weaviate" and backend.weaviate_available:
        backend_available = True
    else:
        backend_available = False

    return MemoryStatus(
        mode=backend.mode,
        backend_available=backend_available,
        degraded=backend.degraded,
        detail=backend.detail,
        last_retrieval=get_last_retrieval(),
        warnings=warnings,
    )
