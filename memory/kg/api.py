"""Public API for Knowledge Graph operations.

Simple, clean interface for creating and querying the personalized knowledge graph.
All functions work locally without requiring Weaviate or other services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .schema import Edge, Entity
from .store import KnowledgeGraphStore

# Module-level store instance (lazily initialized)
_store: Optional[KnowledgeGraphStore] = None


def _get_store(db_path: Optional[Path] = None) -> KnowledgeGraphStore:
    """Get or create the module-level store instance."""
    global _store
    if _store is None or db_path is not None:
        _store = KnowledgeGraphStore(db_path=db_path)
    return _store


def upsert_entity(
    type: str,
    name: str,
    metadata: Optional[dict[str, Any]] = None,
    entity_id: Optional[str] = None,
    db_path: Optional[Path] = None
) -> str:
    """Create or update an entity in the knowledge graph.
    
    Args:
        type: Entity type (e.g., "person", "project", "concept")
        name: Human-readable name
        metadata: Optional metadata dict
        entity_id: Optional custom ID
        db_path: Optional custom database path (for testing)
    
    Returns:
        Entity ID (new or existing)
    
    Example:
        >>> entity_id = upsert_entity(type="project", name="Milton")
        >>> entity_id = upsert_entity(
        ...     type="person", 
        ...     name="Cole", 
        ...     metadata={"role": "user"}
        ... )
    """
    store = _get_store(db_path)
    entity = store.upsert_entity(
        entity_type=type,
        name=name,
        metadata=metadata,
        entity_id=entity_id
    )
    return entity.id


def get_entity(entity_id: str, db_path: Optional[Path] = None) -> Optional[Entity]:
    """Get an entity by ID.
    
    Args:
        entity_id: Entity ID
        db_path: Optional custom database path (for testing)
    
    Returns:
        Entity if found, None otherwise
    """
    store = _get_store(db_path)
    return store.get_entity(entity_id)


def search_entities(
    name: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None
) -> list[Entity]:
    """Search for entities by name and/or type.
    
    Args:
        name: Optional name to search (partial match, case-insensitive)
        type: Optional type filter
        limit: Maximum results
        db_path: Optional custom database path (for testing)
    
    Returns:
        List of matching entities
    
    Example:
        >>> projects = search_entities(type="project")
        >>> milton_entities = search_entities(name="milton")
    """
    store = _get_store(db_path)
    return store.search_entities(name=name, entity_type=type, limit=limit)


def upsert_edge(
    subject_id: str,
    predicate: str,
    object_id: str,
    weight: float = 1.0,
    evidence: Optional[dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> str:
    """Create or update an edge (relationship) between entities.
    
    Args:
        subject_id: Subject entity ID
        predicate: Relationship type (e.g., "uses", "knows", "works_on")
        object_id: Object entity ID
        weight: Relationship strength (0.0-1.0)
        evidence: Optional provenance/evidence dict
        db_path: Optional custom database path (for testing)
    
    Returns:
        Edge ID (new or existing)
    
    Example:
        >>> milton_id = upsert_entity(type="project", name="Milton")
        >>> kg_id = upsert_entity(type="concept", name="Knowledge Graph")
        >>> edge_id = upsert_edge(
        ...     milton_id, 
        ...     "uses", 
        ...     kg_id, 
        ...     weight=0.9,
        ...     evidence={"src": "manual"}
        ... )
    """
    store = _get_store(db_path)
    edge = store.upsert_edge(
        subject_id=subject_id,
        predicate=predicate,
        object_id=object_id,
        weight=weight,
        evidence=evidence
    )
    return edge.id


def neighbors(
    entity_id: str,
    direction: str = "outgoing",
    predicate: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None
) -> list[tuple[Edge, Entity]]:
    """Get neighboring entities connected by edges.
    
    Args:
        entity_id: Entity ID to find neighbors for
        direction: "outgoing" (entity is subject), "incoming" (entity is object), or "both"
        predicate: Optional predicate filter
        limit: Maximum results
        db_path: Optional custom database path (for testing)
    
    Returns:
        List of (Edge, Entity) tuples representing connected entities
    
    Example:
        >>> milton_id = upsert_entity(type="project", name="Milton")
        >>> for edge, entity in neighbors(milton_id):
        ...     print(f"{edge.predicate} -> {entity.name}")
    """
    store = _get_store(db_path)
    return store.get_neighbors(
        entity_id=entity_id,
        direction=direction,
        predicate=predicate,
        limit=limit
    )


def export_snapshot(db_path: Optional[Path] = None) -> dict[str, Any]:
    """Export entire graph to JSON-serializable dict.
    
    Args:
        db_path: Optional custom database path (for testing)
    
    Returns:
        Dict with 'entities' and 'edges' lists
    
    Example:
        >>> snapshot = export_snapshot()
        >>> import json
        >>> with open("kg_backup.json", "w") as f:
        ...     json.dump(snapshot, f, indent=2)
    """
    store = _get_store(db_path)
    return store.export_snapshot()


def import_snapshot(
    snapshot: dict[str, Any],
    merge: bool = False,
    db_path: Optional[Path] = None
) -> None:
    """Import graph from JSON snapshot.
    
    Args:
        snapshot: Dict with 'entities' and 'edges' lists
        merge: If True, merge with existing data. If False, clear first.
        db_path: Optional custom database path (for testing)
    
    Example:
        >>> import json
        >>> with open("kg_backup.json") as f:
        ...     snapshot = json.load(f)
        >>> import_snapshot(snapshot, merge=True)
    """
    store = _get_store(db_path)
    store.import_snapshot(snapshot, merge=merge)
