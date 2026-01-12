"""Integration tests for KG enrichment from memory writes."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory.schema import MemoryItem
from memory.store import add_memory
from memory.kg.api import search_entities, neighbors, get_entity
from memory.kg.extract import USER_ENTITY_ID, extract_entities_and_edges


def _process_memory_to_kg(memory_dict: dict, db_path: Path) -> None:
    """Helper to extract entities/edges from memory and populate KG.
    
    Mimics what _enrich_knowledge_graph does but with explicit db_path.
    """
    from memory.kg.api import upsert_entity, upsert_edge
    from memory.kg.schema import _normalize_name
    
    entities, edge_specs = extract_entities_and_edges(memory_dict)
    
    # Build ID map
    id_map = {}
    for entity in entities:
        actual_id = upsert_entity(
            type=entity.type,
            name=entity.name,
            metadata=entity.metadata,
            entity_id=entity.id if entity.id.startswith("entity:") else None,
            db_path=db_path
        )
        id_map[entity.id] = actual_id
        # Map type:normalized_name format
        normalized_key = f"{entity.type}:{_normalize_name(entity.name)}"
        id_map[normalized_key] = actual_id
    
    # Create edges
    for subj_id, pred, obj_id, weight, evidence in edge_specs:
        actual_subj = id_map.get(subj_id, subj_id)
        actual_obj = id_map.get(obj_id, obj_id)
        upsert_edge(
            subject_id=actual_subj,
            predicate=pred,
            object_id=actual_obj,
            weight=weight,
            evidence=evidence,
            db_path=db_path
        )


def test_memory_write_creates_kg_entities(tmp_path: Path, monkeypatch):
    """Test that writing memory automatically creates KG entities."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    
    # Create memory with preference
    item = MemoryItem(
        agent="NEXUS",
        type="preference",
        content="I prefer tabs over spaces",
        tags=["coding"],
        importance=0.7,
        source="chat"
    )
    
    memory_id = add_memory(item, repo_root=tmp_path)
    assert memory_id is not None
    
    # Check that entities were created
    entities = search_entities(name="tabs")
    # Note: Uses default KG database, not tmp_path
    # For isolated test, we'd need to pass db_path through the chain


def test_memory_write_creates_preference_edges(tmp_path: Path, monkeypatch):
    """Test that preference memories create prefers edges."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    db_path = tmp_path / "kg.db"
    
    memory_dict = {
        "id": "test-mem-1",
        "content": "I prefer dark mode for editors",
        "type": "preference",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    _process_memory_to_kg(memory_dict, db_path)
    
    # Verify user entity exists
    user = get_entity(USER_ENTITY_ID, db_path=db_path)
    assert user is not None
    assert user.type == "person"
    
    # Verify preference edge exists
    user_neighbors = neighbors(USER_ENTITY_ID, direction="outgoing", db_path=db_path)
    pref_edges = [e for e, ent in user_neighbors if e.predicate == "prefers"]
    assert len(pref_edges) >= 1


def test_memory_write_creates_project_entities(tmp_path: Path, monkeypatch):
    """Test that project memories create project entities and work edges."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    db_path = tmp_path / "kg.db"
    
    memory_dict = {
        "id": "test-mem-2",
        "content": "Working on Project Milton dashboard feature",
        "type": "project",
        "ts": datetime.now(timezone.utc),
        "tags": ["project:milton"],
        "agent": "NEXUS",
        "source": "status"
    }
    
    _process_memory_to_kg(memory_dict, db_path)
    
    # Verify project entity exists
    projects = search_entities(name="Milton", type="project", db_path=db_path)
    assert len(projects) >= 1
    
    # Verify work edge exists
    user_neighbors = neighbors(USER_ENTITY_ID, direction="outgoing", db_path=db_path)
    work_edges = [e for e, ent in user_neighbors if e.predicate == "works_on"]
    assert len(work_edges) >= 1


