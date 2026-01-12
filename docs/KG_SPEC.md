# Knowledge Graph Specification

This document defines the structure, semantics, and operational rules for Milton's Knowledge Graph (KG) system.

## Overview

Milton's Knowledge Graph automatically extracts and maintains structured knowledge from memory items. It tracks entities (people, projects, tools, concepts) and their relationships, providing rich context to agents like NEXUS.

**Key Principles:**
- **Automatic**: Entities and edges extracted automatically during memory writes
- **Local-first**: SQLite backend, no external dependencies required
- **Never blocks**: KG enrichment failures don't block memory writes
- **Offline-capable**: Works without network access or LLM calls
- **Privacy-first**: No PII in entities, evidence-based provenance

## Entity Types

Entities represent concrete or abstract concepts mentioned in memories.

### Core Types

| Type | Description | Example Names |
|------|-------------|---------------|
| `user` | The primary user | "Primary User" |
| `project` | Software projects or work efforts | "Meshalyzer", "Milton", "PhD Research" |
| `tool` | Technologies, languages, frameworks | "Python", "Docker", "SQLite" |
| `file` | File paths or filesystem references | "/home/user/project/main.py" |
| `concept` | Abstract ideas or approaches | "Dark Mode", "Tabs vs Spaces" |
| `decision` | Explicit choices made | "Use SQLite for KG", "Deploy to prod" |

### Entity Schema

```python
@dataclass
class Entity:
    id: str              # UUID format: "entity:<uuid>"
    type: str            # One of the types above
    name: str            # Display name (original casing)
    normalized_name: str # Lowercase for lookups (auto-computed)
    metadata: dict       # Optional structured data
    created_ts: str      # ISO 8601 timestamp
    updated_ts: str      # ISO 8601 timestamp
```

**Special Entities:**
- `entity:user:primary`: Stable ID for the user, always created as edge subject

**Normalization:**
- Entity lookups use `normalized_name = name.strip().lower()`
- Uniqueness constraint: `(normalized_name, type)` must be unique
- Upsert semantics: existing entities updated with new metadata

## Predicate Types

Predicates define typed relationships between entities.

### Core Predicates

| Predicate | Subject Type | Object Type | Meaning | Example |
|-----------|--------------|-------------|---------|---------|
| `prefers` | user | tool, concept | User preference | User prefers Python |
| `decided` | user | decision | User made a choice | User decided "Use SQLite" |
| `works_on` | user | project | Active work | User works_on Meshalyzer |
| `uses` | user, project | tool | Tool usage | User uses Docker |
| `references` | project, decision | file | File reference | Meshalyzer references main.py |

**Edge Direction:**
- All edges have explicit direction: `subject --[predicate]--> object`
- Queries support `outgoing` (from subject), `incoming` (to object), or `both`

### Edge Schema

```python
@dataclass
class Edge:
    id: str              # UUID format: "edge:<uuid>"
    subject_id: str      # Source entity ID
    predicate: str       # Relationship type
    object_id: str       # Target entity ID
    weight: float        # Confidence score [0.0, 1.0]
    evidence: dict       # Provenance metadata
    created_ts: str      # ISO 8601 timestamp
```

**Evidence Structure:**

All edges include provenance metadata:

```json
{
  "memory_id": "mem_abc123",     // Source memory item ID
  "src": "deterministic",         // "deterministic" or "llm"
  "timestamp": "2026-01-12T03:00:00Z",
  "pattern": "prefers_x"          // Pattern name (deterministic only)
}
```

**Weight Semantics:**
- `1.0`: Explicit statement ("I prefer Python")
- `0.9`: Strong implication ("I always use Python")
- `0.8`: LLM high confidence
- `0.7`: Contextual inference
- `0.5`: Weak association (LLM minimum threshold)

## Extraction Pipeline

### Phase 1: Deterministic Extraction (Always On)

Pattern-based extraction using regex and heuristics:

**Project Patterns:**
- "working on X", "project X", "X project"
- Word boundary matching, title-cased output
- Example: "working on meshalyzer" → Entity(type="project", name="Meshalyzer")

**Tool Patterns:**
- Hardcoded known tools: Python, JavaScript, Docker, Git, SQLite, etc.
- Case-insensitive word boundary matching
- Example: "using python" → Entity(type="tool", name="Python")

