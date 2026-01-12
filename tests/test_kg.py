"""Unit tests for Knowledge Graph module.

Tests storage, querying, and snapshot operations without requiring Weaviate.
"""

from pathlib import Path

import pytest

from memory.kg import (
    Entity,
    export_snapshot,
    get_entity,
    import_snapshot,
    neighbors,
    search_entities,
    upsert_edge,
    upsert_entity,
)


def test_upsert_entity_creates_new(tmp_path: Path):
    """Test creating a new entity."""
    db_path = tmp_path / "test.db"
    
    entity_id = upsert_entity(
        type="project",
        name="Milton",
        metadata={"description": "AI assistant"},
        db_path=db_path
    )
    
    assert entity_id is not None
    entity = get_entity(entity_id, db_path=db_path)
    assert entity is not None
    assert entity.type == "project"
    assert entity.name == "Milton"
    assert entity.metadata["description"] == "AI assistant"
    assert entity.normalized_name == "milton"


def test_upsert_entity_updates_existing(tmp_path: Path):
    """Test updating an existing entity by normalized name + type."""
    db_path = tmp_path / "test.db"
    
    # Create entity
    id1 = upsert_entity(
        type="person",
        name="Cole",
        metadata={"version": 1},
        db_path=db_path
    )
    
    # Upsert with same normalized name + type should update
    id2 = upsert_entity(
        type="person",
        name="COLE",  # Different case
        metadata={"version": 2},
        db_path=db_path
    )
    
    # Should return same ID
    assert id1 == id2
    
    entity = get_entity(id1, db_path=db_path)
    assert entity is not None
    assert entity.name == "COLE"  # Updated name
    assert entity.metadata["version"] == 2  # Updated metadata


def test_search_entities_by_name(tmp_path: Path):
    """Test searching entities by partial name match."""
    db_path = tmp_path / "test.db"
    
    upsert_entity(type="project", name="Milton", db_path=db_path)
    upsert_entity(type="project", name="Milton Gateway", db_path=db_path)
    upsert_entity(type="project", name="Dashboard", db_path=db_path)
    
    # Search by partial name (case-insensitive)
    results = search_entities(name="milt", db_path=db_path)
    assert len(results) == 2
    names = {e.name for e in results}
    assert "Milton" in names
    assert "Milton Gateway" in names


def test_search_entities_by_type(tmp_path: Path):
    """Test searching entities by type."""
    db_path = tmp_path / "test.db"
    
    upsert_entity(type="project", name="Milton", db_path=db_path)
    upsert_entity(type="person", name="Cole", db_path=db_path)
    upsert_entity(type="concept", name="Knowledge Graph", db_path=db_path)
    
    results = search_entities(type="project", db_path=db_path)
    assert len(results) == 1
    assert results[0].name == "Milton"


def test_search_entities_by_name_and_type(tmp_path: Path):
    """Test searching entities by both name and type."""
    db_path = tmp_path / "test.db"
    
    upsert_entity(type="project", name="Milton", db_path=db_path)
    upsert_entity(type="concept", name="Milton Architecture", db_path=db_path)
    
    results = search_entities(name="milton", type="project", db_path=db_path)
    assert len(results) == 1
    assert results[0].type == "project"


def test_upsert_edge_creates_new(tmp_path: Path):
    """Test creating a new edge."""
    db_path = tmp_path / "test.db"
    
    subject_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    object_id = upsert_entity(type="concept", name="Knowledge Graph", db_path=db_path)
    
    edge_id = upsert_edge(
        subject_id=subject_id,
        predicate="uses",
        object_id=object_id,
        weight=0.9,
        evidence={"src": "manual", "confidence": "high"},
        db_path=db_path
    )
    
    assert edge_id is not None


def test_upsert_edge_updates_existing(tmp_path: Path):
    """Test updating an existing edge."""
    db_path = tmp_path / "test.db"
    
    subject_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    object_id = upsert_entity(type="concept", name="AI", db_path=db_path)
    
    # Create edge
    edge_id1 = upsert_edge(
        subject_id=subject_id,
        predicate="implements",
        object_id=object_id,
        weight=0.5,
        db_path=db_path
    )
    
    # Update with same triple
    edge_id2 = upsert_edge(
        subject_id=subject_id,
        predicate="implements",
        object_id=object_id,
        weight=0.9,
        evidence={"updated": True},
        db_path=db_path
    )
    
    # Should be same edge
    assert edge_id1 == edge_id2


