"""Tests for LLM-based knowledge graph enrichment."""

import json
import os
from unittest.mock import Mock, patch

import pytest

from memory.kg.enrich_llm import (
    _call_llm,
    _get_llm_config,
    _get_max_edges,
    _is_llm_enrichment_enabled,
    _validate_and_sanitize,
    propose_graph_updates,
)


class TestEnvFlags:
    """Test environment flag parsing."""

    def test_llm_enrichment_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove flag if it exists
            os.environ.pop("MILTON_KG_LLM_ENRICH_ENABLED", None)
            assert not _is_llm_enrichment_enabled()

    def test_llm_enrichment_enabled_variations(self):
        for value in ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"]:
            with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": value}):
                assert _is_llm_enrichment_enabled(), f"Failed for {value}"

    def test_llm_enrichment_disabled_variations(self):
        for value in ["0", "false", "False", "no", "off", "anything_else"]:
            with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": value}):
                assert not _is_llm_enrichment_enabled(), f"Failed for {value}"

    def test_max_edges_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MILTON_KG_LLM_ENRICH_MAX_EDGES", None)
            assert _get_max_edges() == 10

    def test_max_edges_custom(self):
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_MAX_EDGES": "5"}):
            assert _get_max_edges() == 5

    def test_max_edges_invalid_uses_default(self):
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_MAX_EDGES": "not_a_number"}):
            assert _get_max_edges() == 10