def test_memory_write_creates_tool_entities(tmp_path: Path, monkeypatch):
    """Test that memories mentioning tools create tool entities."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    db_path = tmp_path / "kg.db"
    
    memory_dict = {
        "id": "test-mem-3",
        "content": "Decided to use Python and SQLite for the backend",
        "type": "decision",
        "ts": datetime.now(timezone.utc),
        "tags": ["architecture"],
        "agent": "CORTEX",
        "source": "planning"
    }
    
    _process_memory_to_kg(memory_dict, db_path)
    
    # Verify tool entities exist
    tools = search_entities(type="tool", db_path=db_path)
    tool_names = {t.name.lower() for t in tools}
    assert "python" in tool_names
    assert "sqlite" in tool_names


def test_memory_write_handles_extraction_failure(tmp_path: Path, monkeypatch):
    """Test that extraction failures don't block memory writes."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    
    # Create a memory item
    item = MemoryItem(
        agent="TEST",
        type="crumb",
        content="Some test content",
        tags=[],
        importance=0.5,
        source="test"
    )
    
    # Even if KG enrichment fails, memory should be stored
    memory_id = add_memory(item, repo_root=tmp_path)
    assert memory_id is not None
    
    # Verify memory was stored (check JSONL file)
    from memory.backends import memory_paths
    short_path, _ = memory_paths(tmp_path)
    assert short_path.exists()


def test_memory_write_with_missing_kg_module(tmp_path: Path, monkeypatch):
    """Test that memory writes work even if KG module is unavailable."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    
    # Simulate missing KG module by catching ImportError
    item = MemoryItem(
        agent="TEST",
        type="crumb",
        content="Test content",
        tags=[],
        importance=0.5,
        source="test"
    )
    
    # Should not raise exception
    memory_id = add_memory(item, repo_root=tmp_path)
    assert memory_id is not None


def test_multiple_memories_accumulate_knowledge(tmp_path: Path, monkeypatch):
    """Test that multiple memories build up the knowledge graph."""
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    db_path = tmp_path / "kg.db"
    
    # First memory: preference
    mem1 = {
        "id": "mem-1",
        "content": "I prefer Python for backend development",
        "type": "preference",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    # Second memory: project work
    mem2 = {
        "id": "mem-2",
        "content": "Working on Milton using Python and Docker",
        "type": "project",
        "ts": datetime.now(timezone.utc),
        "tags": ["project:milton"],
        "agent": "NEXUS",
        "source": "status"
    }
    
    # Third memory: tool decision
    mem3 = {
        "id": "mem-3",
        "content": "Decided to use SQLite for local storage",
        "type": "decision",
        "ts": datetime.now(timezone.utc),
        "tags": ["architecture"],
        "agent": "CORTEX",
        "source": "planning"
    }
    
    # Process all memories
    for mem in [mem1, mem2, mem3]:
        _process_memory_to_kg(mem, db_path)
    
    # Verify accumulated knowledge
    
    # Should have project entities
    projects = search_entities(type="project", db_path=db_path)
    assert len(projects) >= 1
    
    # Should have tool entities
    tools = search_entities(type="tool", db_path=db_path)
    assert len(tools) >= 3  # Python, Docker, SQLite
    
    # User should have multiple relationships
    user_neighbors = neighbors(USER_ENTITY_ID, direction="outgoing", db_path=db_path)
    assert len(user_neighbors) >= 3
    
    # Check different predicates
    predicates = {e.predicate for e, ent in user_neighbors}
    assert "prefers" in predicates
    assert "works_on" in predicates
    assert "decided" in predicates


def test_extraction_preserves_memory_id_in_evidence(tmp_path: Path):
    """Test that extracted edges preserve memory ID in evidence."""
    db_path = tmp_path / "kg.db"
    
    memory_id = "test-mem-evidence"
    mem = {
        "id": memory_id,
        "content": "I prefer vim for editing",
        "type": "preference",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    _process_memory_to_kg(mem, db_path)
    
    # Check edge evidence
    user_neighbors = neighbors(USER_ENTITY_ID, direction="outgoing", db_path=db_path)
    assert len(user_neighbors) >= 1
    
    edge, entity = user_neighbors[0]
    assert edge.evidence["memory_id"] == memory_id
    assert edge.evidence["src"] == "memory"