def test_upsert_edge_validates_weight(tmp_path: Path):
    """Test edge weight validation."""
    db_path = tmp_path / "test.db"
    
    subject_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    object_id = upsert_entity(type="concept", name="AI", db_path=db_path)
    
    # Invalid weight should raise
    with pytest.raises(ValueError, match="weight must be 0.0-1.0"):
        upsert_edge(
            subject_id=subject_id,
            predicate="uses",
            object_id=object_id,
            weight=1.5,
            db_path=db_path
        )


def test_neighbors_outgoing(tmp_path: Path):
    """Test querying outgoing neighbors."""
    db_path = tmp_path / "test.db"
    
    # Create graph: Milton -> uses -> (KG, SQLite)
    milton_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    kg_id = upsert_entity(type="concept", name="Knowledge Graph", db_path=db_path)
    sqlite_id = upsert_entity(type="tool", name="SQLite", db_path=db_path)
    
    upsert_edge(milton_id, "uses", kg_id, weight=0.9, db_path=db_path)
    upsert_edge(milton_id, "uses", sqlite_id, weight=0.8, db_path=db_path)
    
    # Query neighbors
    results = neighbors(milton_id, direction="outgoing", db_path=db_path)
    
    assert len(results) == 2
    neighbor_names = {entity.name for edge, entity in results}
    assert "Knowledge Graph" in neighbor_names
    assert "SQLite" in neighbor_names


def test_neighbors_incoming(tmp_path: Path):
    """Test querying incoming neighbors."""
    db_path = tmp_path / "test.db"
    
    # Create graph: Cole -> works_on -> Milton
    cole_id = upsert_entity(type="person", name="Cole", db_path=db_path)
    milton_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    
    upsert_edge(cole_id, "works_on", milton_id, db_path=db_path)
    
    # Query incoming neighbors of Milton
    results = neighbors(milton_id, direction="incoming", db_path=db_path)
    
    assert len(results) == 1
    edge, entity = results[0]
    assert entity.name == "Cole"
    assert edge.predicate == "works_on"


def test_neighbors_both_directions(tmp_path: Path):
    """Test querying neighbors in both directions."""
    db_path = tmp_path / "test.db"
    
    # Create graph: A -> rel1 -> B -> rel2 -> C
    a_id = upsert_entity(type="concept", name="A", db_path=db_path)
    b_id = upsert_entity(type="concept", name="B", db_path=db_path)
    c_id = upsert_entity(type="concept", name="C", db_path=db_path)
    
    upsert_edge(a_id, "rel1", b_id, db_path=db_path)
    upsert_edge(b_id, "rel2", c_id, db_path=db_path)
    
    # B has 1 incoming (A) and 1 outgoing (C)
    results = neighbors(b_id, direction="both", db_path=db_path)
    
    assert len(results) == 2
    neighbor_names = {entity.name for edge, entity in results}
    assert "A" in neighbor_names
    assert "C" in neighbor_names


def test_neighbors_filtered_by_predicate(tmp_path: Path):
    """Test filtering neighbors by predicate."""
    db_path = tmp_path / "test.db"
    
    milton_id = upsert_entity(type="project", name="Milton", db_path=db_path)
    kg_id = upsert_entity(type="concept", name="Knowledge Graph", db_path=db_path)
    sqlite_id = upsert_entity(type="tool", name="SQLite", db_path=db_path)
    
    upsert_edge(milton_id, "uses", sqlite_id, db_path=db_path)
    upsert_edge(milton_id, "implements", kg_id, db_path=db_path)
    
    # Filter by predicate
    results = neighbors(milton_id, predicate="uses", db_path=db_path)
    
    assert len(results) == 1
    edge, entity = results[0]
    assert entity.name == "SQLite"
    assert edge.predicate == "uses"


def test_export_import_snapshot_roundtrip(tmp_path: Path):
    """Test export and import of graph snapshot."""
    db_path = tmp_path / "test.db"
    
    # Create a small graph
    milton_id = upsert_entity(
        type="project",
        name="Milton",
        metadata={"active": True},
        db_path=db_path
    )
    kg_id = upsert_entity(
        type="concept",
        name="Knowledge Graph",
        db_path=db_path
    )
    upsert_edge(
        milton_id,
        "uses",
        kg_id,
        weight=0.9,
        evidence={"src": "manual"},
        db_path=db_path
    )
    
    # Export
    snapshot = export_snapshot(db_path=db_path)
    
    assert "entities" in snapshot
    assert "edges" in snapshot
    assert len(snapshot["entities"]) == 2
    assert len(snapshot["edges"]) == 1
    
    # Import to new database
    new_db_path = tmp_path / "imported.db"
    import_snapshot(snapshot, merge=False, db_path=new_db_path)
    
    # Verify imported data
    entities = search_entities(db_path=new_db_path)
    assert len(entities) == 2
    
    entity_names = {e.name for e in entities}
    assert "Milton" in entity_names
    assert "Knowledge Graph" in entity_names