class TestValidateAndSanitize:
    """Test JSON validation and sanitization."""

    def test_valid_json_accepted(self):
        raw = json.dumps({
            "entities": [
                {"type": "concept", "name": "machine learning", "aliases": ["ML"], "metadata": {"key": "val"}},
            ],
            "edges": [
                {
                    "subject_name": "Python",
                    "subject_type": "tool",
                    "predicate": "enables",
                    "object_name": "machine learning",
                    "object_type": "concept",
                    "weight": 0.9,
                    "reason_short": "Python is used for ML",
                }
            ],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(entities) == 1
        assert entities[0]["name"] == "machine learning"
        assert len(edges) == 1
        assert edges[0]["weight"] == 0.9

    def test_markdown_code_fence_removed(self):
        raw = "```json\n" + json.dumps({"entities": [], "edges": []}) + "\n```"
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert entities == []
        assert edges == []

    def test_markdown_with_json_language(self):
        raw = "```json\n" + json.dumps({"entities": [{"type": "tool", "name": "Git"}], "edges": []})
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(entities) == 1
        assert entities[0]["name"] == "Git"

    def test_invalid_json_returns_empty(self):
        raw = "not valid json at all"
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert entities == []
        assert edges == []

    def test_missing_entity_fields_skipped(self):
        raw = json.dumps({
            "entities": [
                {"type": "concept"},  # Missing name
                {"name": "test"},  # Missing type
                {"type": "tool", "name": "valid"},
            ],
            "edges": [],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(entities) == 1
        assert entities[0]["name"] == "valid"

    def test_missing_edge_fields_skipped(self):
        raw = json.dumps({
            "entities": [],
            "edges": [
                {"subject_name": "A", "predicate": "relates"},  # Missing fields
                {
                    "subject_name": "A",
                    "subject_type": "concept",
                    "predicate": "relates_to",
                    "object_name": "B",
                    "object_type": "concept",
                    "weight": 0.8,
                },
            ],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(edges) == 1
        assert edges[0]["subject_name"] == "A"

    def test_low_weight_edges_rejected(self):
        raw = json.dumps({
            "entities": [],
            "edges": [
                {
                    "subject_name": "A",
                    "subject_type": "concept",
                    "predicate": "relates_to",
                    "object_name": "B",
                    "object_type": "concept",
                    "weight": 0.3,  # Below 0.5 threshold
                },
                {
                    "subject_name": "C",
                    "subject_type": "concept",
                    "predicate": "relates_to",
                    "object_name": "D",
                    "object_type": "concept",
                    "weight": 0.7,  # Above threshold
                },
            ],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(edges) == 1
        assert edges[0]["subject_name"] == "C"

    def test_high_weight_edges_rejected(self):
        raw = json.dumps({
            "entities": [],
            "edges": [
                {
                    "subject_name": "A",
                    "subject_type": "concept",
                    "predicate": "relates_to",
                    "object_name": "B",
                    "object_type": "concept",
                    "weight": 1.5,  # Above 1.0 limit
                },
            ],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(edges) == 0

    def test_edge_cap_enforced(self):
        edges_list = [
            {
                "subject_name": f"A{i}",
                "subject_type": "concept",
                "predicate": "relates_to",
                "object_name": f"B{i}",
                "object_type": "concept",
                "weight": 0.8,
            }
            for i in range(20)
        ]
        raw = json.dumps({"entities": [], "edges": edges_list})
        entities, edges = _validate_and_sanitize(raw, max_edges=5)
        assert len(edges) == 5

    def test_pii_entities_rejected(self):
        raw = json.dumps({
            "entities": [
                {"type": "person", "name": "john@example.com"},  # Email
                {"type": "person", "name": "visit example.com"},  # Domain
                {"type": "person", "name": "phone: 555-1234"},  # Phone
                {"type": "person", "name": "123 main address"},  # Address
                {"type": "concept", "name": "valid concept"},  # Should pass
            ],
            "edges": [],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(entities) == 1
        assert entities[0]["name"] == "valid concept"

    def test_default_weight_and_reason(self):
        raw = json.dumps({
            "entities": [],
            "edges": [
                {
                    "subject_name": "A",
                    "subject_type": "concept",
                    "predicate": "relates_to",
                    "object_name": "B",
                    "object_type": "concept",
                    # No weight or reason_short
                }
            ],
        })
        entities, edges = _validate_and_sanitize(raw, max_edges=10)
        assert len(edges) == 1
        assert edges[0]["weight"] == 0.7
        assert edges[0]["reason_short"] == ""


class TestProposeGraphUpdates:
    """Test the main propose_graph_updates function."""

    def test_disabled_returns_empty(self):
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "false"}):
            memory_item = {"type": "preference", "content": "test", "tags": []}
            result = propose_graph_updates(memory_item)
            assert result == {"entities": [], "edges": []}

    @patch("memory.kg.enrich_llm._call_llm")
    def test_enabled_calls_llm(self, mock_call_llm):
        mock_call_llm.return_value = json.dumps({
            "entities": [{"type": "concept", "name": "test"}],
            "edges": [],
        })
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            memory_item = {"type": "preference", "content": "test", "tags": []}
            result = propose_graph_updates(memory_item)
            assert len(result["entities"]) == 1
            mock_call_llm.assert_called_once()

    @patch("memory.kg.enrich_llm._call_llm")
    def test_llm_failure_returns_empty(self, mock_call_llm):
        mock_call_llm.side_effect = RuntimeError("LLM failed")
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            memory_item = {"type": "preference", "content": "test", "tags": []}
            result = propose_graph_updates(memory_item)
            assert result == {"entities": [], "edges": []}

    @patch("memory.kg.enrich_llm._call_llm")
    def test_invalid_json_returns_empty(self, mock_call_llm):
        mock_call_llm.return_value = "not valid json"
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            memory_item = {"type": "preference", "content": "test", "tags": []}
            result = propose_graph_updates(memory_item)
            assert result == {"entities": [], "edges": []}

    @patch("memory.kg.enrich_llm._call_llm")
    def test_max_edges_respected(self, mock_call_llm):
        edges_list = [
            {
                "subject_name": f"A{i}",
                "subject_type": "concept",
                "predicate": "relates_to",
                "object_name": f"B{i}",
                "object_type": "concept",
                "weight": 0.8,
            }
            for i in range(20)
        ]
        mock_call_llm.return_value = json.dumps({"entities": [], "edges": edges_list})
        with patch.dict(
            os.environ,
            {
                "MILTON_KG_LLM_ENRICH_ENABLED": "true",
                "MILTON_KG_LLM_ENRICH_MAX_EDGES": "3",
            },
        ):
            memory_item = {"type": "preference", "content": "test", "tags": []}
            result = propose_graph_updates(memory_item)
            assert len(result["edges"]) == 3


class TestCallLLM:
    """Test LLM calling with mocked requests."""

    @patch("memory.kg.enrich_llm.requests.post")
    def test_successful_call(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test response"}}]
        }
        mock_post.return_value = mock_response

        config = _get_llm_config()
        messages = [{"role": "user", "content": "test"}]
        result = _call_llm(messages, config)
        assert result == "test response"

    @patch("memory.kg.enrich_llm.requests.post")
    def test_connection_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        config = _get_llm_config()
        messages = [{"role": "user", "content": "test"}]
        with pytest.raises(RuntimeError, match="Cannot connect to LLM"):
            _call_llm(messages, config)

    @patch("memory.kg.enrich_llm.requests.post")
    def test_timeout_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.Timeout("Timeout")

        config = _get_llm_config()
        messages = [{"role": "user", "content": "test"}]
        with pytest.raises(RuntimeError, match="timed out"):
            _call_llm(messages, config)
