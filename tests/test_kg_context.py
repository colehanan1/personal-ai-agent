"""Tests for KG context injection into NEXUS."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.kg_context import (
    KGContextPacket,
    _get_max_chars,
    _get_max_edges,
    _is_kg_enabled,
    build_kg_context,
)


class TestKGContextPacket:
    """Test KGContextPacket formatting."""

    def test_empty_packet(self):
        """Empty packet should return empty string."""
        packet = KGContextPacket()
        assert packet.is_empty()
        assert packet.to_prompt_section() == ""

    def test_entities_only(self):
        """Packet with only entities."""
        packet = KGContextPacket(
            entities=[("Python", "tool"), ("Milton", "project")],
            relationships=[],
            total_entities=2,
            total_edges=0,
        )
        prompt = packet.to_prompt_section()
        assert "**Knowledge Graph Context:**" in prompt
        assert "Entities (2/2):" in prompt
        assert "- Python (tool)" in prompt
        assert "- Milton (project)" in prompt
        assert "Relationships" not in prompt

    def test_relationships_only(self):
        """Packet with only relationships."""
        packet = KGContextPacket(
            entities=[],
            relationships=[
                ("Milton", "uses", "Python", "mem-123"),
                ("User", "works_on", "Milton", ""),
            ],
            total_entities=0,
            total_edges=2,
        )
        prompt = packet.to_prompt_section()
        assert "**Knowledge Graph Context:**" in prompt
        assert "Relationships (2/2):" in prompt
        assert "- Milton --uses--> Python [evidence: mem-123]" in prompt
        assert "- User --works_on--> Milton" in prompt
        assert "Entities" not in prompt

    def test_full_packet(self):
        """Packet with both entities and relationships."""
        packet = KGContextPacket(
            entities=[("FastAPI", "tool"), ("microservices", "concept")],
            relationships=[("FastAPI", "enables", "microservices", "mem-456")],
            total_entities=2,
            total_edges=1,
        )
        prompt = packet.to_prompt_section()
        assert "Entities (2/2):" in prompt
        assert "Relationships (1/1):" in prompt
        assert "- FastAPI (tool)" in prompt
        assert "- FastAPI --enables--> microservices [evidence: mem-456]" in prompt

    def test_entity_cap(self):
        """Should cap entities at 10."""
        entities = [(f"entity{i}", "concept") for i in range(20)]
        packet = KGContextPacket(
            entities=entities,
            relationships=[],
            total_entities=20,
            total_edges=0,
        )
        prompt = packet.to_prompt_section()
        # Should show 10/20
        assert "Entities (10/20):" in prompt
        # Should only have 10 entities in output
        assert prompt.count("  - entity") == 10

    def test_relationship_cap(self):
        """Should cap relationships at 20."""
        relationships = [
            (f"subj{i}", "relates_to", f"obj{i}", "") for i in range(30)
        ]
        packet = KGContextPacket(
            entities=[],
            relationships=relationships,
            total_entities=0,
            total_edges=30,
        )
        prompt = packet.to_prompt_section()
        # Should show 20/30
        assert "Relationships (20/30):" in prompt
        # Should only have 20 relationships in output
        assert prompt.count("  - subj") == 20


class TestEnvFlags:
    """Test environment flag configuration."""

    def test_kg_enabled_by_default(self):
        """KG context should be enabled by default."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MILTON_KG_CONTEXT_ENABLED", None)
            assert _is_kg_enabled()

    def test_kg_can_be_disabled(self):
        """KG context can be disabled via env flag."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_ENABLED": "false"}):
            assert not _is_kg_enabled()

    def test_max_edges_default(self):
        """Default max edges should be 20."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MILTON_KG_CONTEXT_MAX_EDGES", None)
            assert _get_max_edges() == 20

    def test_max_edges_custom(self):
        """Can set custom max edges."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_MAX_EDGES": "10"}):
            assert _get_max_edges() == 10

    def test_max_chars_default(self):
        """Default max chars should be 1500."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MILTON_KG_CONTEXT_MAX_CHARS", None)
            assert _get_max_chars() == 1500

    def test_max_chars_custom(self):
        """Can set custom max chars."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_MAX_CHARS": "2000"}):
            assert _get_max_chars() == 2000


class TestBuildKGContext:
    """Test build_kg_context function."""

    def test_disabled_returns_empty(self):
        """When disabled, should return empty packet."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_ENABLED": "false"}):
            packet = build_kg_context("test query")
            assert packet.is_empty()

    def test_no_entities_returns_empty(self, tmp_path):
        """When no entities found, should return empty packet."""
        from memory.kg.api import upsert_entity

        kg_db = tmp_path / "kg.sqlite"

        # Create an entity that won't match
        with patch("memory.kg.api._get_store") as mock_get_store:
            from memory.kg.store import KnowledgeGraphStore

            store = KnowledgeGraphStore(db_path=kg_db)
            mock_get_store.return_value = store

            upsert_entity(type="tool", name="SomeOtherTool", db_path=kg_db)

            packet = build_kg_context("completely unrelated query text")
            # Should be empty since no matches
            assert packet.is_empty()

    def test_finds_matching_entities(self, tmp_path):
        """Should find entities matching query terms."""
        from memory.kg.api import upsert_entity

        kg_db = tmp_path / "kg.sqlite"

        # Create entities
        python_id = upsert_entity(type="tool", name="Python", db_path=kg_db)
        milton_id = upsert_entity(type="project", name="Milton", db_path=kg_db)

        # Mock the search to return our entities
        with patch("memory.kg.api.search_entities") as mock_search:
            from memory.kg.schema import Entity
            from datetime import datetime, timezone

            mock_search.return_value = [
                Entity(
                    id=python_id,
                    type="tool",
                    name="Python",
                    created_ts=datetime.now(timezone.utc),
                    updated_ts=datetime.now(timezone.utc),
                ),
            ]

            with patch("memory.kg.api.neighbors") as mock_neighbors:
                mock_neighbors.return_value = []  # No edges

                packet = build_kg_context("Using Python for development")

                assert not packet.is_empty()
                assert len(packet.entities) > 0
                assert ("Python", "tool") in packet.entities

    def test_expands_neighborhood(self, tmp_path):
        """Should expand 1-hop neighborhood."""
        from memory.kg.api import upsert_edge, upsert_entity

        kg_db = tmp_path / "kg.sqlite"

        # Create entities and edges
        python_id = upsert_entity(type="tool", name="Python", db_path=kg_db)
        fastapi_id = upsert_entity(type="tool", name="FastAPI", db_path=kg_db)
        upsert_edge(
            subject_id=python_id,
            predicate="enables",
            object_id=fastapi_id,
            weight=0.8,
            evidence={"memory_id": "mem-123"},
            db_path=kg_db,
        )

        # Mock search and neighbors
        with patch("memory.kg.api.search_entities") as mock_search:
            from datetime import datetime, timezone

            from memory.kg.schema import Entity

            mock_search.return_value = [
                Entity(
                    id=python_id,
                    type="tool",
                    name="Python",
                    created_ts=datetime.now(timezone.utc),
                    updated_ts=datetime.now(timezone.utc),
                ),
            ]

            with patch("memory.kg.api.neighbors") as mock_neighbors:
                fastapi_entity = Entity(
                    id=fastapi_id,
                    type="tool",
                    name="FastAPI",
                    created_ts=datetime.now(timezone.utc),
                    updated_ts=datetime.now(timezone.utc),
                )
                from memory.kg.schema import Edge
                mock_edge = Edge(
                    id="test-edge",
                    subject_id="test-subj",
                    predicate="enables",
                    object_id="test-obj",
                    weight=0.8,
                    evidence={"memory_id": "test-mem"},
                )
                mock_neighbors.return_value = [(mock_edge, fastapi_entity)]

                packet = build_kg_context("Python development")

                assert not packet.is_empty()
                assert len(packet.entities) > 0
                assert len(packet.relationships) > 0
                # Check relationship format (subj, pred, obj, evidence)
                assert any(
                    rel[0] == "Python" and rel[1] == "enables" and rel[2] == "FastAPI"
                    for rel in packet.relationships
                )

    def test_respects_edge_cap(self, tmp_path):
        """Should respect max edges limit."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_MAX_EDGES": "3"}):
            with patch("memory.kg.api.search_entities") as mock_search:
                from datetime import datetime, timezone

                from memory.kg.schema import Entity

                mock_search.return_value = [
                    Entity(
                        id="test-1",
                        type="tool",
                        name="TestTool",
                        created_ts=datetime.now(timezone.utc),
                        updated_ts=datetime.now(timezone.utc),
                    ),
                ]

                with patch("memory.kg.api.neighbors") as mock_neighbors:
                    from memory.kg.schema import Edge
                    # Return 10 edges
                    edges = [
                        (
                            Edge(
                                id=f"edge-{i}",
                                subject_id="test-1",
                                predicate=f"pred{i}",
                                object_id=f"ent-{i}",
                                weight=0.8,
                                evidence={"memory_id": "test-mem"},
                            ),
                            Entity(
                                id=f"ent-{i}",
                                type="concept",
                                name=f"Entity{i}",
                                created_ts=datetime.now(timezone.utc),
                                updated_ts=datetime.now(timezone.utc),
                            ),
                        )
                        for i in range(10)
                    ]
                    mock_neighbors.return_value = edges

                    packet = build_kg_context("test query")

                    # Should be capped at 3
                    assert len(packet.relationships) <= 3

    def test_respects_char_limit(self):
        """Should truncate to fit character limit."""
        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_MAX_CHARS": "200"}):
            # Create a packet that would exceed 200 chars
            entities = [(f"VeryLongEntityName{i}", "concept") for i in range(20)]
            relationships = [
                (f"LongSubject{i}", "relates_to", f"LongObject{i}", "")
                for i in range(20)
            ]

            # Build packet directly
            packet = KGContextPacket(
                entities=entities,
                relationships=relationships,
                total_entities=20,
                total_edges=20,
            )

            # This would be too long
            prompt = packet.to_prompt_section()
            assert len(prompt) > 200

            # Now test build_kg_context with mocks
            with patch("memory.kg.api.search_entities") as mock_search:
                from datetime import datetime, timezone

                from memory.kg.schema import Entity

                mock_search.return_value = [
                    Entity(
                        id=f"ent-{i}",
                        type="concept",
                        name=f"VeryLongEntityName{i}",
                        created_ts=datetime.now(timezone.utc),
                        updated_ts=datetime.now(timezone.utc),
                    )
                    for i in range(5)
                ]

                with patch("memory.kg.api.neighbors") as mock_neighbors:
                    mock_neighbors.return_value = []

                    packet = build_kg_context("test")
                    prompt = packet.to_prompt_section()

                    # Should fit within limit
                    assert len(prompt) <= 200
