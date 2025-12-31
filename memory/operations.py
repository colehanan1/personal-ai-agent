"""
Weaviate Memory Operations
CRUD operations for short-term, working, and long-term memory.
"""
import json
import weaviate
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import uuid
from .init_db import get_client


def _serialize_metadata(metadata: Optional[Dict[str, Any]]) -> str:
    if not metadata:
        return "{}"
    return json.dumps(metadata)


def _deserialize_metadata(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class MemoryOperations:
    """Handles all memory CRUD operations."""

    def __init__(self, client: Optional[weaviate.WeaviateClient] = None):
        """
        Initialize memory operations.

        Args:
            client: Weaviate client instance (optional, creates new if not provided)
        """
        self.client = client or get_client()
        self._close_on_exit = client is None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._close_on_exit:
            self.client.close()

    # === Short-Term Memory Operations ===

    def add_short_term(
        self,
        agent: str,
        content: str,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add entry to short-term memory.

        Args:
            agent: Name of the agent (CORTEX, NEXUS, FRONTIER)
            content: Memory content
            context: Additional context
            metadata: Additional metadata

        Returns:
            UUID of created memory entry
        """
        collection = self.client.collections.get("ShortTermMemory")

        memory_id = collection.data.insert(
            properties={
                "timestamp": _now_rfc3339(),
                "agent": agent,
                "content": content,
                "context": context,
                "metadata": _serialize_metadata(metadata),
            }
        )

        return str(memory_id)

    def get_recent_short_term(
        self, hours: int = 24, agent: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent short-term memories.

        Args:
            hours: How many hours back to retrieve
            agent: Filter by specific agent (optional)

        Returns:
            List of memory entries
        """
        collection = self.client.collections.get("ShortTermMemory")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = collection.query.fetch_objects(limit=100)

        results = []
        for obj in query.objects:
            props = obj.properties
            parsed = _parse_timestamp(props.get("timestamp"))
            if parsed and parsed >= cutoff:
                props["metadata"] = _deserialize_metadata(props.get("metadata"))
                if agent is None or props["agent"] == agent:
                    results.append({"id": str(obj.uuid), **props})

        return sorted(results, key=lambda x: x["timestamp"], reverse=True)

    def delete_old_short_term(self, hours: int = 48) -> int:
        """
        Delete short-term memories older than specified hours.

        Args:
            hours: Age threshold in hours

        Returns:
            Number of deleted entries
        """
        collection = self.client.collections.get("ShortTermMemory")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = collection.query.fetch_objects(limit=1000)

        deleted = 0
        for obj in query.objects:
            props = obj.properties
            parsed = _parse_timestamp(props.get("timestamp"))
            if parsed and parsed < cutoff:
                collection.data.delete_by_id(obj.uuid)
                deleted += 1

        return deleted

    # === Working Memory Operations ===

    def add_working_memory(
        self,
        task_id: str,
        agent: str,
        task_type: str,
        content: str,
        status: str = "pending",
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add entry to working memory.

        Args:
            task_id: Unique task identifier
            agent: Agent responsible for task
            task_type: Type of task
            content: Task details
            status: Current status (pending, in_progress, completed)
            dependencies: List of dependent task IDs
            metadata: Additional metadata

        Returns:
            UUID of created memory entry
        """
        collection = self.client.collections.get("WorkingMemory")

        memory_id = collection.data.insert(
            properties={
                "task_id": task_id,
                "timestamp": _now_rfc3339(),
                "agent": agent,
                "task_type": task_type,
                "status": status,
                "content": content,
                "dependencies": dependencies or [],
                "metadata": _serialize_metadata(metadata),
            }
        )

        return str(memory_id)

    def update_working_memory_status(self, task_id: str, status: str) -> bool:
        """
        Update status of working memory task.

        Args:
            task_id: Task identifier
            status: New status

        Returns:
            True if updated successfully
        """
        collection = self.client.collections.get("WorkingMemory")

        # Find task by task_id
        query = collection.query.fetch_objects(limit=1000)

        for obj in query.objects:
            if obj.properties.get("task_id") == task_id:
                collection.data.update(
                    uuid=obj.uuid, properties={"status": status}
                )
                return True

        return False

    def get_working_tasks(
        self, status: Optional[str] = None, agent: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get working memory tasks.

        Args:
            status: Filter by status (optional)
            agent: Filter by agent (optional)

        Returns:
            List of task entries
        """
        collection = self.client.collections.get("WorkingMemory")

        query = collection.query.fetch_objects(limit=100)

        results = []
        for obj in query.objects:
            props = obj.properties
            props["metadata"] = _deserialize_metadata(props.get("metadata"))
            if (status is None or props["status"] == status) and (
                agent is None or props["agent"] == agent
            ):
                results.append({"id": str(obj.uuid), **props})

        return sorted(results, key=lambda x: x["timestamp"], reverse=True)

    def clear_completed_tasks(self) -> int:
        """
        Remove completed tasks from working memory.

        Returns:
            Number of deleted tasks
        """
        collection = self.client.collections.get("WorkingMemory")

        query = collection.query.fetch_objects(limit=1000)

        deleted = 0
        for obj in query.objects:
            if obj.properties.get("status") == "completed":
                collection.data.delete_by_id(obj.uuid)
                deleted += 1

        return deleted

    # === Long-Term Memory Operations ===

    def add_long_term(
        self,
        category: str,
        summary: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add entry to long-term memory.

        Args:
            category: Memory category (learning, preference, fact, etc.)
            summary: Compressed summary
            importance: Importance score (0.0 to 1.0)
            tags: Searchable tags
            metadata: Additional metadata

        Returns:
            UUID of created memory entry
        """
        collection = self.client.collections.get("LongTermMemory")

        memory_id = collection.data.insert(
            properties={
                "timestamp": _now_rfc3339(),
                "category": category,
                "summary": summary,
                "importance": importance,
                "tags": tags or [],
                "metadata": _serialize_metadata(metadata),
            }
        )

        return str(memory_id)

    def search_long_term(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memories.

        Args:
            category: Filter by category (optional)
            tags: Filter by tags (optional)
            min_importance: Minimum importance score
            limit: Maximum number of results

        Returns:
            List of matching memories
        """
        collection = self.client.collections.get("LongTermMemory")

        query = collection.query.fetch_objects(limit=limit * 2)

        results = []
        for obj in query.objects:
            props = obj.properties
            props["metadata"] = _deserialize_metadata(props.get("metadata"))

            # Apply filters
            if category and props["category"] != category:
                continue

            if tags and not any(tag in props.get("tags", []) for tag in tags):
                continue

            if props.get("importance", 0) < min_importance:
                continue

            results.append({"id": str(obj.uuid), **props})

        # Sort by importance and timestamp
        results.sort(
            key=lambda x: (x.get("importance", 0), x.get("timestamp")),
            reverse=True,
        )

        return results[:limit]

    def compress_to_long_term(
        self, short_term_entries: List[Dict[str, Any]], summary: str
    ) -> str:
        """
        Compress multiple short-term memories into one long-term memory.

        Args:
            short_term_entries: List of short-term memories to compress
            summary: Compressed summary

        Returns:
            UUID of created long-term memory
        """
        # Determine importance based on number of entries
        importance = min(len(short_term_entries) / 10.0, 1.0)

        # Extract common tags/themes
        tags = []
        for entry in short_term_entries:
            if "metadata" in entry and "tags" in entry["metadata"]:
                tags.extend(entry["metadata"]["tags"])

        tags = list(set(tags))  # Remove duplicates

        return self.add_long_term(
            category="compressed_history",
            summary=summary,
            importance=importance,
            tags=tags,
            metadata={"source_count": len(short_term_entries)},
        )


# Convenience functions for standalone usage
def add_memory(agent: str, content: str, **kwargs) -> str:
    """Add short-term memory (convenience function)."""
    with MemoryOperations() as mem:
        return mem.add_short_term(agent, content, **kwargs)


def get_recent_memories(hours: int = 24, **kwargs) -> List[Dict[str, Any]]:
    """Get recent memories (convenience function)."""
    with MemoryOperations() as mem:
        return mem.get_recent_short_term(hours, **kwargs)


def add_task(task_id: str, agent: str, task_type: str, content: str, **kwargs) -> str:
    """Add working memory task (convenience function)."""
    with MemoryOperations() as mem:
        return mem.add_working_memory(task_id, agent, task_type, content, **kwargs)
