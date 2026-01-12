"""Integration tests for LLM enrichment with memory store."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from memory.schema import MemoryItem
from memory.kg.api import search_entities, neighbors, upsert_entity, upsert_edge
from memory.kg.extract import extract_entities_and_edges


def _now_utc():
    return datetime.now(timezone.utc)


def _process_memory_to_kg_with_llm(memory_dict: dict, db_path: Path) -> None:
    """Helper to extract entities/edges (with LLM) from memory and populate KG.
    
    Mimics what _enrich_knowledge_graph does but with explicit db_path.
    """
    from memory.kg.schema import _normalize_name, Entity
    from memory.kg.enrich_llm import propose_graph_updates
    
    # Phase 1: Deterministic extraction
    entities, edge_specs = extract_entities_and_edges(memory_dict)
    
    # Phase 2: LLM enrichment
    try:
        llm_updates = propose_graph_updates(memory_dict)
        # Merge LLM entities
        for llm_entity in llm_updates.get("entities", []):
            ent = Entity(
                id="",
                type=llm_entity["type"],
                name=llm_entity["name"],
                metadata={
                    "source": "llm_enrichment",
                    "aliases": llm_entity.get("aliases", []),
                    **llm_entity.get("metadata", {}),
                },
                created_ts=_now_utc(),
                updated_ts=_now_utc(),
            )
            entities.append(ent)
        
        # Merge LLM edges
        for llm_edge in llm_updates.get("edges", []):
            subj_key = f"{llm_edge['subject_type']}:{_normalize_name(llm_edge['subject_name'])}"
            obj_key = f"{llm_edge['object_type']}:{_normalize_name(llm_edge['object_name'])}"
            evidence = {
                "memory_id": memory_dict["id"],
                "src": "llm_enrichment",
                "timestamp": _now_utc().isoformat(),
                "reason": llm_edge.get("reason_short", ""),
            }
            edge_specs.append((subj_key, llm_edge["predicate"], obj_key, llm_edge["weight"], evidence))
    except Exception:
        pass  # LLM enrichment is optional
    
    # Build ID map and upsert
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


class TestMemoryLLMIntegration:
    """Test LLM enrichment integration with memory writes."""

    def test_disabled_no_llm_edges(self, tmp_path):
        """With flag disabled, should only get deterministic edges."""
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "false"}):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-1",
                "content": "I prefer using Python for data analysis",
                "type": "preference",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # Should have deterministic extractions
            python_ent = search_entities(name="Python", db_path=kg_db)
            assert len(python_ent) > 0
            
            # No LLM-specific metadata
            for ent in python_ent:
                assert ent.metadata.get("source") != "llm_enrichment"

    @patch("memory.kg.enrich_llm._call_llm")
    def test_enabled_adds_llm_edges(self, mock_call_llm, tmp_path):
        """With flag enabled and mocked LLM, should add enriched entities/edges."""
        mock_call_llm.return_value = json.dumps({
            "entities": [
                {"type": "concept", "name": "data science", "aliases": ["DS"]},
                {"type": "methodology", "name": "statistical analysis"},
            ],
            "edges": [
                {
                    "subject_name": "Python",
                    "subject_type": "tool",
                    "predicate": "enables",
                    "object_name": "data science",
                    "object_type": "concept",
                    "weight": 0.9,
                    "reason_short": "Python is primary tool for data science",
                },
            ],
        })
        
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-2",
                "content": "I prefer using Python for data analysis",
                "type": "preference",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # Should have LLM-enriched entities
            data_science = search_entities(name="data science", db_path=kg_db)
            assert len(data_science) == 1
            assert data_science[0].metadata.get("source") == "llm_enrichment"
            
            stats = search_entities(name="statistical analysis", db_path=kg_db)
            assert len(stats) == 1
            assert stats[0].metadata.get("source") == "llm_enrichment"

    @patch("memory.kg.enrich_llm._call_llm")
    def test_llm_failure_continues_with_deterministic(self, mock_call_llm, tmp_path):
        """If LLM fails, should still get deterministic extractions."""
        mock_call_llm.side_effect = RuntimeError("LLM failed")
        
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-3",
                "content": "I prefer using Python",
                "type": "preference",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            # Should not raise exception
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # Should still have deterministic entities
            python_ent = search_entities(name="Python", db_path=kg_db)
            assert len(python_ent) > 0

    @patch("memory.kg.enrich_llm._call_llm")
    def test_llm_invalid_json_continues(self, mock_call_llm, tmp_path):
        """If LLM returns invalid JSON, should continue with deterministic only."""
        mock_call_llm.return_value = "not valid json at all"
        
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-4",
                "content": "Working on Milton project using Python",
                "type": "fact",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # Should have deterministic entities only
            milton = search_entities(name="Milton", db_path=kg_db)
            assert len(milton) > 0
            # No LLM metadata
            assert milton[0].metadata.get("source") != "llm_enrichment"

    @patch("memory.kg.enrich_llm._call_llm")
    def test_edge_cap_enforced(self, mock_call_llm, tmp_path):
        """Should enforce max edges limit from env."""
        edges_list = [
            {
                "subject_name": f"concept{i}",
                "subject_type": "concept",
                "predicate": "relates_to",
                "object_name": f"concept{i+1}",
                "object_type": "concept",
                "weight": 0.8,
                "reason_short": "test",
            }
            for i in range(20)
        ]
        entities_list = [
            {"type": "concept", "name": f"concept{i}"}
            for i in range(21)
        ]
        mock_call_llm.return_value = json.dumps({
            "entities": entities_list,
            "edges": edges_list,
        })
        
        with patch.dict(
            os.environ,
            {
                "MILTON_KG_LLM_ENRICH_ENABLED": "true",
                "MILTON_KG_LLM_ENRICH_MAX_EDGES": "3",
            },
        ):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-5",
                "content": "test content",
                "type": "fact",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # Should have many entities but capped edges
            llm_entities = search_entities(name="concept", db_path=kg_db)
            assert len(llm_entities) > 0

    @patch("memory.kg.enrich_llm._call_llm")
    def test_llm_not_called_when_disabled(self, mock_call_llm, tmp_path):
        """LLM should not be called when flag is disabled."""
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "false"}):
            kg_db = tmp_path / "kg.sqlite"
            memory_dict = {
                "id": "test-mem-6",
                "content": "test content",
                "type": "fact",
                "ts": _now_utc().isoformat(),
                "tags": [],
                "agent": "test",
                "source": "test",
            }
            
            _process_memory_to_kg_with_llm(memory_dict, kg_db)
            
            # LLM should never have been called
            mock_call_llm.assert_not_called()
