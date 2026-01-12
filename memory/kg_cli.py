"""CLI tool for Knowledge Graph inspection and management"""

import argparse
import json
import sqlite3
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from collections import Counter

from memory.kg.api import (
    search_entities,
    neighbors,
    export_snapshot,
    import_snapshot,
)
from memory.kg.store import KnowledgeGraphStore
from memory.backends import get_backend, repo_root_from_file
from memory.kg.extract import extract_entities_and_edges

logger = logging.getLogger(__name__)


def cmd_stats(db_path: Optional[Path] = None):
    """Show KG statistics: entity/edge counts, top predicates"""
    store = KnowledgeGraphStore(db_path=db_path)
    
    # Create connection for querying
    conn = sqlite3.connect(store.db_path)
    try:
        # Get entity counts by type
        entities_query = """
            SELECT type, COUNT(*) as count 
            FROM entities 
            GROUP BY type 
            ORDER BY count DESC
        """
        cursor = conn.execute(entities_query)
        entity_stats = cursor.fetchall()
        
        # Get total entity count
        total_entities = sum(count for _, count in entity_stats)
        
        # Get edge counts by predicate
        edges_query = """
            SELECT predicate, COUNT(*) as count 
            FROM edges 
            GROUP BY predicate 
            ORDER BY count DESC
        """
        cursor = conn.execute(edges_query)
        edge_stats = cursor.fetchall()
        
        # Get total edge count
        total_edges = sum(count for _, count in edge_stats)
        
        # Get oldest and newest timestamps
        age_query = """
            SELECT 
                MIN(created_ts) as oldest_entity,
                MAX(created_ts) as newest_entity
            FROM entities
        """
        cursor = conn.execute(age_query)
        oldest_ts, newest_ts = cursor.fetchone()
    finally:
        conn.close()
    
    # Print statistics
    print("=" * 60)
    print("Knowledge Graph Statistics")
    print("=" * 60)
    print(f"\nDatabase: {store.db_path}")
    print(f"\nTotal Entities: {total_entities}")
    print(f"Total Edges: {total_edges}")
    
    if oldest_ts and newest_ts:
        print(f"\nOldest Entity: {oldest_ts}")
        print(f"Newest Entity: {newest_ts}")
    
    if entity_stats:
        print("\n--- Entities by Type ---")
        for entity_type, count in entity_stats:
            print(f"  {entity_type:20s}: {count:5d}")
    
    if edge_stats:
        print("\n--- Relationships by Predicate ---")
        for predicate, count in edge_stats:
            print(f"  {predicate:20s}: {count:5d}")
    
    print("=" * 60)


def cmd_search(term: str, entity_type: Optional[str] = None, limit: int = 20, db_path: Optional[Path] = None):
    """Search for entities by name"""
    results = search_entities(name=term, type=entity_type, limit=limit, db_path=db_path)
    
    print(f"\nSearch results for '{term}' (limit={limit}):")
    print("-" * 80)
    
    if not results:
        print("No matching entities found.")
        return
    
    for entity in results:
        metadata_str = ""
        if entity.metadata:
            metadata_str = f" | metadata: {json.dumps(entity.metadata)}"
        print(f"  [{entity.type}] {entity.name}")
        print(f"    ID: {entity.id}")
        print(f"    Created: {entity.created_ts}{metadata_str}")
        print()


def cmd_neighbors(entity_ref: str, direction: str = "outgoing", limit: int = 20, db_path: Optional[Path] = None):
    """Show neighbors of an entity (by ID or name)"""
    # If entity_ref looks like an ID (starts with "entity:" or is a UUID), use it directly
    if entity_ref.startswith("entity:") or ("-" in entity_ref and len(entity_ref) == 36):
        entity_id = entity_ref
        # Verify entity exists
        from memory.kg.api import get_entity
        entity = get_entity(entity_id, db_path=db_path)
        if not entity:
            print(f"No entity found with ID '{entity_ref}'")
            return
        print(f"Found entity: [{entity.type}] {entity.name} ({entity_id})")
    else:
        # Search for entity by name
        results = search_entities(name=entity_ref, limit=1, db_path=db_path)
        if not results:
            print(f"No entity found matching '{entity_ref}'")
            return
        entity_id = results[0].id
        print(f"Found entity: [{results[0].type}] {results[0].name} ({entity_id})")
    
    # Get neighbors
    edges_and_entities = neighbors(
        entity_id=entity_id,
        direction=direction,
        limit=limit,
        db_path=db_path,
    )
    
    print(f"\n{direction.capitalize()} relationships (limit={limit}):")
    print("-" * 80)
    
    if not edges_and_entities:
        print("No relationships found.")
        return
    
    for edge, neighbor in edges_and_entities:
        evidence_str = ""
        if edge.evidence:
            memory_id = edge.evidence.get("memory_id", "")
            source = edge.evidence.get("src", "")
            if memory_id or source:
                evidence_str = f" [evidence: memory_id={memory_id}, src={source}]"
        
        print(f"  --[{edge.predicate}]--> [{neighbor.type}] {neighbor.name}")
        print(f"    Weight: {edge.weight:.2f} | Created: {edge.created_ts}{evidence_str}")
        print()


def cmd_export(output_path: str, db_path: Optional[Path] = None):
    """Export KG to JSON file"""
    snapshot = export_snapshot(db_path=db_path)
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    print(f"Exported {len(snapshot['entities'])} entities and {len(snapshot['edges'])} edges to {output_path}")


def cmd_import(input_path: str, merge: bool = False, db_path: Optional[Path] = None):
    """Import KG from JSON file"""
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: File not found: {input_path}")
        return
    
    with open(input_file, 'r') as f:
        snapshot = json.load(f)
    
    import_snapshot(snapshot, merge=merge, db_path=db_path)
    
    action = "Merged" if merge else "Imported"
    print(f"{action} {len(snapshot['entities'])} entities and {len(snapshot['edges'])} edges from {input_path}")