def test_import_snapshot_merge(tmp_path: Path):
    """Test merging imported snapshot with existing data."""
    db_path = tmp_path / "test.db"
    
    # Create initial entity
    upsert_entity(type="project", name="Existing", db_path=db_path)
    
    # Create snapshot to import
    snapshot = {
        "schema_version": 1,
        "entities": [
            {
                "id": "new-1",
                "type": "project",
                "name": "New Project",
                "metadata": {},
                "created_ts": "2025-01-01T00:00:00+00:00",
                "updated_ts": "2025-01-01T00:00:00+00:00"
            }
        ],
        "edges": []
    }
    
    # Import with merge=True
    import_snapshot(snapshot, merge=True, db_path=db_path)
    
    # Both entities should exist
    entities = search_entities(db_path=db_path)
    assert len(entities) == 2
    entity_names = {e.name for e in entities}
    assert "Existing" in entity_names
    assert "New Project" in entity_names


def test_import_snapshot_replace(tmp_path: Path):
    """Test replacing existing data with imported snapshot."""
    db_path = tmp_path / "test.db"
    
    # Create initial entity
    upsert_entity(type="project", name="Old", db_path=db_path)
    
    # Create snapshot to import
    snapshot = {
        "schema_version": 1,
        "entities": [
            {
                "id": "new-1",
                "type": "project",
                "name": "New",
                "metadata": {},
                "created_ts": "2025-01-01T00:00:00+00:00",
                "updated_ts": "2025-01-01T00:00:00+00:00"
            }
        ],
        "edges": []
    }
    
    # Import with merge=False (replace)
    import_snapshot(snapshot, merge=False, db_path=db_path)
    
    # Only new entity should exist
    entities = search_entities(db_path=db_path)
    assert len(entities) == 1
    assert entities[0].name == "New"


def test_entity_normalized_name_consistency(tmp_path: Path):
    """Test that normalized names work consistently."""
    db_path = tmp_path / "test.db"
    
    # Create entity with mixed case
    id1 = upsert_entity(type="project", name="Knowledge Graph", db_path=db_path)
    
    # Try to create with different case
    id2 = upsert_entity(type="project", name="KNOWLEDGE GRAPH", db_path=db_path)
    
    # Should be same entity
    assert id1 == id2
    
    # Search should find it regardless of case
    results = search_entities(name="KnOwLeDgE gRaPh", db_path=db_path)
    assert len(results) == 1


def test_get_entity_not_found(tmp_path: Path):
    """Test getting non-existent entity returns None."""
    db_path = tmp_path / "test.db"
    
    entity = get_entity("non-existent-id", db_path=db_path)
    assert entity is None


def test_empty_graph_operations(tmp_path: Path):
    """Test operations on empty graph."""
    db_path = tmp_path / "test.db"
    
    # Search in empty graph
    results = search_entities(db_path=db_path)
    assert len(results) == 0
    
    # Get non-existent entity
    entity = get_entity("does-not-exist", db_path=db_path)
    assert entity is None
    
    # Export empty graph
    snapshot = export_snapshot(db_path=db_path)
    assert snapshot["entities"] == []
    assert snapshot["edges"] == []


def test_multiple_predicates_same_entities(tmp_path: Path):
    """Test multiple relationships between same entities."""
    db_path = tmp_path / "test.db"
    
    a_id = upsert_entity(type="person", name="Alice", db_path=db_path)
    b_id = upsert_entity(type="project", name="Project", db_path=db_path)
    
    # Create multiple different relationships
    upsert_edge(a_id, "works_on", b_id, db_path=db_path)
    upsert_edge(a_id, "owns", b_id, db_path=db_path)
    
    results = neighbors(a_id, direction="outgoing", db_path=db_path)
    
    # Should have 2 edges to same entity
    assert len(results) == 2
    predicates = {edge.predicate for edge, entity in results}
    assert "works_on" in predicates
    assert "owns" in predicates
