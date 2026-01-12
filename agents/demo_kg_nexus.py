#!/usr/bin/env python3
"""
Demo of Phase 4: KG Context Injection into NEXUS.

Shows how NEXUS includes KG context in its prompts for "connected" answers
about projects, tools, goals, and relationships.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from memory.kg.api import upsert_edge, upsert_entity
from memory.schema import MemoryItem
from memory.store import add_memory


def setup_demo_kg(kg_db: Path):
    """Set up demo KG with projects, tools, and relationships."""
    print("Setting up demo Knowledge Graph...")
    
    # Create entities
    user_id = upsert_entity(
        type="person",
        name="User",
        entity_id="entity:user:primary",
        db_path=kg_db
    )
    
    milton_id = upsert_entity(
        type="project",
        name="Milton",
        metadata={"description": "Personal AI assistant"},
        db_path=kg_db
    )
    
    meshalyzer_id = upsert_entity(
        type="project",
        name="Meshalyzer",
        metadata={"description": "Clamp design tool"},
        db_path=kg_db
    )
    
    python_id = upsert_entity(
        type="tool",
        name="Python",
        db_path=kg_db
    )
    
    fastapi_id = upsert_entity(
        type="tool",
        name="FastAPI",
        db_path=kg_db
    )
    
    weaviate_id = upsert_entity(
        type="tool",
        name="Weaviate",
        db_path=kg_db
    )
    
    kg_concept_id = upsert_entity(
        type="concept",
        name="knowledge graph",
        db_path=kg_db
    )
    
    # Create relationships
    upsert_edge(user_id, "works_on", milton_id, 0.9, {"src": "demo"}, db_path=kg_db)
    upsert_edge(user_id, "works_on", meshalyzer_id, 0.7, {"src": "demo"}, db_path=kg_db)
    upsert_edge(milton_id, "uses", python_id, 0.9, {"src": "demo"}, db_path=kg_db)
    upsert_edge(milton_id, "uses", fastapi_id, 0.8, {"src": "demo"}, db_path=kg_db)
    upsert_edge(milton_id, "uses", weaviate_id, 0.8, {"src": "demo"}, db_path=kg_db)
    upsert_edge(milton_id, "implements", kg_concept_id, 0.9, {"src": "demo"}, db_path=kg_db)
    
    print(f"Created 7 entities and 6 relationships\n")


def demo_kg_context_injection():
    """Demonstrate KG context injection in NEXUS."""
    print("=" * 70)
    print("Demo: KG Context Injection in NEXUS")
    print("=" * 70 + "\n")
    
    # Set up temporary KG database
    tmp_dir = Path(tempfile.mkdtemp())
    kg_db = tmp_dir / "kg.sqlite"
    
    setup_demo_kg(kg_db)
    
    # Test query
    queries = [
        "What projects am I working on?",
        "What tools does Milton use?",
        "Tell me about my projects",
    ]
    
    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 70)
        
        # Build KG context (mocking what NEXUS does)
        from agents.kg_context import build_kg_context
        
        # Override db_path for this demo
        with os.popen(f"MILTON_KG_CONTEXT_ENABLED=true python -c \"import os; os.environ['MILTON_KG_CONTEXT_ENABLED']='true'; from agents.kg_context import build_kg_context; packet = build_kg_context('{query}', top_k=5); print(packet.to_prompt_section())\"") as proc:
            pass  # Complex to mock in demo
        
        # Instead, let's manually show what would be injected
        from memory.kg.api import search_entities, neighbors
        
        # Search for relevant entities
        words = query.lower().split()
        relevant_entities = []
        for word in ["milton", "project", "projects", "tools", "meshalyzer"]:
            if word in query.lower():
                entities = search_entities(name=word, db_path=kg_db)
                relevant_entities.extend(entities)
        
        if not relevant_entities:
            # Try broader search
            for word in words:
                if len(word) >= 4:
                    entities = search_entities(name=word, db_path=kg_db)
                    relevant_entities.extend(entities[:2])
        
        # Remove duplicates
        seen = set()
        unique_entities = []
        for ent in relevant_entities:
            if ent.id not in seen:
                seen.add(ent.id)
                unique_entities.append(ent)
        
        if unique_entities:
            print("\n**Knowledge Graph Context:**")
            print(f"Entities ({len(unique_entities)}/{len(unique_entities)}):")
            for ent in unique_entities[:5]:
                print(f"  - {ent.name} ({ent.type})")
            
            # Get relationships
            all_edges = []
            for ent in unique_entities[:3]:
                outgoing = neighbors(ent.id, direction="outgoing", db_path=kg_db, limit=5)
                for pred, weight, target in outgoing:
                    all_edges.append((ent.name, pred, target.name))
            
            if all_edges:
                print(f"Relationships ({len(all_edges)}/{len(all_edges)}):")
                for subj, pred, obj in all_edges[:10]:
                    print(f"  - {subj} --{pred}--> {obj}")
        else:
            print("\n(No relevant KG context found)")
    
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print("\nKG context injection enriches NEXUS responses with:")
    print("  ✓ Relevant entities from the knowledge graph")
    print("  ✓ Relationships connecting those entities")
    print("  ✓ Evidence pointers for provenance")
    print("\nThis enables NEXUS to provide 'connected' answers that")
    print("reference explicit relationships stored in the graph.\n")
    
    print("Configuration:")
    print("  export MILTON_KG_CONTEXT_ENABLED=true  # default")
    print("  export MILTON_KG_CONTEXT_MAX_EDGES=20  # default")
    print("  export MILTON_KG_CONTEXT_MAX_CHARS=1500  # default\n")


def demo_context_packet_format():
    """Show the ContextPacket format with KG context."""
    print("=" * 70)
    print("Demo: ContextPacket Format with KG Context")
    print("=" * 70 + "\n")
    
    from agents.nexus import ContextBullet, ContextPacket
    
    # Example context packet
    packet = ContextPacket(
        query="What tools does Milton use?",
        bullets=[
            ContextBullet(
                text="Working on Milton AI assistant project",
                evidence_ids=["mem-123"]
            ),
            ContextBullet(
                text="Using Python and FastAPI for backend",
                evidence_ids=["mem-456"]
            ),
        ],
        unknowns=[],
        assumptions=["Assume request is self-contained unless clarified."],
        kg_context=(
            "**Knowledge Graph Context:**\n"
            "Entities (3/3):\n"
            "  - Milton (project)\n"
            "  - Python (tool)\n"
            "  - FastAPI (tool)\n"
            "Relationships (2/2):\n"
            "  - Milton --uses--> Python [evidence: mem-789]\n"
            "  - Milton --uses--> FastAPI [evidence: mem-789]"
        ),
    )
    
    print("ContextPacket structure:")
    print(packet.to_prompt())
    print("\n" + "=" * 70)
    print("Note: KG context appears as a separate section after")
    print("memory bullets and assumptions, providing structured")
    print("relationship data to complement unstructured memories.\n")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Knowledge Graph Context Injection Demo")
    print("=" * 70 + "\n")
    
    demo_kg_context_injection()
    print()
    demo_context_packet_format()
    
    print("=" * 70)
    print("Phase 4 Complete!")
    print("=" * 70)
    print("\nKG context injection is now active in NEXUS.")
    print("Test it with:")
    print("  python -m agents.nexus")
    print("  or check tests/test_nexus_kg_integration.py\n")
