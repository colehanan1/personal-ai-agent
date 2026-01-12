"""Integration tests for KG context in NEXUS."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agents.nexus import ContextPacket


class TestNEXUSKGIntegration:
    """Test KG context injection into NEXUS build_context."""

    def test_context_packet_includes_kg_field(self):
        """ContextPacket should have kg_context field."""
        packet = ContextPacket(
            query="test",
            bullets=[],
            unknowns=[],
            assumptions=[],
            kg_context="**Knowledge Graph Context:**\nEntities (1/1):\n  - Python (tool)",
        )
        assert packet.kg_context is not None
        prompt = packet.to_prompt()
        assert "Knowledge Graph Context" in prompt
        assert "Python (tool)" in prompt

    def test_context_packet_without_kg(self):
        """ContextPacket without KG context should work normally."""
        packet = ContextPacket(
            query="test",
            bullets=[],
            unknowns=[],
            assumptions=[],
            kg_context=None,
        )
        assert packet.kg_context is None
        prompt = packet.to_prompt()
        assert "Knowledge Graph Context" not in prompt

    @patch("agents.nexus.memory_enabled")
    @patch("agents.nexus.query_relevant_hybrid")
    @patch("agents.kg_context.build_kg_context")
    def test_build_context_includes_kg(
        self, mock_build_kg, mock_query, mock_mem_enabled
    ):
        """build_context should include KG context when available."""
        from agents.kg_context import KGContextPacket
        from agents.nexus import NEXUS

        # Setup mocks
        mock_mem_enabled.return_value = True
        mock_query.return_value = []  # No memory results

        # Mock KG context
        kg_packet = KGContextPacket(
            entities=[("Python", "tool"), ("Milton", "project")],
            relationships=[("User", "works_on", "Milton", "mem-123")],
            total_entities=2,
            total_edges=1,
        )
        mock_build_kg.return_value = kg_packet

        nexus = NEXUS()
        context = nexus.build_context("What am I working on?")

        assert context.kg_context is not None
        assert "Python (tool)" in context.kg_context
        assert "Milton (project)" in context.kg_context
        assert "works_on" in context.kg_context

    @patch("agents.nexus.memory_enabled")
    @patch("agents.nexus.query_relevant_hybrid")
    @patch("agents.kg_context.build_kg_context")
    def test_build_context_handles_kg_failure(
        self, mock_build_kg, mock_query, mock_mem_enabled
    ):
        """build_context should handle KG failures gracefully."""
        from agents.nexus import NEXUS

        # Setup mocks
        mock_mem_enabled.return_value = True
        mock_query.return_value = []

        # Mock KG to raise exception
        mock_build_kg.side_effect = RuntimeError("KG failed")

        nexus = NEXUS()
        context = nexus.build_context("test query")

        # Should still work, just without KG context
        assert context.kg_context is None

    @patch("agents.nexus.memory_enabled")
    @patch("agents.nexus.query_relevant_hybrid")
    def test_build_context_when_kg_disabled(self, mock_query, mock_mem_enabled):
        """build_context should work when KG is disabled."""
        from agents.nexus import NEXUS

        # Setup mocks
        mock_mem_enabled.return_value = True
        mock_query.return_value = []

        with patch.dict(os.environ, {"MILTON_KG_CONTEXT_ENABLED": "false"}):
            nexus = NEXUS()
            context = nexus.build_context("test query")

            # Should have no KG context
            assert context.kg_context is None or context.kg_context == ""

    @patch("agents.nexus.memory_enabled")
    @patch("agents.nexus.query_relevant_hybrid")
    @patch("memory.kg.api.search_entities")
    def test_build_context_with_real_kg_empty(
        self, mock_search, mock_query, mock_mem_enabled
    ):
        """build_context with empty KG should not crash."""
        from agents.nexus import NEXUS

        # Setup mocks
        mock_mem_enabled.return_value = True
        mock_query.return_value = []
        mock_search.return_value = []  # No entities found

        nexus = NEXUS()
        context = nexus.build_context("test query")

        # Should work, with empty or None kg_context
        assert context.kg_context is None or context.kg_context == ""
