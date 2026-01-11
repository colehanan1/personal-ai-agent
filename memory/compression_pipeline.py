"""
Compression Pipeline Module

Alias/wrapper for memory.compress module to match Week 1 naming convention.
Provides LLM-driven summarization and compression routines.
"""
from __future__ import annotations

# Import all public API from compress module
from .compress import (
    PROJECT_TAG_PREFIX,
    compress_short_to_long,
)

__all__ = [
    "PROJECT_TAG_PREFIX",
    "compress_short_to_long",
]


# Additional pipeline functions for daily/weekly routines

def daily_compression(cutoff_hours: int = 48, **kwargs) -> dict[str, int]:
    """
    Daily compression routine: short-term → working summaries.

    Args:
        cutoff_hours: Hours before which items are compressed (default: 48)
        **kwargs: Additional args passed to compress_short_to_long

    Returns:
        Dictionary with compression statistics
    """
    return compress_short_to_long(cutoff_hours=cutoff_hours, **kwargs)


def weekly_compression(cutoff_hours: int = 168, **kwargs) -> dict[str, int]:
    """
    Weekly compression routine: working → long-term themes.

    Args:
        cutoff_hours: Hours before which items are compressed (default: 168 = 1 week)
        **kwargs: Additional args passed to compress_short_to_long

    Returns:
        Dictionary with compression statistics
    """
    return compress_short_to_long(cutoff_hours=cutoff_hours, **kwargs)