def cmd_rebuild_from_memory(db_path: Optional[Path] = None, dry_run: bool = False):
    """Rebuild KG by re-extracting from all stored memories"""
    print("Rebuilding Knowledge Graph from stored memories...")
    print("-" * 80)
    
    if not dry_run:
        # Clear existing KG
        store = KnowledgeGraphStore(db_path=db_path)
        conn = sqlite3.connect(store.db_path)
        try:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM entities")
            conn.commit()
        finally:
            conn.close()
        print("Cleared existing KG data.")
    
    # Query all memories from backend
    repo_root = repo_root_from_file()
    backend = get_backend(repo_root)
    memories = backend.list_short_term()
    print(f"Found {len(memories)} memory items to process.")
    
    entity_count = 0
    edge_count = 0
    
    for i, memory in enumerate(memories, 1):
        if i % 50 == 0:
            print(f"  Processed {i}/{len(memories)} memories...")
        
        # Convert MemoryItem to dict for extraction
        memory_dict = {
            "id": memory.id,
            "content": memory.content,
            "type": memory.type,
            "ts": memory.ts,
            "tags": memory.tags,
            "agent": getattr(memory, "agent", "unknown"),
            "source": getattr(memory, "source", "unknown"),
        }
        
        # Extract entities and edges
        entities, edges = extract_entities_and_edges(memory_dict)
        
        if dry_run:
            entity_count += len(entities)
            edge_count += len(edges)
            continue
        
        # Upsert entities
        from memory.kg.api import upsert_entity, upsert_edge
        entity_id_map = {}
        
        for entity in entities:
            entity_id = upsert_entity(
                type=entity.type,
                name=entity.name,
                metadata=entity.metadata,
                db_path=db_path,
            )
            entity_id_map[entity.id] = entity_id
            # Also map type:normalized_name format
            from memory.kg.schema import _normalize_name
            key = f"{entity.type}:{_normalize_name(entity.name)}"
            entity_id_map[key] = entity_id
            entity_count += 1
        
        # Upsert edges
        for edge in edges:
            # Resolve IDs
            subject_id = entity_id_map.get(edge.subject_id)
            object_id = entity_id_map.get(edge.object_id)
            
            if not subject_id or not object_id:
                logger.debug(f"Skipping edge {edge.predicate}: missing subject or object")
                continue
            
            upsert_edge(
                subject_id=subject_id,
                predicate=edge.predicate,
                object_id=object_id,
                weight=edge.weight,
                evidence=edge.evidence,
                db_path=db_path,
            )
            edge_count += 1
    
    print("-" * 80)
    if dry_run:
        print(f"[DRY RUN] Would extract {entity_count} entities and {edge_count} edges")
    else:
        print(f"✓ Rebuild complete: {entity_count} entities, {edge_count} edges")


def main():
    """CLI entrypoint"""
    parser = argparse.ArgumentParser(
        description="Milton Knowledge Graph CLI - Inspect and manage the knowledge graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show statistics
  python -m memory.kg_cli --stats
  
  # Search for entities
  python -m memory.kg_cli --search "meshalyzer"
  python -m memory.kg_cli --search "python" --type tool
  
  # Show entity relationships
  python -m memory.kg_cli --neighbors "entity:user:primary"
  python -m memory.kg_cli --neighbors "Python" --direction incoming
  
  # Export/import
  python -m memory.kg_cli --export kg_backup.json
  python -m memory.kg_cli --import kg_backup.json --merge
  
  # Rebuild from memories
  python -m memory.kg_cli --rebuild-from-memory
  python -m memory.kg_cli --rebuild-from-memory --dry-run

Environment Variables:
  STATE_DIR or MILTON_STATE_DIR  Directory for KG database (default: ~/.local/state/milton)
        """,
    )
    
    # Command options (mutually exclusive)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--stats", action="store_true", help="Show KG statistics")
    commands.add_argument("--search", metavar="TERM", help="Search for entities by name")
    commands.add_argument("--neighbors", metavar="ENTITY", help="Show entity relationships (by ID or name)")
    commands.add_argument("--export", metavar="PATH", help="Export KG to JSON file")
    commands.add_argument("--import", metavar="PATH", dest="import_path", help="Import KG from JSON file")
    commands.add_argument("--rebuild-from-memory", action="store_true", help="Rebuild KG from stored memories")
    
    # Shared options
    parser.add_argument("--type", help="Filter by entity type (for --search)")
    parser.add_argument("--direction", choices=["outgoing", "incoming", "both"], default="outgoing",
                        help="Edge direction for --neighbors (default: outgoing)")
    parser.add_argument("--limit", type=int, default=20, help="Result limit (default: 20)")
    parser.add_argument("--merge", action="store_true", help="Merge on import (for --import)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode (for --rebuild-from-memory)")
    parser.add_argument("--db-path", type=Path, help="Override KG database path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    try:
        if args.stats:
            cmd_stats(db_path=args.db_path)
        elif args.search:
            cmd_search(term=args.search, entity_type=args.type, limit=args.limit, db_path=args.db_path)
        elif args.neighbors:
            cmd_neighbors(entity_ref=args.neighbors, direction=args.direction, limit=args.limit, db_path=args.db_path)
        elif args.export:
            cmd_export(output_path=args.export, db_path=args.db_path)
        elif args.import_path:
            cmd_import(input_path=args.import_path, merge=args.merge, db_path=args.db_path)
        elif args.rebuild_from_memory:
            cmd_rebuild_from_memory(db_path=args.db_path, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
