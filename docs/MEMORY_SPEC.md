# Memory Spec

This document defines the deterministic memory API and storage rules.

## Memory Types

- `fact`: Stable truths about the user or system.
- `preference`: Explicit likes/dislikes or working preferences.
- `project`: Project-related goals or context.
- `decision`: Explicit choices that affect future actions.
- `crumb`: Recent conversation crumbs or ephemeral context.
- `request`: Inbound requests captured from ntfy/iPhone.
- `result`: Outputs and summaries with evidence links or paths.

## Retrieval Ranking Logic

### Deterministic Retrieval

`query_relevant(text, limit, recency_bias)` uses a deterministic token-based score:

- Token overlap between query and memory content/tags.
- Recency score: `1 / (1 + age_hours)`.
- Importance bonus: `importance * 0.15`.
- Final score: `(text_score * (1 - recency_bias)) + (recency_score * recency_bias) + importance_bonus`.
- Stable ties: higher importance, newer timestamp, then id.

`query_recent(hours, tags, limit)` filters by timestamp and tags.

### Hybrid Retrieval (Semantic + Deterministic)

`query_relevant_hybrid(text, limit, recency_bias, semantic_weight, mode)` combines semantic similarity with deterministic scoring:

**Semantic Tier**:
- Uses sentence-transformers model `all-MiniLM-L6-v2` (384-dim embeddings)
- Weaviate HNSW vector index for fast approximate nearest neighbor search
- Cosine similarity distance metric
- Embeddings cached locally in `STATE_DIR/embeddings_cache/`

**Hybrid Scoring**:
- Deterministic score (token overlap + recency + importance)
- Semantic score (cosine similarity between query and memory embeddings)
- Both scores normalized to [0, 1] range
- Final score: `(deterministic_score * (1 - semantic_weight)) + (semantic_score * semantic_weight)`
- Default `semantic_weight=0.5` for balanced hybrid

**Modes**:
- `mode="hybrid"` (default): Combines deterministic + semantic
- `mode="deterministic"`: Pure token-based (same as `query_relevant`)
- `mode="semantic"`: Pure semantic similarity

**Graceful Degradation**:
- Falls back to deterministic mode if embeddings unavailable
- Falls back if sentence-transformers not installed
- Falls back on Weaviate query errors

**Indexing**:
- Embeddings generated on-demand during storage
- Batch indexing available via `memory/index_embeddings.py`
- CLI: `python memory/index_embeddings.py [--dry-run] [--batch-size 32] [--force] [--stats]`

## Compression Schedule

`compress_short_to_long(cutoff_hours=48)`:

- Selects short-term items older than cutoff.
- Writes a long-term `UserProfile` update from non-project items.
- Writes `ProjectMemory` summaries for tags like `project:<name>`.
- Deletes compressed short-term entries.

## Provenance Rules

- No long-term summary without evidence.
- `UserProfile.evidence_ids` and `ProjectMemory.evidence_ids` must reference source
  `MemoryItem.id` values.
- `upsert_user_profile` rejects updates without evidence ids.
- `MemoryItem.evidence` stores supporting paths/URLs when available.

## Fail-safe Storage

- If Weaviate is unavailable, storage falls back to:
  - `data/memory/short_term.jsonl`
  - `data/memory/long_term.jsonl`
- JSONL records include a `record_type` and validated payload.

## Agent Hooks

- `MILTON_MEMORY_ENABLED` (default: true) toggles automatic agent hooks.
- `MILTON_MEMORY_STORE_RESPONSES` (default: false) stores assistant replies as crumbs.
- `MILTON_MEMORY_CONTEXT_LIMIT` and `MILTON_MEMORY_CONTEXT_MAX_CHARS` cap injected context.
