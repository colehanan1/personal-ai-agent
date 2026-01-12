"""Personalized Knowledge Graph module for Milton.

A minimal, local-first knowledge graph for storing entities (people, projects, 
concepts, tools) and their relationships. Designed to be independent of Weaviate 
and other memory tiers.

Storage:
- Primary: SQLite database in STATE_DIR/kg.sqlite
- Auto-creates database and tables on first use
- Supports export/import to JSON for portability

Usage:
    >>> from memory.kg import upsert_entity, upsert_edge, neighbors
    >>> 
    >>> # Create entities
    >>> milton_id = upsert_entity(type="project", name="Milton")
    >>> kg_id = upsert_entity(type="concept", name="Knowledge Graph")
    >>> 
    >>> # Create relationship
    >>> upsert_edge(milton_id, "uses", kg_id, weight=0.9)
    >>> 
    >>> # Query neighbors
    >>> for edge, entity in neighbors(milton_id):
    ...     print(f"{edge.predicate} -> {entity.name}")
"""

from .api import (
    export_snapshot,
    get_entity,
    import_snapshot,
    neighbors,
    search_entities,
    upsert_edge,
    upsert_entity,
)
from .schema import Edge, Entity

__all__ = [
    "Entity",
    "Edge",
    "upsert_entity",
    "get_entity",
    "search_entities",
    "upsert_edge",
    "neighbors",
    "export_snapshot",
    "import_snapshot",
]
