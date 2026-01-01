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

`query_relevant(text, limit, recency_bias)` uses a deterministic score:

- Token overlap between query and memory content/tags.
- Recency score: `1 / (1 + age_hours)`.
- Importance bonus: `importance * 0.15`.
- Final score: `(text_score * (1 - recency_bias)) + (recency_score * recency_bias) + importance_bonus`.
- Stable ties: higher importance, newer timestamp, then id.

`query_recent(hours, tags, limit)` filters by timestamp and tags.

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
