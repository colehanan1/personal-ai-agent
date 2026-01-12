"""Knowledge Graph demonstration and validation script.

Demonstrates basic KG operations: entity creation, relationships, queries, and snapshots.
"""

from memory.kg import (
    export_snapshot,
    neighbors,
    search_entities,
    upsert_edge,
    upsert_entity,
)


def demo_basic_operations():
    """Demonstrate basic entity and edge operations."""
    print("=" * 60)
    print("Knowledge Graph Basic Operations Demo")
    print("=" * 60)
    
    # Create entities
    print("\n1. Creating entities...")
    milton_id = upsert_entity(
        type="project",
        name="Milton",
        metadata={"description": "Personal AI agent", "active": True}
    )
    print(f"   Created Milton: {milton_id}")
    
    kg_id = upsert_entity(
        type="concept",
        name="Knowledge Graph",
        metadata={"technology": "graph database"}
    )
    print(f"   Created Knowledge Graph: {kg_id}")
    
    sqlite_id = upsert_entity(
        type="tool",
        name="SQLite",
        metadata={"category": "database"}
    )
    print(f"   Created SQLite: {sqlite_id}")
    
    weaviate_id = upsert_entity(
        type="tool",
        name="Weaviate",
        metadata={"category": "vector database"}
    )
    print(f"   Created Weaviate: {weaviate_id}")
    
    # Create relationships
    print("\n2. Creating relationships...")
    upsert_edge(
        milton_id,
        "implements",
        kg_id,
        weight=0.9,
        evidence={"src": "design_doc", "date": "2025-01"}
    )
    print(f"   Milton --implements--> Knowledge Graph")
    
    upsert_edge(
        milton_id,
        "uses",
        sqlite_id,
        weight=1.0,
        evidence={"src": "codebase"}
    )
    print(f"   Milton --uses--> SQLite")
    
    upsert_edge(
        milton_id,
        "uses",
        weaviate_id,
        weight=0.8,
        evidence={"src": "codebase", "optional": True}
    )
    print(f"   Milton --uses--> Weaviate")
    
    # Query neighbors
    print("\n3. Querying neighbors of Milton...")
    results = neighbors(milton_id, direction="outgoing")
    for edge, entity in results:
        print(f"   --[{edge.predicate}]--> {entity.name} (weight: {edge.weight})")
    
    # Search entities
    print("\n4. Searching entities...")
    tools = search_entities(type="tool")
    print(f"   Found {len(tools)} tools:")
    for tool in tools:
        print(f"     - {tool.name}")
    
    # Export snapshot
    print("\n5. Exporting snapshot...")
    snapshot = export_snapshot()
    print(f"   Entities: {len(snapshot['entities'])}")
    print(f"   Edges: {len(snapshot['edges'])}")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


def demo_collaborative_graph():
    """Demonstrate a more complex graph with people and projects."""
    print("\n" + "=" * 60)
    print("Collaborative Knowledge Graph Demo")
    print("=" * 60)
    
    # Create people
    print("\n1. Creating people...")
    cole_id = upsert_entity(
        type="person",
        name="Cole",
        metadata={"role": "developer"}
    )
    print(f"   Created Cole: {cole_id}")
    
    # Create projects
    print("\n2. Creating projects...")
    milton_id = upsert_entity(type="project", name="Milton")
    dashboard_id = upsert_entity(type="project", name="Dashboard")
    
    # Create concepts
    print("\n3. Creating concepts...")
    ai_id = upsert_entity(type="concept", name="AI")
    automation_id = upsert_entity(type="concept", name="Automation")
    
    # Create relationships
    print("\n4. Creating relationships...")
    upsert_edge(cole_id, "works_on", milton_id, weight=1.0)
    upsert_edge(cole_id, "works_on", dashboard_id, weight=0.8)
    upsert_edge(milton_id, "implements", ai_id, weight=0.9)
    upsert_edge(milton_id, "enables", automation_id, weight=0.8)
    
    # Query what Cole works on
    print("\n5. What does Cole work on?")
    for edge, entity in neighbors(cole_id, predicate="works_on"):
        print(f"   {entity.name} (intensity: {edge.weight})")
    
    # Query what implements AI
    print("\n6. What implements AI?")
    for edge, entity in neighbors(ai_id, direction="incoming", predicate="implements"):
        print(f"   {entity.name}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo_basic_operations()
    demo_collaborative_graph()