**File Patterns:**
- Unix paths: starts with `/` or `./` or `../`
- Windows paths: contains `:\` or starts with `\\`
- Example: "/home/user/main.py" → Entity(type="file", name="/home/user/main.py")

**Preference Patterns:**
- "I prefer X", "I like X", "I enjoy X"
- Creates `user --[prefers]--> X` edge
- Weight: 1.0 (explicit statement)

**Decision Patterns:**
- "decided to X", "choosing X", "going with X"
- Creates Entity(type="decision", name=X) and `user --[decided]--> X` edge
- Weight: 1.0 (explicit decision)

**Work Patterns:**
- "working on X", "building X", "developing X"
- Creates `user --[works_on]--> X` edge
- Weight: 0.9 (strong implication)

**Usage Patterns:**
- "using X", "with X", "via X"
- Creates `user --[uses]--> X` edge
- Weight: 0.8 (contextual usage)

### Phase 2: LLM Enrichment (Optional, Off by Default)

When enabled via `MILTON_KG_LLM_ENRICH_ENABLED=true`:

**LLM Prompt:**
- Receives memory content + extracted entities
- Asks for additional entities/edges in JSON schema
- Emphasizes "do not hallucinate, only extract what's explicit"

**Validation & Filtering:**
- Weight threshold: edges with weight < 0.5 rejected
- Edge cap: max 10 edges per memory (configurable via `MILTON_KG_LLM_ENRICH_MAX_EDGES`)
- PII filtering: rejects entities containing `@`, `.com`, `phone`, `email`, `address`
- JSON schema validation: strict schema enforcement

**Fallback:**
- LLM failures never block deterministic extraction
- Errors logged at debug/warning level
- Gracefully degrades to deterministic-only

### Integration

KG extraction happens in `memory/store.py::add_memory()`:

```python
def add_memory(...):
    # Store memory first
    memory_id = _write_to_storage(...)
    
    # Enrich KG (never blocks)
    try:
        _enrich_knowledge_graph(memory_id, content, tags, ...)
    except Exception as e:
        logger.debug(f"KG enrichment failed: {e}")
    
    return memory_id
```

**Performance:**
- Deterministic extraction: <10ms
- Entity/edge upserts: ~1ms total
- Total overhead: <15ms per memory write
- LLM enrichment (when enabled): 500-3000ms (async recommended)

## Storage Backend

### SQLite Schema

**entities table:**
```sql
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    metadata TEXT,  -- JSON blob
    created_ts TEXT NOT NULL,
    updated_ts TEXT NOT NULL,
    UNIQUE(normalized_name, type)
);

CREATE INDEX idx_entities_normalized_type ON entities(normalized_name, type);
CREATE INDEX idx_entities_type ON entities(type);
```

**edges table:**
```sql
CREATE TABLE edges (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    weight REAL NOT NULL,
    evidence TEXT,  -- JSON blob
    created_ts TEXT NOT NULL,
    UNIQUE(subject_id, predicate, object_id),
    FOREIGN KEY(subject_id) REFERENCES entities(id),
    FOREIGN KEY(object_id) REFERENCES entities(id)
);

CREATE INDEX idx_edges_subject ON edges(subject_id);
CREATE INDEX idx_edges_object ON edges(object_id);
CREATE INDEX idx_edges_predicate ON edges(predicate);
```

### Database Location

- Default: `~/.local/state/milton/kg.sqlite`
- Configurable via `STATE_DIR` or `MILTON_STATE_DIR` environment variables
- Auto-creates parent directories on first use

### Upsert Semantics

**Entity Upsert:**
- Unique key: `(normalized_name, type)`
- On conflict: updates `updated_ts`, merges `metadata`
- Returns existing or new entity ID

**Edge Upsert:**
- Unique key: `(subject_id, predicate, object_id)`
- On conflict: updates `weight` (max of old/new), merges `evidence`
- Preserves original `created_ts`

## Context Injection (NEXUS Integration)

When NEXUS builds context, it queries the KG for relevant entities and relationships.

### Query Flow

1. **Entity Search**: Search by name/tags with relevance scoring
   - Exact match: score 1.0
   - Partial match: score 0.7
   - Word match: score 0.5

2. **Neighborhood Expansion**: Get 1-hop neighbors
   - Outgoing edges: `entity --[predicate]--> neighbor`
   - Incoming edges: `neighbor --[predicate]--> entity`
   - Sorted by edge weight descending

3. **Capping**: Limit tokens to avoid context overflow
   - Max edges: 20 (configurable via `MILTON_KG_CONTEXT_MAX_EDGES`)
   - Max chars: 1500 (configurable via `MILTON_KG_CONTEXT_MAX_CHARS`)
   - Shows "displayed/total" counts for transparency

### Output Format

```
=== Knowledge Graph Context ===

Entities (5/10):
  [project] Meshalyzer (Score: 1.0)
  [tool] Python (Score: 0.7)
  ...

Relationships (8/15):
  [project] Meshalyzer --[uses]--> [tool] Python (weight: 0.9)
  User --[works_on]--> [project] Meshalyzer (weight: 0.9)
  ...

Evidence IDs: mem_abc123, mem_def456
```

### Configuration

```bash
# Disable KG context injection
export MILTON_KG_CONTEXT_ENABLED=false

# Adjust limits
export MILTON_KG_CONTEXT_MAX_EDGES=50
export MILTON_KG_CONTEXT_MAX_CHARS=3000
```

## CLI Tools

### Inspection Commands

```bash
# Show statistics (entity/edge counts, top predicates)
python -m memory.kg_cli --stats

