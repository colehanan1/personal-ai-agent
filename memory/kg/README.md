# Knowledge Graph Module

A minimal, local-first knowledge graph for Milton's personalized memory system.

## Overview

The Knowledge Graph (KG) module provides structured storage for entities (people, projects, concepts, tools) and their relationships. It's designed to be:

- **Local-first**: SQLite storage in `STATE_DIR/kg.sqlite`
- **Independent**: No dependency on Weaviate or other services
- **Durable**: Supports export/import for backups and portability
- **Simple**: Clean Python API with minimal dependencies
- **Automatic**: Extracts entities/relations from memory writes (NEW!)

## Automatic Extraction

As of Phase 2, the KG automatically extracts entities and relationships from memory items using deterministic heuristics. As of Phase 3, optional LLM-based enrichment can propose additional entities and relationships.

### Deterministic Extraction (Always Enabled)

```python
from memory.schema import MemoryItem
from memory.store import add_memory

# Store a memory
item = MemoryItem(
    agent="NEXUS",
    type="preference",
    content="I prefer Python for backend development",
    tags=["tech"],
    importance=0.8,
    source="chat"
)

memory_id = add_memory(item)  # Automatically creates:
# - Entity: concept:python_for_backend_development
# - Entity: tool:python
# - Edge: user --prefers--> concept (weight=0.7)
```

### LLM Enrichment (Optional, Phase 3)

Enable LLM-based enrichment to discover implicit relationships:

```bash
export MILTON_KG_LLM_ENRICH_ENABLED=true
export MILTON_KG_LLM_ENRICH_MAX_EDGES=10  # default
```

With enrichment enabled, the LLM may discover additional entities and relationships not found by pattern matching:

```python
item = MemoryItem(
    agent="NEXUS",
    type="fact",
    content="Using FastAPI with Pydantic for API validation in microservices",
    tags=["tech"],
    importance=0.8,
    source="chat"
)

memory_id = add_memory(item)  # Creates deterministic + LLM entities:
# Deterministic: tool:FastAPI, tool:Pydantic
# LLM may add: concept:microservices, concept:API_validation
#             edges like FastAPI --enables--> microservices
```

**Important:** LLM enrichment:
- Is disabled by default (zero impact when off)
- Never blocks memory writes (failures are caught)
- Works offline (falls back to deterministic only)
- Validates and caps output (max edges, min confidence)
- Filters PII (rejects email/phone patterns)

See `memory/kg/LLM_ENRICHMENT_SUMMARY.md` for details.

### Extraction Patterns

**Preferences**: `"I prefer X"`, `"I like X"`
→ Creates `concept` entity + `prefers` edge

**Decisions**: `"decided to X"`, `"chose X"`
→ Creates `decision` entity + `decided` edge

**Project Work**: `"working on X"`, `"building X"`
→ Creates `project` entity + `works_on` edge

**Tool Usage**: `"using X"`, `"with X"`
→ Creates `tool` entity + `uses` edge

**File References**: `/path/to/file.py`
→ Creates `path` entity + `references` edge

### Performance

- **<15ms overhead** per memory write
- Never blocks writes (all errors caught and logged)
- Gracefully degrades if KG module unavailable

See `memory/kg/EXTRACTION_SUMMARY.md` for details.

## Storage Backend

- **Primary**: SQLite database (Python stdlib `sqlite3`)
- **Location**: Configured via `STATE_DIR` environment variable or defaults to `~/.local/state/milton/kg.sqlite`
- **Schema**: Two tables (entities, edges) with indexes for efficient queries
- **Auto-initialization**: Database and tables created automatically on first use

## API Reference

### Core Operations

```python
from memory.kg import upsert_entity, upsert_edge, neighbors

# Create entities
milton_id = upsert_entity(
    type="project",
    name="Milton",
    metadata={"description": "Personal AI agent"}
)

kg_id = upsert_entity(
    type="concept",
    name="Knowledge Graph"
)

# Create relationship
upsert_edge(
    subject_id=milton_id,
    predicate="uses",
    object_id=kg_id,
    weight=0.9,
    evidence={"src": "design_doc"}
)

# Query neighbors
for edge, entity in neighbors(milton_id):
    print(f"{edge.predicate} -> {entity.name}")
```

