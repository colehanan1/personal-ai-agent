"""
FRONTIER Discovery Cache

Implements TTL-based caching for research discovery results to ensure:
- Deterministic output (same query returns cached results within TTL)
- Local-first operation (reduces external API calls)
- Offline capability (can work with cached data)

Cache storage: STATE_DIR/cache/frontier/
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, List
import logging

from milton_orchestrator.state_paths import resolve_state_dir

logger = logging.getLogger(__name__)

# Default cache TTL: 6 hours for research discovery
DEFAULT_CACHE_TTL_HOURS = 6


class DiscoveryCache:
    """
    TTL-based cache for FRONTIER discovery results.

    Cache keys are derived from:
    - Source type (arxiv, news, etc.)
    - Query parameters
    - Timestamp (for TTL validation)

    Storage format: JSON files in STATE_DIR/cache/frontier/
    """

    def __init__(self, cache_dir: Optional[Path] = None, ttl_hours: int = DEFAULT_CACHE_TTL_HOURS):
        """
        Initialize discovery cache.

        Args:
            cache_dir: Cache directory (defaults to STATE_DIR/cache/frontier)
            ttl_hours: Time-to-live in hours (default: 6)
        """
        if cache_dir is None:
            state_dir = resolve_state_dir()
            cache_dir = state_dir / "cache" / "frontier"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours

        logger.debug(f"DiscoveryCache initialized: {self.cache_dir}, TTL={ttl_hours}h")

    def _generate_cache_key(self, source: str, query: str, params: Dict[str, Any]) -> str:
        """
        Generate deterministic cache key from source, query, and params.

        Args:
            source: Source type (arxiv, news, etc.)
            query: Search query
            params: Additional parameters (max_results, filters, etc.)

        Returns:
            Cache key (hex digest)
        """
        # Normalize params for deterministic key
        normalized_params = json.dumps(params, sort_keys=True)
        key_data = f"{source}:{query}:{normalized_params}"

        # Hash to avoid filesystem issues with special chars
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]

        return f"{source}_{key_hash}"

    def _cache_file_path(self, cache_key: str) -> Path:
        """Get cache file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, source: str, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached discovery results if available and not expired.

        Args:
            source: Source type (arxiv, news, etc.)
            query: Search query
            params: Additional parameters

        Returns:
            Cached data dict or None if not found/expired
        """
        params = params or {}
        cache_key = self._generate_cache_key(source, query, params)
        cache_file = self._cache_file_path(cache_key)

        if not cache_file.exists():
            logger.debug(f"Cache miss: {cache_key}")
            return None

        try:
            with cache_file.open("r") as f:
                cached_data = json.load(f)

            # Check TTL
            cached_at = datetime.fromisoformat(cached_data["cached_at"])
            now = datetime.now(timezone.utc)

            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)

            age_hours = (now - cached_at).total_seconds() / 3600

            if age_hours > self.ttl_hours:
                logger.debug(f"Cache expired: {cache_key} (age={age_hours:.1f}h)")
                # Clean up expired cache
                cache_file.unlink(missing_ok=True)
                return None

            logger.debug(f"Cache hit: {cache_key} (age={age_hours:.1f}h)")
            return cached_data["data"]

        except Exception as e:
            logger.warning(f"Cache read error for {cache_key}: {e}")
            # Clean up corrupted cache
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, source: str, query: str, data: Any, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Store discovery results in cache.

        Args:
            source: Source type (arxiv, news, etc.)
            query: Search query
            data: Data to cache (must be JSON-serializable)
            params: Additional parameters
        """
        params = params or {}
        cache_key = self._generate_cache_key(source, query, params)
        cache_file = self._cache_file_path(cache_key)

        cache_entry = {
            "source": source,
            "query": query,
            "params": params,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "ttl_hours": self.ttl_hours,
            "data": data,
        }

        try:
            with cache_file.open("w") as f:
                json.dump(cache_entry, f, indent=2)

            logger.debug(f"Cached: {cache_key}")

        except Exception as e:
            logger.error(f"Cache write error for {cache_key}: {e}")

    def clear(self, source: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            source: If provided, only clear entries for this source

        Returns:
            Number of entries cleared
        """
        if not self.cache_dir.exists():
            return 0

        cleared = 0

        for cache_file in self.cache_dir.glob("*.json"):
            if source is None:
                cache_file.unlink()
                cleared += 1
            else:
                # Check if file matches source
                if cache_file.stem.startswith(f"{source}_"):
                    cache_file.unlink()
                    cleared += 1

        logger.info(f"Cleared {cleared} cache entries" + (f" for source={source}" if source else ""))
        return cleared

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats (total entries, by source, oldest/newest)
        """
        if not self.cache_dir.exists():
            return {"total": 0, "by_source": {}}

        stats = {
            "total": 0,
            "by_source": {},
            "oldest": None,
            "newest": None,
        }

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with cache_file.open("r") as f:
                    cached_data = json.load(f)

                source = cached_data.get("source", "unknown")
                cached_at = datetime.fromisoformat(cached_data["cached_at"])

                stats["total"] += 1
                stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

                if stats["oldest"] is None or cached_at < stats["oldest"]:
                    stats["oldest"] = cached_at.isoformat()

                if stats["newest"] is None or cached_at > stats["newest"]:
                    stats["newest"] = cached_at.isoformat()

            except Exception:
                pass

        return stats


# Global cache instance (lazily initialized)
_global_cache: Optional[DiscoveryCache] = None


def get_discovery_cache() -> DiscoveryCache:
    """
    Get global discovery cache instance.

    Returns:
        DiscoveryCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = DiscoveryCache()

    return _global_cache
