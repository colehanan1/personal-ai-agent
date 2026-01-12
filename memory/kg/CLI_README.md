# Knowledge Graph CLI

Command-line interface for inspecting and managing Milton's Knowledge Graph.

## Quick Start

```bash
# Show statistics
python -m memory.kg_cli --stats

# Search for entities
python -m memory.kg_cli --search "python"

# Show entity relationships
python -m memory.kg_cli --neighbors "entity:user:primary"

# Run interactive demo
python -m memory.kg_cli_demo
```

## Commands

### `--stats`

Show Knowledge Graph statistics including entity counts by type, edge counts by predicate, and database info.

```bash
python -m memory.kg_cli --stats
```

**Output:**
```
============================================================
Knowledge Graph Statistics
============================================================

Database: /home/user/.local/state/milton/kg.sqlite

Total Entities: 26
Total Edges: 23

--- Entities by Type ---
  concept             :     9
  project             :     7
  tool                :     6
  ...
```

### `--search "term"`

Search for entities by name (partial match, case-insensitive).

```bash
# Search all entities
python -m memory.kg_cli --search "python"

# Filter by type
python -m memory.kg_cli --search "python" --type tool

# Limit results
python -m memory.kg_cli --search "milton" --limit 5
```

**Output:**
```
Search results for 'python' (limit=20):
--------------------------------------------------------------------------------
  [tool] Python
    ID: 753a715c-6f2c-45ac-8c5f-3505cff0de21
    Created: 2026-01-12 03:23:04+00:00
    metadata: {"memory_id": "...", "source": "memory_extraction"}
```

### `--neighbors "<entity>"`

Show relationships of an entity (by ID or name).

```bash
# By entity ID
python -m memory.kg_cli --neighbors "entity:user:primary"

# By entity name (searches and uses first match)
python -m memory.kg_cli --neighbors "Python"

# Show incoming edges
python -m memory.kg_cli --neighbors "Python" --direction incoming

# Limit results
python -m memory.kg_cli --neighbors "entity:user:primary" --limit 10
```

**Output:**
```
Found entity: [person] User (entity:user:primary)

Outgoing relationships (limit=5):
--------------------------------------------------------------------------------
  --[prefers]--> [concept] tabs
    Weight: 0.70 | Created: 2026-01-12 03:21:42+00:00
    [evidence: memory_id=32c7bb04-..., src=memory]

  --[works_on]--> [project] Milton AI assistant project
    Weight: 0.80 | Created: 2026-01-12 03:23:04+00:00
    [evidence: memory_id=b4602642-..., src=memory]
```

**Direction options:**
- `outgoing` (default): Edges from the entity
- `incoming`: Edges to the entity
- `both`: All edges

### `--export <path>`

Export Knowledge Graph to JSON snapshot.

```bash
python -m memory.kg_cli --export kg_backup.json
```

**Output format:**
```json
{
  "version": "1.0",
  "exported_at": "2026-01-12T03:00:00Z",
  "entities": [
    {
      "id": "entity:user:primary",
      "type": "person",
      "name": "User",
      "normalized_name": "user",
      "metadata": {},
      "created_ts": "2026-01-10T10:00:00Z",
      "updated_ts": "2026-01-12T03:00:00Z"
    }
  ],
  "edges": [
    {
      "id": "edge:def456",
      "subject_id": "entity:user:primary",
      "predicate": "prefers",
      "object_id": "entity:abc123",
      "weight": 1.0,
      "evidence": {
        "memory_id": "mem_xyz",
        "src": "deterministic",
        "timestamp": "2026-01-10T10:00:00Z",
        "pattern": "prefers_x"
      },
      "created_ts": "2026-01-10T10:00:00Z"
    }
  ]
}
```

### `--import <path>`

Import Knowledge Graph from JSON snapshot.

```bash
# Replace existing KG (default)
python -m memory.kg_cli --import kg_backup.json

# Merge with existing KG
python -m memory.kg_cli --import kg_backup.json --merge
```

**Merge behavior:**
- Entities: Updates if `(normalized_name, type)` matches
- Edges: Updates weight (max of old/new) if `(subject, predicate, object)` matches

### `--rebuild-from-memory`

Rebuild Knowledge Graph by re-extracting from all stored memories.

```bash
# Actual rebuild (clears existing KG)
python -m memory.kg_cli --rebuild-from-memory

# Dry-run (simulate without changes)
python -m memory.kg_cli --rebuild-from-memory --dry-run
```

**Warning:** This clears the existing KG and re-extracts deterministically. LLM enrichment is not re-run.

**Output:**
```
Rebuilding Knowledge Graph from stored memories...
--------------------------------------------------------------------------------
Cleared existing KG data.
Found 150 memory items to process.
  Processed 50/150 memories...
  Processed 100/150 memories...
  Processed 150/150 memories...
--------------------------------------------------------------------------------
✓ Rebuild complete: 245 entities, 189 edges
```

