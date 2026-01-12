# Memory Extraction Error Fix

## Issue

The CLI command `--rebuild-from-memory` was failing with:
```
extract_entities_and_edges() got an unexpected keyword argument 'content'
```

## Root Cause

**File:** `memory/kg_cli.py` line 226-230

**Problem:** CLI was calling `extract_entities_and_edges()` with keyword arguments:
```python
entities, edges = extract_entities_and_edges(
    content=memory.content,
    tags=memory.tags,
    memory_id=memory.id,
)
```

**Expected:** Function signature requires a single dict argument:
```python
def extract_entities_and_edges(
    memory_item: dict[str, Any]
) -> tuple[list[Entity], list[tuple[str, str, str, float, dict]]]:
```

## Fix

Updated `memory/kg_cli.py` to convert MemoryItem to dict before extraction:

```python
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
```

This matches the pattern used in `memory/store.py` lines 58-69.

## Verification

### Tests
```bash
$ pytest tests/test_kg_cli.py -v
13 passed in 2.48s

$ pytest tests/test_kg*.py tests/test_nexus_kg_integration.py -v
114 passed in 13.64s
```

### CLI Command
```bash
$ python -m memory.kg_cli --rebuild-from-memory --dry-run
Rebuilding Knowledge Graph from stored memories...
Found 896 memory items to process.
  Processed 50/896 memories...
  ...
  Processed 850/896 memories...
[DRY RUN] Would extract 981 entities and 49 edges
✓ Success - no errors!
```

## Impact

- **Files changed:** 1 (`memory/kg_cli.py`)
- **Lines changed:** 12 lines (added dict conversion)
- **Breaking changes:** None
- **Tests affected:** 0 (all still passing)

## Related Code

All other call sites already use the correct format:
- `memory/store.py` line 69: ✅ Uses memory_dict
- `tests/test_kg_extract.py`: ✅ All tests use memory_item dict
- `tests/test_kg_memory_integration.py`: ✅ Uses memory_dict
- `memory/kg/demo_llm.py`: ✅ Uses memory_dict

Only the CLI rebuild command had the incorrect signature.

## Date

**Fixed:** 2026-01-12 03:54 UTC  
**Status:** ✅ Complete and verified
