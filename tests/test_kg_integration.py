"""Integration test for Knowledge Graph without Weaviate.

Verifies KG works independently of Weaviate and other memory backends.
"""

import os
from pathlib import Path

import pytest

from memory.kg import (
    export_snapshot,
    neighbors,
    search_entities,
    upsert_edge,
    upsert_entity,
)


def test_kg_works_without_weaviate(tmp_path: Path, monkeypatch):
    """Verify KG operates independently of Weaviate."""
    # Force JSONL memory backend (no Weaviate)
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    monkeypatch.delenv("WEAVIATE_URL", raising=False)
    
    db_path = tmp_path / "kg.db"
    
    # Create a small knowledge graph
    milton_id = upsert_entity(
        type="project",
        name="Milton",
        metadata={"status": "active"},
        db_path=db_path
    )
    
    kg_id = upsert_entity(
        type="concept",
        name="Knowledge Graph",
        db_path=db_path
    )
    
    sqlite_id = upsert_entity(
        type="tool",
        name="SQLite",
        db_path=db_path
    )
    
    # Create relationships
    upsert_edge(
        milton_id,
        "implements",
        kg_id,
        weight=0.9,
        db_path=db_path
    )
    
    upsert_edge(
        milton_id,
        "uses",
        sqlite_id,
        weight=1.0,
        db_path=db_path
    )
    
    # Verify queries work
    results = neighbors(milton_id, db_path=db_path)
    assert len(results) == 2
    
    neighbor_names = {entity.name for edge, entity in results}
    assert "Knowledge Graph" in neighbor_names
    assert "SQLite" in neighbor_names
    
    # Verify search works
    projects = search_entities(type="project", db_path=db_path)
    assert len(projects) == 1
    assert projects[0].name == "Milton"
    
    # Verify export works
    snapshot = export_snapshot(db_path=db_path)
    assert len(snapshot["entities"]) == 3
    assert len(snapshot["edges"]) == 2


def test_kg_auto_creates_directory(tmp_path: Path):
    """Verify KG auto-creates database directory if missing."""
    # Use explicit db_path to test directory creation
    custom_dir = tmp_path / "custom_state"
    db_path = custom_dir / "kg.sqlite"
    
    assert not custom_dir.exists()
    
    # This should create the directory when store is initialized
    entity_id = upsert_entity(type="test", name="test", db_path=db_path)
    
    # Directory and database should now exist
    assert custom_dir.exists()
    assert db_path.exists()


def test_kg_persists_across_sessions(tmp_path: Path):
    """Verify data persists across store instances."""
    db_path = tmp_path / "persistent.db"
    
    # Session 1: Create data
    entity_id = upsert_entity(
        type="project",
        name="Persistent Project",
        db_path=db_path
    )
    
    # Session 2: Read data (simulated by not passing store instance)
    from memory.kg.api import _get_store
    from memory.kg import api as kg_api
    
    # Reset module-level store
    kg_api._store = None
    
    # Should read existing data from same db_path
    entities = search_entities(name="persistent", db_path=db_path)
    assert len(entities) == 1
    assert entities[0].id == entity_id