# Search for entities
python -m memory.kg_cli --search "meshalyzer"
python -m memory.kg_cli --search "python" --type tool --limit 10

# Show entity relationships
python -m memory.kg_cli --neighbors "entity:user:primary"
python -m memory.kg_cli --neighbors "Python" --direction incoming

# Export/import
python -m memory.kg_cli --export kg_backup.json
python -m memory.kg_cli --import kg_backup.json --merge

# Rebuild KG from stored memories (deterministic only)
python -m memory.kg_cli --rebuild-from-memory
python -m memory.kg_cli --rebuild-from-memory --dry-run
```

### Export/Import Format

JSON snapshot with versioning:

```json
{
  "version": "1.0",
  "exported_at": "2026-01-12T03:00:00Z",
  "entities": [
    {
      "id": "entity:abc123",
      "type": "project",
      "name": "Meshalyzer",
      "normalized_name": "meshalyzer",
      "metadata": {},
      "created_ts": "2026-01-10T10:00:00Z",
      "updated_ts": "2026-01-12T03:00:00Z"
    }
  ],
  "edges": [
    {
      "id": "edge:def456",
      "subject_id": "entity:user:primary",
      "predicate": "works_on",
      "object_id": "entity:abc123",
      "weight": 0.9,
      "evidence": {
        "memory_id": "mem_xyz",
        "src": "deterministic",
        "timestamp": "2026-01-10T10:00:00Z",
        "pattern": "works_on"
      },
      "created_ts": "2026-01-10T10:00:00Z"
    }
  ]
}
```

## Privacy & Security

### PII Protection

**Entity-level:**
- No email addresses, phone numbers, or postal addresses
- LLM enrichment filters entities matching PII patterns
- Deterministic extraction avoids personal data by design

**Evidence-level:**
- Memory IDs provide provenance without exposing content
- Full memory content available via `memory.store.get_memory(id)`
- Never embed sensitive data in entity metadata

### Data Retention

- Entities persist indefinitely (no automatic expiry)
- Edges remain as long as both entities exist
- Manual cleanup via `--rebuild-from-memory` or `--import`

### Failure Modes

**Graceful Degradation:**
- KG unavailable → no context injection, agents continue normally
- Extraction fails → memory write succeeds, warning logged
- LLM enrichment fails → falls back to deterministic extraction

**Error Handling:**
- All KG operations wrapped in try/except
- Never propagates exceptions to memory writes
- Logs at debug/warning level for observability

## Performance Characteristics

### Deterministic Extraction
- Pattern matching: <10ms per memory
- Scales O(n) with content length
- No external dependencies

### Storage Operations
- Entity upsert: ~0.5ms (SQLite with indexes)
- Edge upsert: ~0.5ms
- Neighbor query: 1-5ms (indexed lookups)
- Entity search: 2-10ms (LIKE queries with indexes)

### LLM Enrichment (Optional)
- Prompt construction: <1ms
- LLM call: 500-3000ms (depends on model)
- Validation: <5ms
- **Recommendation**: Run async or disable in hot paths

### Context Injection
- Entity search: 2-10ms
- Neighborhood expansion: 3-15ms per entity
- Formatting: <1ms
- **Total**: 5-30ms typical, <50ms worst case

## Testing Strategy

### Unit Tests (tests/test_kg*.py)

- **Storage layer**: CRUD operations, upserts, indexes
- **Extraction**: Pattern matching for each entity/edge type
- **LLM enrichment**: Validation, filtering, mocking
- **Context injection**: Search scoring, capping, formatting

### Integration Tests

- **Memory integration**: End-to-end memory write → KG enrichment
- **NEXUS integration**: Context building with KG injection
- **CLI commands**: Stats, search, export/import

### Coverage

- 109 total tests across 4 phases
- 100% pass rate
- Zero breaking changes to existing functionality

## Future Extensions

### Potential Enhancements

1. **Temporal queries**: "What was I working on last week?"
2. **Graph algorithms**: PageRank for entity importance, community detection
3. **Multi-hop reasoning**: "Find all tools used in my projects"
4. **Confidence decay**: Lower weight over time for stale edges
5. **Conflict resolution**: Handle contradictory preferences
6. **Entity merging**: Deduplicate similar entities ("python" vs "Python3")

### Compatibility Guarantees

- Storage schema versioned (currently v1.0)
- API stability: functions won't change signatures
- Backward compatibility: new fields added as optional
- Migration scripts provided for schema changes

## References

- **Implementation**: `memory/kg/README.md`
- **Phase summaries**: `PHASE{1-4}_COMPLETION_SUMMARY.md`
- **API docs**: Docstrings in `memory/kg/api.py`
- **Demo scripts**: `memory/kg/demo.py`, `memory/kg/demo_llm.py`, `agents/demo_kg_nexus.py`
