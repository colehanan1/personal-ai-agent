# Agent Context Rules

This document defines how NEXUS builds context packets and when agents should
use memory versus ask the user.

## When To Retrieve Memory

- Always build a context packet for user-facing requests.
- Use only evidence-backed memory items from `memory.retrieve`.
- Skip memory entirely if `MILTON_MEMORY_ENABLED=false`.

## Evidence + Citations

- Each context bullet must include evidence ids.
- If there is no evidence, do not include the memory bullet.
- When referencing a memory fact in responses, cite its evidence id (e.g., `[mem-123]`).

## Unknowns / Assumptions

- Always include an explicit unknowns/assumptions section.
- If memory is empty, say so rather than guessing.
- Keep assumptions minimal and clearly labeled.

## Ask vs Proceed

- Ask a clarifying question if the request depends on missing user preferences.
- Proceed only when the request is actionable without extra context.
- Never invent project status, preferences, or facts without evidence ids.

## Tool Registry

- Tool registry lives in `agents/tool_registry.py`.
- Register external tools via `agents.tool_registry.register_tool(...)`.
- NEXUS pulls tools from the shared registry at startup.