## Options

### Global Options

- `--limit N`: Maximum results to return (default: 20)
- `--db-path PATH`: Custom database path (overrides STATE_DIR)
- `-v, --verbose`: Enable verbose logging
- `--help`: Show help message

### Direction Option (for `--neighbors`)

- `--direction outgoing`: Show edges from entity (default)
- `--direction incoming`: Show edges to entity
- `--direction both`: Show all edges

### Type Filter (for `--search`)

- `--type TYPE`: Filter by entity type (e.g., `tool`, `project`, `concept`)

### Merge Option (for `--import`)

- `--merge`: Merge imported KG with existing (default: replace)

### Dry-run Option (for `--rebuild-from-memory`)

- `--dry-run`: Simulate rebuild without modifying database

## Environment Variables

- `STATE_DIR` or `MILTON_STATE_DIR`: Directory for KG database
  - Default: `~/.local/state/milton`
  - Database file: `$STATE_DIR/kg.sqlite`

## Examples

### Inspect Production KG

```bash
# Get overview
python -m memory.kg_cli --stats

# Find specific entity
python -m memory.kg_cli --search "meshalyzer" --type project

# See what user prefers
python -m memory.kg_cli --neighbors "entity:user:primary" | grep prefers
```

### Backup and Restore

```bash
# Backup
python -m memory.kg_cli --export kg_backup_$(date +%Y%m%d).json

# Restore
python -m memory.kg_cli --import kg_backup_20260112.json
```

### Debug Entity Relationships

```bash
# Find entity
python -m memory.kg_cli --search "Python" --type tool

# Get ID from output (e.g., 753a715c-...)
export PYTHON_ID="753a715c-6f2c-45ac-8c5f-3505cff0de21"

# Show what uses Python
python -m memory.kg_cli --neighbors "$PYTHON_ID" --direction incoming

# Show what Python is used by
python -m memory.kg_cli --neighbors "$PYTHON_ID" --direction outgoing
```

### Rebuild After Memory Changes

```bash
# Check current state
python -m memory.kg_cli --stats

# Simulate rebuild
python -m memory.kg_cli --rebuild-from-memory --dry-run

# If simulation looks good, rebuild
python -m memory.kg_cli --rebuild-from-memory

# Verify
python -m memory.kg_cli --stats
```

## Troubleshooting

### "No entity found matching X"

Entity doesn't exist. Try:
```bash
# Search with more general term
python -m memory.kg_cli --search "pyth"

# Check all entities of that type
python -m memory.kg_cli --search "" --type tool --limit 100
```

### Empty database

```bash
python -m memory.kg_cli --stats
# Shows: Total Entities: 0, Total Edges: 0
```

Solution: Store some memories or rebuild:
```bash
python -m memory.kg_cli --rebuild-from-memory
```

### Permission denied

Database file is read-only or directory doesn't exist:
```bash
# Check path
python -m memory.kg_cli --stats
# Shows: Database: /path/to/kg.sqlite

# Fix permissions
chmod 644 /path/to/kg.sqlite
chmod 755 /path/to

# Or use custom path
python -m memory.kg_cli --stats --db-path /tmp/test_kg.sqlite
```

## Performance

- **Stats**: 5-15ms (SQLite aggregates)
- **Search**: 2-10ms (indexed LIKE queries)
- **Neighbors**: 3-15ms (indexed lookups)
- **Export**: 50-200ms (full table scan)
- **Import**: 100-500ms (bulk upserts)
- **Rebuild**: 2-5ms per memory

## Related Documentation

- **KG Specification**: `docs/KG_SPEC.md`
- **API Reference**: `memory/kg/README.md`
- **Phase Summaries**: `PHASE{1-5}_COMPLETION_SUMMARY.md`
- **Demo Script**: `python -m memory.kg_cli_demo`

## Implementation Notes

### Entity ID Formats

CLI accepts both:
- UUID format: `753a715c-6f2c-45ac-8c5f-3505cff0de21`
- Prefixed format: `entity:user:primary`

Detection: Checks for "entity:" prefix OR 36-character UUID with hyphens.

### Search Algorithm

Case-insensitive LIKE query on `normalized_name`:
```sql
SELECT * FROM entities 
WHERE normalized_name LIKE '%python%' 
  AND (type = 'tool' OR 'tool' IS NULL)
ORDER BY type, name 
LIMIT 20
```

### Rebuild Logic

1. Clear existing entities and edges
2. Query all memories from backend (`list_short_term()`)
3. Run deterministic extraction on each memory
4. Build entity ID mapping (UUID + type:name formats)
5. Upsert entities and resolve edge IDs
6. Upsert edges with resolved subject/object IDs

**Note:** LLM enrichment is NOT re-run during rebuild (deterministic only).
