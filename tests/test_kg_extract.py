"""Unit tests for KG extraction from memory items."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory.kg.extract import (
    USER_ENTITY_ID,
    extract_entities_and_edges,
    _extract_preference_relations,
    _extract_decision_relations,
    _extract_work_relations,
    _extract_project_names,
    _extract_tool_names,
    _extract_file_paths,
)


def test_extract_preference_relations():
    """Test extracting preference relations."""
    content = "I prefer tabs over spaces for Python code"
    memory_id = "mem-123"
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    
    relations = _extract_preference_relations(content, memory_id, timestamp)
    
    assert len(relations) == 1
    subj_id, pred, obj_name, evidence = relations[0]
    assert subj_id == USER_ENTITY_ID
    assert pred == "prefers"
    assert "tabs" in obj_name
    assert evidence["memory_id"] == memory_id


def test_extract_decision_relations():
    """Test extracting decision relations."""
    content = "I decided to use SQLite for the knowledge graph"
    memory_id = "mem-456"
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    
    relations = _extract_decision_relations(content, memory_id, timestamp)
    
    assert len(relations) == 1
    subj_id, pred, obj_name, evidence = relations[0]
    assert subj_id == USER_ENTITY_ID
    assert pred == "decided"
    assert "sqlite" in obj_name.lower()


def test_extract_work_relations():
    """Test extracting work-on relations."""
    content = "I'm working on Milton Knowledge Graph feature"
    memory_id = "mem-789"
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    
    relations = _extract_work_relations(content, memory_id, timestamp)
    
    assert len(relations) == 1
    subj_id, pred, obj_name, evidence = relations[0]
    assert subj_id == USER_ENTITY_ID
    assert pred == "works_on"
    assert "Milton" in obj_name or "Knowledge Graph" in obj_name


def test_extract_project_names():
    """Test extracting project names."""
    content = "Working on Project Milton and the Dashboard project"
    
    projects = _extract_project_names(content)
    
    # Should extract project names (may include extra context)
    assert len(projects) >= 1
    # Check that Milton is in at least one extracted project
    assert any("Milton" in p for p in projects)


def test_extract_tool_names():
    """Test extracting known tool names."""
    content = "Using Python, SQLite, and Docker for the project"
    
    tools = _extract_tool_names(content)
    
    assert len(tools) >= 3
    tool_names_lower = [t.lower() for t in tools]
    assert "python" in tool_names_lower
    assert "sqlite" in tool_names_lower
    assert "docker" in tool_names_lower


def test_extract_file_paths():
    """Test extracting file paths."""
    content = "Check /home/user/config.yaml and ./relative/path.py"
    
    paths = _extract_file_paths(content)
    
    assert len(paths) >= 2
    assert any("/home/user" in p for p in paths)
    assert any("./relative" in p or "relative" in p for p in paths)


def test_extract_entities_and_edges_preference():
    """Test full extraction with preference memory."""
    memory_item = {
        "id": "mem-pref-1",
        "content": "I prefer dark mode for coding",
        "type": "preference",
        "ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "tags": ["ui", "preference"],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should have user entity + preference concept entity
    assert len(entities) >= 2
    
    # Should have at least one edge (user prefers X)
    assert len(edge_specs) >= 1
    
    # Check user entity exists
    user_entities = [e for e in entities if e.id == USER_ENTITY_ID]
    assert len(user_entities) == 1
    
    # Check preference edge
    pref_edges = [e for e in edge_specs if e[1] == "prefers"]
    assert len(pref_edges) >= 1


def test_extract_entities_and_edges_decision():
    """Test full extraction with decision memory."""
    memory_item = {
        "id": "mem-dec-1",
        "content": "Decided to use SQLite for local storage",
        "type": "decision",
        "ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "tags": ["architecture"],
        "agent": "CORTEX",
        "source": "planning"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should have user entity + decision entity + tool entity
    assert len(entities) >= 2
    
    # Should have edges
    assert len(edge_specs) >= 1
    
    # Check for SQLite tool entity
    tool_entities = [e for e in entities if e.type == "tool" and "sqlite" in e.name.lower()]
    assert len(tool_entities) >= 1


def test_extract_entities_and_edges_project():
    """Test full extraction with project/work memory."""
    memory_item = {
        "id": "mem-proj-1",
        "content": "Working on Milton dashboard using React and Python",
        "type": "project",
        "ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "tags": ["project:milton"],
        "agent": "NEXUS",
        "source": "status_update"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should have user, project, and tool entities
    assert len(entities) >= 3
    
    # Check for project entity
    project_entities = [e for e in entities if e.type == "project"]
    assert len(project_entities) >= 1
    
    # Check for tool entities
    tool_entities = [e for e in entities if e.type == "tool"]
    assert len(tool_entities) >= 2  # React and Python
    
    # Should have work relation
    work_edges = [e for e in edge_specs if e[1] == "works_on"]
    assert len(work_edges) >= 1


def test_extract_with_empty_content():
    """Test extraction with empty content."""
    memory_item = {
        "id": "mem-empty",
        "content": "",
        "type": "crumb",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "SYSTEM",
        "source": "test"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should return empty results gracefully
    assert entities == []
    assert edge_specs == []


def test_extract_with_malformed_input():
    """Test extraction handles malformed input gracefully."""
    memory_item = {
        "id": "mem-bad",
        "content": None,  # Invalid content
        "type": "crumb"
    }
    
    # Should not raise exception
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    assert isinstance(entities, list)
    assert isinstance(edge_specs, list)


def test_extract_multiple_patterns():
    """Test extraction with multiple patterns in same content."""
    memory_item = {
        "id": "mem-multi",
        "content": "Working on Project Milton. I prefer Python over JavaScript. Decided to use SQLite.",
        "type": "crumb",
        "ts": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should extract project, tools, preferences, decisions
    assert len(entities) >= 4
    assert len(edge_specs) >= 3
    
    # Check entity types
    entity_types = {e.type for e in entities}
    assert "project" in entity_types
    assert "tool" in entity_types
    
    # Check edge predicates
    predicates = {e[1] for e in edge_specs}
    assert "works_on" in predicates
    assert "prefers" in predicates
    assert "decided" in predicates


def test_extract_file_paths_creates_path_entities():
    """Test that file paths create path entities."""
    memory_item = {
        "id": "mem-path",
        "content": "Modified /home/user/milton/memory/kg/extract.py",
        "type": "crumb",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "SYSTEM",
        "source": "git"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Should have path entities
    path_entities = [e for e in entities if e.type == "path"]
    assert len(path_entities) >= 1
    
    # Should have reference edges
    ref_edges = [e for e in edge_specs if e[1] == "references"]
    assert len(ref_edges) >= 1


def test_user_entity_always_present():
    """Test that user entity is always created."""
    memory_item = {
        "id": "mem-user",
        "content": "Some random content",
        "type": "crumb",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "TEST",
        "source": "test"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # User entity should always be present
    user_entities = [e for e in entities if e.id == USER_ENTITY_ID]
    assert len(user_entities) == 1
    assert user_entities[0].type == "person"
    assert user_entities[0].name == "User"


def test_extract_respects_memory_type():
    """Test that extraction respects memory type for relation patterns."""
    # Preference type should extract preferences
    pref_item = {
        "id": "mem-pref",
        "content": "prefer tabs",
        "type": "preference",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "test"
    }
    
    entities, edge_specs = extract_entities_and_edges(pref_item)
    pref_edges = [e for e in edge_specs if e[1] == "prefers"]
    assert len(pref_edges) >= 1
    
    # Crumb type should NOT extract preferences (pattern won't match)
    crumb_item = {
        "id": "mem-crumb",
        "content": "random crumb",
        "type": "crumb",
        "ts": datetime.now(timezone.utc),
        "tags": [],
        "agent": "NEXUS",
        "source": "test"
    }
    
    entities, edge_specs = extract_entities_and_edges(crumb_item)
    # Should have user entity but no preference edges
    pref_edges = [e for e in edge_specs if e[1] == "prefers"]
    assert len(pref_edges) == 0


def test_edge_evidence_includes_metadata():
    """Test that edge evidence includes memory metadata."""
    memory_item = {
        "id": "mem-evidence",
        "content": "I prefer dark theme",
        "type": "preference",
        "ts": datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
        "tags": ["ui"],
        "agent": "NEXUS",
        "source": "chat"
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_item)
    
    # Check evidence dict
    pref_edges = [e for e in edge_specs if e[1] == "prefers"]
    assert len(pref_edges) >= 1
    
    evidence = pref_edges[0][4]
    assert evidence["memory_id"] == "mem-evidence"
    assert evidence["src"] == "memory"
    assert "timestamp" in evidence
    assert "pattern" in evidence
