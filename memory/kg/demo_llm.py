#!/usr/bin/env python3
"""
Demo of Phase 3: Optional LLM-based KG enrichment.

Shows how LLM enrichment proposes additional entities and relationships
beyond deterministic pattern matching.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile

# Mock the LLM for demo purposes (no actual LLM needed)
from unittest.mock import patch

from memory.kg.api import search_entities, neighbors
from memory.kg.extract import extract_entities_and_edges


def demo_without_llm():
    """Demonstrate deterministic extraction only."""
    print("=" * 70)
    print("Demo 1: Deterministic Extraction (No LLM)")
    print("=" * 70)
    
    memory_dict = {
        "id": "demo-1",
        "content": "I'm using FastAPI with Pydantic for API validation",
        "type": "fact",
        "ts": datetime.now(timezone.utc).isoformat(),
        "tags": [],
        "agent": "test",
        "source": "demo",
    }
    
    entities, edge_specs = extract_entities_and_edges(memory_dict)
    
    print(f"\nMemory: {memory_dict['content']}\n")
    print(f"Extracted {len(entities)} entities:")
    for ent in entities:
        if ent.type != "person":  # Skip user entity
            print(f"  - {ent.name} ({ent.type})")
    
    print(f"\nExtracted {len(edge_specs)} relationships:")
    for subj, pred, obj, weight, evidence in edge_specs:
        print(f"  - {subj} --{pred}--> {obj} (weight={weight})")
    
    print()


def demo_with_llm():
    """Demonstrate LLM enrichment with mocked LLM."""
    print("=" * 70)
    print("Demo 2: With LLM Enrichment (Mocked)")
    print("=" * 70)
    
    # Mock LLM response
    llm_response = json.dumps({
        "entities": [
            {
                "type": "concept",
                "name": "microservices architecture",
                "aliases": ["microservices"],
                "metadata": {"domain": "software_architecture"}
            },
            {
                "type": "concept",
                "name": "REST API",
                "aliases": ["RESTful API"],
            },
            {
                "type": "concept",
                "name": "data validation",
                "aliases": ["input validation"],
            },
        ],
        "edges": [
            {
                "subject_name": "FastAPI",
                "subject_type": "tool",
                "predicate": "enables",
                "object_name": "REST API",
                "object_type": "concept",
                "weight": 0.95,
                "reason_short": "FastAPI is a framework for building REST APIs"
            },
            {
                "subject_name": "Pydantic",
                "subject_type": "tool",
                "predicate": "provides",
                "object_name": "data validation",
                "object_type": "concept",
                "weight": 0.9,
                "reason_short": "Pydantic provides runtime data validation"
            },
            {
                "subject_name": "REST API",
                "subject_type": "concept",
                "predicate": "part_of",
                "object_name": "microservices architecture",
                "object_type": "concept",
                "weight": 0.8,
                "reason_short": "REST APIs are common in microservices"
            },
        ],
    })
    
    memory_dict = {
        "id": "demo-2",
        "content": "I'm using FastAPI with Pydantic for API validation",
        "type": "fact",
        "ts": datetime.now(timezone.utc).isoformat(),
        "tags": [],
        "agent": "test",
        "source": "demo",
    }
    
    with patch("memory.kg.enrich_llm._call_llm") as mock_llm:
        mock_llm.return_value = llm_response
        
        with patch.dict(os.environ, {"MILTON_KG_LLM_ENRICH_ENABLED": "true"}):
            # Import here so it picks up the env var
            from memory.kg.enrich_llm import propose_graph_updates
            
            # Get deterministic extraction
            det_entities, det_edge_specs = extract_entities_and_edges(memory_dict)
            
            # Get LLM enrichment
            llm_updates = propose_graph_updates(memory_dict)
            
            print(f"\nMemory: {memory_dict['content']}\n")
            
            print(f"Deterministic extraction found {len([e for e in det_entities if e.type != 'person'])} entities:")
            for ent in det_entities:
                if ent.type != "person":
                    print(f"  - {ent.name} ({ent.type})")
            
            print(f"\nLLM enrichment added {len(llm_updates['entities'])} entities:")
            for ent in llm_updates["entities"]:
                print(f"  - {ent['name']} ({ent['type']})")
                if ent.get("aliases"):
                    print(f"    aliases: {', '.join(ent['aliases'])}")
            
            print(f"\nLLM enrichment added {len(llm_updates['edges'])} relationships:")
            for edge in llm_updates["edges"]:
                print(f"  - {edge['subject_name']} --{edge['predicate']}--> {edge['object_name']}")
                print(f"    weight={edge['weight']}, reason: {edge['reason_short']}")
    
    print()


def demo_safety_features():
    """Demonstrate validation and safety features."""
    print("=" * 70)
    print("Demo 3: Safety Features")
    print("=" * 70)
    
    print("\n1. PII Filtering:")
    print("   Input entity: 'john@example.com' -> REJECTED (contains @)")
    print("   Input entity: 'visit example.com' -> REJECTED (contains .com)")
    print("   Input entity: 'valid concept' -> ACCEPTED")
    
    print("\n2. Confidence Threshold:")
    print("   Edge weight=0.3 -> REJECTED (below 0.5 threshold)")
    print("   Edge weight=0.7 -> ACCEPTED")
    print("   Edge weight=1.2 -> REJECTED (above 1.0 limit)")
    
    print("\n3. Edge Cap:")
    print("   LLM proposes 20 edges")
    print("   MILTON_KG_LLM_ENRICH_MAX_EDGES=3")
    print("   Result: Only first 3 edges accepted")
    
    print("\n4. Fail-Safe:")
    print("   LLM call fails -> Continue with deterministic only")
    print("   Invalid JSON -> Return empty results, no crash")
    print("   Memory write never blocked by enrichment errors")
    
    print()


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("Knowledge Graph LLM Enrichment Demo")
    print("=" * 70 + "\n")
    
    demo_without_llm()
    demo_with_llm()
    demo_safety_features()
    
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print("\nLLM enrichment is:")
    print("  ✓ Disabled by default (MILTON_KG_LLM_ENRICH_ENABLED=false)")
    print("  ✓ Never required (always falls back to deterministic)")
    print("  ✓ Safe (validates output, filters PII, caps edges)")
    print("  ✓ Fail-safe (errors never block memory writes)")
    print("  ✓ Works offline (gracefully degrades)")
    print("\nTo enable:")
    print("  export MILTON_KG_LLM_ENRICH_ENABLED=true")
    print("  export MILTON_KG_LLM_ENRICH_MAX_EDGES=10  # optional")
    print("\nSee memory/kg/LLM_ENRICHMENT_SUMMARY.md for details.\n")


if __name__ == "__main__":
    main()
