# Milton Memory System

Complete guide to Milton's hybrid memory system combining deterministic retrieval with semantic embeddings.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Memory Types](#memory-types)
- [Retrieval Modes](#retrieval-modes)
- [Semantic Embeddings](#semantic-embeddings)
- [Indexing Existing Data](#indexing-existing-data)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

---

## Overview

Milton's memory system provides:

1. **Deterministic Retrieval**: Token-based matching with recency and importance scoring
2. **Semantic Retrieval**: Neural embeddings for meaning-based similarity
3. **Hybrid Mode**: Combines both approaches for best results
4. **Graceful Degradation**: Works without embeddings when unavailable

### Architecture

```
┌─────────────────┐
│ Short-Term      │  Recent interactions (24-48h)
│ Memory          │  → Stored in Weaviate or JSONL
│                 │  → Optional semantic embeddings
└─────────────────┘
        ↓ compress_short_to_long()
┌─────────────────┐
│ Long-Term       │  Compressed summaries
│ Memory          │  → UserProfile
│                 │  → ProjectMemory
└─────────────────┘
```

---

## Quick Start

### 1. Basic Setup (No Embeddings)

The memory system works out-of-the-box with deterministic retrieval:

```bash
# Start Weaviate (optional, falls back to JSONL)
docker-compose up -d weaviate

# Initialize schema
python memory/init_db.py
```

### 2. Enable Semantic Embeddings (Recommended)

Install sentence-transformers for semantic search:

```bash
pip install sentence-transformers
```

This enables:
- Meaning-based similarity search
- Better results for conceptual queries
- Hybrid retrieval combining token + semantic scoring

### 3. Index Existing Data

Generate embeddings for existing memories:

```bash
# Dry run to see what would be indexed
python memory/index_embeddings.py --dry-run

# Index all memories without embeddings
python memory/index_embeddings.py

# Force re-indexing (regenerate all embeddings)
python memory/index_embeddings.py --force

# Show indexing statistics
python memory/index_embeddings.py --stats
```

---

## Memory Types

| Type | Description | Example |
|------|-------------|---------|
| `fact` | Stable truths about user/system | "User prefers Python over JavaScript" |
| `preference` | Explicit likes/dislikes | "User dislikes verbose logging" |
| `project` | Project context and goals | "Working on ML pipeline optimization" |
| `decision` | Explicit choices affecting future | "Decided to use PostgreSQL" |
| `crumb` | Recent conversation context | "User asked about API rate limits" |
| `request` | Inbound requests from ntfy/iPhone | "Remind me to call John at 3pm" |
| `result` | Outputs with evidence/paths | "Generated report at /tmp/report.pdf" |

---

## Retrieval Modes

### Deterministic Retrieval

```python
from memory.retrieve import query_relevant

# Token-based matching with recency bias
results = query_relevant(
    text="machine learning projects",
    limit=10,
    recency_bias=0.35  # Balance between relevance (0.0) and recency (1.0)
)
```

**Scoring**:
- Token overlap between query and memory content/tags
- Recency: `1 / (1 + age_hours)`
- Importance bonus: `importance * 0.15`
- Final: `(text_score * (1 - recency_bias)) + (recency_score * recency_bias) + importance_bonus`

### Hybrid Retrieval (Recommended)

```python
from memory.retrieve import query_relevant_hybrid

# Balanced hybrid: 50% deterministic + 50% semantic
results = query_relevant_hybrid(
    text="AI and deep learning research",
    limit=10,
    semantic_weight=0.5  # Default: balanced
)

# More weight on semantic similarity
results = query_relevant_hybrid(
    text="neural networks",
    semantic_weight=0.7,  # 70% semantic, 30% deterministic
    recency_bias=0.2      # Slightly favor relevance over recency
)

# Pure semantic search
results = query_relevant_hybrid(
    text="artificial intelligence concepts",
    mode="semantic"
)

# Pure deterministic (explicit)
results = query_relevant_hybrid(
    text="exact token match",
    mode="deterministic"
)
```

### Recent Memory Query

```python
from memory.retrieve import query_recent

# Get memories from last 24 hours
recent = query_recent(hours=24, limit=20)

# Filter by tags
projects = query_recent(
    hours=48,
    tags=["project:milton", "project:research"],
    limit=10
)
```

---

## Semantic Embeddings

### Model Details

- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Size**: ~80 MB
- **Dimensions**: 384
- **Speed**: Fast (CPU-friendly)
- **Quality**: Good for general-purpose semantic similarity

### How It Works

1. **Text → Vector**: Converts text to 384-dimensional embedding
2. **Normalization**: L2-normalized for cosine similarity
3. **Caching**: Embeddings cached in `STATE_DIR/embeddings_cache/`
4. **Indexing**: Stored in Weaviate with HNSW vector index

### Storage Locations

```
~/.local/state/milton/
├── embeddings_cache/           # Local embedding cache
│   ├── a1b2c3d4...npy         # Cached embeddings (SHA256 keys)
│   └── ...
└── credentials/                # OAuth tokens (calendar, etc.)
```

### Disk Usage

- Model: ~80 MB (downloaded once)
- Cache: ~1.5 KB per embedding
- Weaviate vectors: ~1.5 KB per memory item

---

## Indexing Existing Data

### CLI Tool

```bash
# Show current indexing status
python memory/index_embeddings.py --stats

# Output:
# === Embedding Index Statistics ===
# Total items: 1234
# With embeddings: 800 (64%)
# Without embeddings: 434
# Embedding dimension: 384
```

### Batch Indexing

```bash
# Index all items without embeddings
python memory/index_embeddings.py

# Custom batch size (default: 32)
python memory/index_embeddings.py --batch-size 64

# Force regenerate all embeddings
python memory/index_embeddings.py --force

# Dry run (show what would be done)
python memory/index_embeddings.py --dry-run
```

### Progress Tracking

```bash
$ python memory/index_embeddings.py
=== Milton Memory Embedding Indexer ===

Fetching memory items from Weaviate...
Found 1234 memory items
Items to process: 434

Generating embeddings (batch_size=32)...
  Processing batch 1/14... ✓ 32/32 updated
  Processing batch 2/14... ✓ 32/32 updated
  ...
  Processing batch 14/14... ✓ 18/18 updated

✅ Indexing complete
   Processed: 434 items
   Updated: 434 items
```

---

## Usage Examples

### Example 1: Find Similar Projects

```python
from memory.retrieve import query_relevant_hybrid

# Semantic search finds conceptually similar projects
results = query_relevant_hybrid(
    text="machine learning pipeline optimization",
    semantic_weight=0.7,  # Emphasize semantic similarity
    limit=5
)

for item in results:
    print(f"{item.content} (importance: {item.importance})")
```

### Example 2: Recent Context with Semantic Ranking

```python
# Combine recency with semantic similarity
results = query_relevant_hybrid(
    text="API authentication issues",
    recency_bias=0.8,      # Heavily favor recent memories
    semantic_weight=0.5,   # Balanced semantic + deterministic
    limit=10
)
```

### Example 3: Exact Token Match (Deterministic)

```python
# When you need exact token matching (e.g., code symbols)
results = query_relevant_hybrid(
    text="def calculate_metrics",
    mode="deterministic"  # Pure token-based
)
```

### Example 4: Graceful Degradation

```python
# Works even if sentence-transformers not installed
# Automatically falls back to deterministic mode
results = query_relevant_hybrid(
    text="AI research",
    mode="hybrid"  # Will use deterministic if embeddings unavailable
)
```

---

## Configuration

### Environment Variables

```bash
# Memory backend selection
export MILTON_MEMORY_BACKEND=weaviate  # or "jsonl"

# Weaviate connection
export WEAVIATE_URL=http://localhost:8080
export WEAVIATE_GRPC_PORT=50051

# State directory (for cache and credentials)
export STATE_DIR=~/.local/state/milton

# Memory behavior
export MILTON_MEMORY_ENABLED=true
export MILTON_MEMORY_STORE_RESPONSES=false
export MILTON_MEMORY_CONTEXT_LIMIT=10
export MILTON_MEMORY_CONTEXT_MAX_CHARS=2000
```

### Weaviate Schema

The `ShortTermMemory` collection includes:

```python
Properties:
- timestamp: DATE
- agent: TEXT
- content: TEXT  # Main content
- context: TEXT  # Additional context
- metadata: TEXT (JSON string)

Vector Index:
- Algorithm: HNSW
- Distance: cosine
- Dimensions: 384
- ef_construction: 128
- max_connections: 64
```

---

## Troubleshooting

### Embeddings Not Available

**Symptom**: Warning: "Embeddings not available, falling back to deterministic mode"

**Cause**: `sentence-transformers` not installed

**Fix**:
```bash
pip install sentence-transformers
```

### Model Download Slow

**Symptom**: First run takes several minutes

**Cause**: Downloading 80MB model from HuggingFace

**Fix**: Be patient on first run. Model is cached locally afterward.

### High Memory Usage

**Symptom**: Python process using >2GB RAM

**Cause**: Large batch size during indexing

**Fix**:
```bash
# Reduce batch size
python memory/index_embeddings.py --batch-size 16
```

### Weaviate Connection Failed

**Symptom**: "Semantic search failed" errors

**Cause**: Weaviate not running or connection issues

**Fix**:
```bash
# Check Weaviate status
docker-compose ps weaviate

# Restart Weaviate
docker-compose restart weaviate

# Verify connection
curl http://localhost:8080/v1/meta
```

### Cache Taking Too Much Space

**Symptom**: `embeddings_cache/` directory is large

**Fix**:
```python
from memory.embeddings import clear_cache, get_cache_stats

# Check cache size
stats = get_cache_stats()
print(f"Cache: {stats['count']} embeddings, {stats['size_mb']} MB")

# Clear cache (embeddings will be regenerated as needed)
clear_cache()
```

---

## Advanced Topics

### Custom Embedding Models

The default model (`all-MiniLM-L6-v2`) can be changed:

```python
from memory.embeddings import embed

# Use a different model
vector = embed("test text", model_name="sentence-transformers/all-mpnet-base-v2")
```

**Note**: Changing models requires re-indexing and updating Weaviate schema dimensions.

### Programmatic Indexing

```python
from memory.index_embeddings import index_embeddings

# Index with custom settings
processed, updated = index_embeddings(
    batch_size=64,
    dry_run=False,
    force=False
)

print(f"Processed {processed} items, updated {updated}")
```

### Performance Tuning

**HNSW Parameters** (in `memory/init_db.py`):

```python
# Build-time quality/speed tradeoff
ef_construction=128  # Higher = better quality, slower indexing

# Memory/quality tradeoff
max_connections=64   # Higher = better quality, more memory
```

**Query-time Parameters**:

```python
# Adjust semantic_weight based on query type
semantic_weight=0.3   # Favor deterministic for exact matches
semantic_weight=0.7   # Favor semantic for conceptual queries
```

### Hybrid Scoring Details

The hybrid score combines normalized deterministic and semantic scores:

```python
# Normalize to [0, 1]
norm_det = det_score / max_det_score
norm_sem = sem_score / max_sem_score

# Weighted combination
final_score = (norm_det * (1 - semantic_weight)) + (norm_sem * semantic_weight)
```

Tie-breaking: score → importance → timestamp → id

---

## Integration with Agents

### CORTEX Integration

```python
# In agents/cortex.py
from memory.retrieve import query_relevant_hybrid

# Use hybrid retrieval for context
context = query_relevant_hybrid(
    text=user_query,
    semantic_weight=0.6,  # Slightly favor semantic
    limit=10
)
```

### NEXUS Integration

```python
# In agents/nexus.py
from memory.retrieve import query_relevant_hybrid

# Retrieve relevant memories for briefing
memories = query_relevant_hybrid(
    text="today's tasks and projects",
    recency_bias=0.7,
    semantic_weight=0.5,
    limit=15
)
```

---

## See Also

- [MEMORY_SPEC.md](./MEMORY_SPEC.md) - Detailed technical specification
- [AGENTS.md](./AGENTS.md) - Agent system architecture
- Source code:
  - [memory/embeddings.py](../memory/embeddings.py) - Embedding generation
  - [memory/retrieve.py](../memory/retrieve.py) - Retrieval functions
  - [memory/index_embeddings.py](../memory/index_embeddings.py) - Batch indexing
  - [memory/init_db.py](../memory/init_db.py) - Weaviate schema

---

**Last Updated**: 2026-01-04