### Search and Retrieve

```python
from memory.kg import search_entities, get_entity

# Search by type
projects = search_entities(type="project")

# Search by name (partial match, case-insensitive)
milton_entities = search_entities(name="milton")

# Get by ID
entity = get_entity(entity_id)
```

### Export/Import

```python
from memory.kg import export_snapshot, import_snapshot
import json

# Export to JSON
snapshot = export_snapshot()
with open("kg_backup.json", "w") as f:
    json.dump(snapshot, f, indent=2)

# Import from JSON
with open("kg_backup.json") as f:
    snapshot = json.load(f)
import_snapshot(snapshot, merge=True)
```

## Data Model

### Entity

A node in the knowledge graph representing a person, project, concept, tool, etc.

**Fields:**
- `id`: Unique identifier (UUID)
- `type`: Entity type (e.g., "person", "project", "concept")
- `name`: Human-readable name
- `normalized_name`: Lowercased name for consistent lookups
- `metadata`: Arbitrary JSON data
- `created_ts`: Creation timestamp
- `updated_ts`: Last update timestamp

**Uniqueness**: Entities are unique by `(normalized_name, type)` pair. Upserting with the same name+type updates the existing entity.

### Edge

A directed relationship between two entities.

**Fields:**
- `id`: Unique identifier (UUID)
- `subject_id`: Entity ID of the subject
- `predicate`: Relationship type (e.g., "uses", "knows", "works_on")
- `object_id`: Entity ID of the object
- `weight`: Relationship strength (0.0-1.0)
- `evidence`: Provenance/evidence data (JSON)
- `created_ts`: Creation timestamp

**Uniqueness**: Edges are unique by `(subject_id, predicate, object_id)` triple. Multiple edges with different predicates can connect the same entities.

## Query Patterns

### Outgoing Relationships

```python
# What does Milton use?
for edge, entity in neighbors(milton_id, direction="outgoing", predicate="uses"):
    print(f"Uses: {entity.name}")
```

### Incoming Relationships

```python
# Who works on this project?
for edge, entity in neighbors(project_id, direction="incoming", predicate="works_on"):
    print(f"Worker: {entity.name}")
```

### Bidirectional

```python
# All connected entities
for edge, entity in neighbors(entity_id, direction="both"):
    print(f"{edge.predicate}: {entity.name}")
```

## Testing

Run the test suite:

```bash
pytest tests/test_kg.py -v
```

Run the demonstration:

```bash
python -m memory.kg.demo
```

## Design Decisions

1. **SQLite over JSON files**: Better performance for queries, ACID guarantees, indexes
2. **Normalized names**: Case-insensitive entity lookups for user convenience
3. **Upsert semantics**: Simplifies client code (no need to check existence)
4. **Weight field**: Enables confidence scoring and future ranking algorithms
5. **Evidence tracking**: Provenance for auditing and explanation
6. **No schema migration yet**: Single version, will add migrations when needed

## Future Enhancements

- **Entity extraction**: Automatic entity detection from memory items
- **Link prediction**: Suggest missing relationships based on patterns
- **Temporal queries**: Filter edges by time ranges
- **Graph analytics**: PageRank, community detection, centrality metrics
- **Vector similarity**: Connect to embeddings for semantic entity linking
- **Multi-user**: Add user/agent scoping to entities and edges

## Integration with Memory Tiers

The KG module is designed to complement existing memory tiers:

- **Short-term memory**: Unstructured conversation fragments
- **Working memory**: Active context for current task
- **Long-term memory**: Summarized facts and preferences
- **Knowledge Graph**: Structured entities and relationships

KG provides a **structured layer** on top of unstructured/semi-structured memories, enabling:
- Entity-centric queries ("tell me about Project X")
- Relationship traversal ("what tools does this project use?")
- Graph-based reasoning ("how are these concepts connected?")

Future work will add **automatic entity extraction** from memory items to populate the KG.
