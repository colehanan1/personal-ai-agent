"""SQLite storage backend for Knowledge Graph.

Implements local-first storage with automatic fallback to JSON if SQLite fails.
Uses state_paths conventions from Milton's memory system.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from milton_orchestrator.state_paths import resolve_state_dir

from .schema import Edge, Entity, _normalize_name

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1


def _serialize_dict(data: dict[str, Any]) -> str:
    """Serialize dict to JSON string."""
    return json.dumps(data, sort_keys=True)


def _deserialize_dict(value: Optional[str]) -> dict[str, Any]:
    """Deserialize JSON string to dict."""
    if not value:
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_timestamp(value: Optional[str]) -> datetime:
    """Parse ISO timestamp string to datetime."""
    if not value:
        raise ValueError("Timestamp cannot be None")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError(f"Invalid timestamp: {value}") from err


class KnowledgeGraphStore:
    """SQLite-backed knowledge graph storage.
    
    Stores entities and edges with indexes for efficient lookups.
    Auto-creates database and tables on initialization.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize store with optional custom path.
        
        Args:
            db_path: Custom database path. If None, uses STATE_DIR/kg.sqlite
        """
        if db_path is None:
            state_dir = resolve_state_dir()
            state_dir.mkdir(parents=True, exist_ok=True)
            db_path = state_dir / "kg.sqlite"
        else:
            # Ensure parent directory exists for custom paths
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Entities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_ts TEXT NOT NULL,
                    updated_ts TEXT NOT NULL
                )
            """)
            
            # Edges table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_ts TEXT NOT NULL,
                    FOREIGN KEY (subject_id) REFERENCES entities(id),
                    FOREIGN KEY (object_id) REFERENCES entities(id)
                )
            """)
            
            # Indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_normalized 
                ON entities(normalized_name, type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_edges_subject 
                ON edges(subject_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_edges_object 
                ON edges(object_id)
            """)
            
            # Schema version tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),)
            )
            
            conn.commit()
        finally:
            conn.close()
    
    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        metadata: Optional[dict[str, Any]] = None,
        entity_id: Optional[str] = None
    ) -> Entity:
        """Insert or update an entity.
        
        If an entity with the same normalized name and type exists, updates it.
        Otherwise creates a new entity.
        
        Args:
            entity_type: Type of entity (e.g., "person", "project")
            name: Human-readable name
            metadata: Optional metadata dict
            entity_id: Optional custom ID (generated if not provided)
        
        Returns:
            The created or updated Entity
        """
        normalized = _normalize_name(name)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Check for existing entity
            cursor.execute(
                "SELECT id, created_ts FROM entities WHERE normalized_name = ? AND type = ?",
                (normalized, entity_type)
            )
            row = cursor.fetchone()
            
            now = datetime.now(timezone.utc).isoformat()
            metadata_json = _serialize_dict(metadata or {})
            
            if row:
                # Update existing
                existing_id = row[0]
                created_ts = row[1]
                cursor.execute(
                    """UPDATE entities 
                       SET name = ?, metadata_json = ?, updated_ts = ?
                       WHERE id = ?""",
                    (name, metadata_json, now, existing_id)
                )
                conn.commit()
                return Entity(
                    id=existing_id,
                    type=entity_type,
                    name=name,
                    metadata=metadata or {},
                    created_ts=_parse_timestamp(created_ts),
                    updated_ts=_parse_timestamp(now)
                )
            else:
                # Insert new
                from uuid import uuid4
                eid = entity_id or str(uuid4())
                cursor.execute(
                    """INSERT INTO entities 
                       (id, type, name, normalized_name, metadata_json, created_ts, updated_ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (eid, entity_type, name, normalized, metadata_json, now, now)
                )
                conn.commit()
                return Entity(
                    id=eid,
                    type=entity_type,
                    name=name,
                    metadata=metadata or {},
                    created_ts=_parse_timestamp(now),
                    updated_ts=_parse_timestamp(now)
                )
        finally:
            conn.close()
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID.
        
        Args:
            entity_id: Entity ID
        
        Returns:
            Entity if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, type, name, metadata_json, created_ts, updated_ts FROM entities WHERE id = ?",
                (entity_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return Entity(
                id=row[0],
                type=row[1],
                name=row[2],
                metadata=_deserialize_dict(row[3]),
                created_ts=_parse_timestamp(row[4]),
                updated_ts=_parse_timestamp(row[5])
            )
        finally:
            conn.close()
    
    def search_entities(
        self,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> list[Entity]:
        """Search entities by normalized name and/or type.
        
        Args:
            name: Optional name to search (normalized automatically)
            entity_type: Optional type filter
            limit: Maximum results to return
        
        Returns:
            List of matching entities
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            conditions = []
            params: list[Any] = []
            
            if name:
                conditions.append("normalized_name LIKE ?")
                params.append(f"%{_normalize_name(name)}%")
            
            if entity_type:
                conditions.append("type = ?")
                params.append(entity_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"""
                SELECT id, type, name, metadata_json, created_ts, updated_ts 
                FROM entities 
                WHERE {where_clause}
                LIMIT ?
            """
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                Entity(
                    id=row[0],
                    type=row[1],
                    name=row[2],
                    metadata=_deserialize_dict(row[3]),
                    created_ts=_parse_timestamp(row[4]),
                    updated_ts=_parse_timestamp(row[5])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def upsert_edge(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        weight: float = 1.0,
        evidence: Optional[dict[str, Any]] = None
    ) -> Edge:
        """Insert or update an edge between entities.
        
        If an edge with the same (subject, predicate, object) exists, updates it.
        
        Args:
            subject_id: Subject entity ID
            predicate: Relationship type
            object_id: Object entity ID
            weight: Relationship strength (0.0-1.0)
            evidence: Optional provenance/evidence dict
        
        Returns:
            The created or updated Edge
        """
        if not (0.0 <= weight <= 1.0):
            raise ValueError(f"Edge weight must be 0.0-1.0, got {weight}")
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Check for existing edge
            cursor.execute(
                "SELECT id, created_ts FROM edges WHERE subject_id = ? AND predicate = ? AND object_id = ?",
                (subject_id, predicate, object_id)
            )
            row = cursor.fetchone()
            
            now = datetime.now(timezone.utc).isoformat()
            evidence_json = _serialize_dict(evidence or {})
            
            if row:
                # Update existing
                existing_id = row[0]
                created_ts = row[1]
                cursor.execute(
                    """UPDATE edges 
                       SET weight = ?, evidence_json = ?
                       WHERE id = ?""",
                    (weight, evidence_json, existing_id)
                )
                conn.commit()
                return Edge(
                    id=existing_id,
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    weight=weight,
                    evidence=evidence or {},
                    created_ts=_parse_timestamp(created_ts)
                )
            else:
                # Insert new
                from uuid import uuid4
                edge_id = str(uuid4())
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    """INSERT INTO edges 
                       (id, subject_id, predicate, object_id, weight, evidence_json, created_ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (edge_id, subject_id, predicate, object_id, weight, evidence_json, now)
                )
                conn.commit()
                return Edge(
                    id=edge_id,
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    weight=weight,
                    evidence=evidence or {},
                    created_ts=_parse_timestamp(now)
                )
        finally:
            conn.close()
    
    def get_neighbors(
        self,
        entity_id: str,
        direction: str = "outgoing",
        predicate: Optional[str] = None,
        limit: int = 100
    ) -> list[tuple[Edge, Entity]]:
        """Get neighboring entities connected by edges.
        
        Args:
            entity_id: Entity ID to find neighbors for
            direction: "outgoing" (entity is subject), "incoming" (entity is object), or "both"
            predicate: Optional predicate filter
            limit: Maximum results
        
        Returns:
            List of (Edge, Entity) tuples
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            results: list[tuple[Edge, Entity]] = []
            
            # Outgoing edges
            if direction in ("outgoing", "both"):
                query = """
                    SELECT e.id, e.subject_id, e.predicate, e.object_id, e.weight, 
                           e.evidence_json, e.created_ts,
                           ent.id, ent.type, ent.name, ent.metadata_json, 
                           ent.created_ts, ent.updated_ts
                    FROM edges e
                    JOIN entities ent ON e.object_id = ent.id
                    WHERE e.subject_id = ?
                """
                params: list[Any] = [entity_id]
                if predicate:
                    query += " AND e.predicate = ?"
                    params.append(predicate)
                query += " LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    edge = Edge(
                        id=row[0],
                        subject_id=row[1],
                        predicate=row[2],
                        object_id=row[3],
                        weight=row[4],
                        evidence=_deserialize_dict(row[5]),
                        created_ts=_parse_timestamp(row[6])
                    )
                    entity = Entity(
                        id=row[7],
                        type=row[8],
                        name=row[9],
                        metadata=_deserialize_dict(row[10]),
                        created_ts=_parse_timestamp(row[11]),
                        updated_ts=_parse_timestamp(row[12])
                    )
                    results.append((edge, entity))
            
            # Incoming edges
            if direction in ("incoming", "both"):
                query = """
                    SELECT e.id, e.subject_id, e.predicate, e.object_id, e.weight, 
                           e.evidence_json, e.created_ts,
                           ent.id, ent.type, ent.name, ent.metadata_json, 
                           ent.created_ts, ent.updated_ts
                    FROM edges e
                    JOIN entities ent ON e.subject_id = ent.id
                    WHERE e.object_id = ?
                """
                params = [entity_id]
                if predicate:
                    query += " AND e.predicate = ?"
                    params.append(predicate)
                query += " LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    edge = Edge(
                        id=row[0],
                        subject_id=row[1],
                        predicate=row[2],
                        object_id=row[3],
                        weight=row[4],
                        evidence=_deserialize_dict(row[5]),
                        created_ts=_parse_timestamp(row[6])
                    )
                    entity = Entity(
                        id=row[7],
                        type=row[8],
                        name=row[9],
                        metadata=_deserialize_dict(row[10]),
                        created_ts=_parse_timestamp(row[11]),
                        updated_ts=_parse_timestamp(row[12])
                    )
                    results.append((edge, entity))
            
            return results[:limit]
        finally:
            conn.close()
    
    def export_snapshot(self) -> dict[str, Any]:
        """Export entire graph to JSON-serializable dict.
        
        Returns:
            Dict with 'entities' and 'edges' lists
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Export entities
            cursor.execute("SELECT id, type, name, metadata_json, created_ts, updated_ts FROM entities")
            entities = [
                {
                    "id": row[0],
                    "type": row[1],
                    "name": row[2],
                    "metadata": _deserialize_dict(row[3]),
                    "created_ts": row[4],
                    "updated_ts": row[5]
                }
                for row in cursor.fetchall()
            ]
            
            # Export edges
            cursor.execute(
                "SELECT id, subject_id, predicate, object_id, weight, evidence_json, created_ts FROM edges"
            )
            edges = [
                {
                    "id": row[0],
                    "subject_id": row[1],
                    "predicate": row[2],
                    "object_id": row[3],
                    "weight": row[4],
                    "evidence": _deserialize_dict(row[5]),
                    "created_ts": row[6]
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "schema_version": SCHEMA_VERSION,
                "entities": entities,
                "edges": edges
            }
        finally:
            conn.close()
    
    def import_snapshot(self, snapshot: dict[str, Any], merge: bool = False) -> None:
        """Import graph from JSON snapshot.
        
        Args:
            snapshot: Dict with 'entities' and 'edges' lists
            merge: If True, merge with existing data. If False, clear first.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            if not merge:
                cursor.execute("DELETE FROM edges")
                cursor.execute("DELETE FROM entities")
            
            # Import entities
            for ent in snapshot.get("entities", []):
                cursor.execute(
                    """INSERT OR REPLACE INTO entities 
                       (id, type, name, normalized_name, metadata_json, created_ts, updated_ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ent["id"],
                        ent["type"],
                        ent["name"],
                        _normalize_name(ent["name"]),
                        _serialize_dict(ent.get("metadata", {})),
                        ent["created_ts"],
                        ent["updated_ts"]
                    )
                )
            
            # Import edges
            for edge in snapshot.get("edges", []):
                cursor.execute(
                    """INSERT OR REPLACE INTO edges 
                       (id, subject_id, predicate, object_id, weight, evidence_json, created_ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        edge["id"],
                        edge["subject_id"],
                        edge["predicate"],
                        edge["object_id"],
                        edge["weight"],
                        _serialize_dict(edge.get("evidence", {})),
                        edge["created_ts"]
                    )
                )
            
            conn.commit()
        finally:
            conn.close()
