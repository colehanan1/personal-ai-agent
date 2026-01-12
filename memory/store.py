"""Storage API for Milton memory."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from .backends import get_backend
from .schema import MemoryItem, UserProfile

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def add_memory(
    item: MemoryItem, *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> str:
    """Add a memory item to short-term storage.
    
    After successful storage, automatically extracts entities and relations
    to populate the knowledge graph. Extraction failures are logged but never
    block memory writes.
    """
    if not isinstance(item, MemoryItem):
        item = MemoryItem.model_validate(item)
    backend = backend or get_backend(repo_root=repo_root)
    memory_id = backend.append_short_term(item)
    
    # Extract entities/edges and populate KG (async, best-effort)
    _enrich_knowledge_graph(item, memory_id)
    
    return memory_id


def _enrich_knowledge_graph(item: MemoryItem, memory_id: str) -> None:
    """Extract entities/edges from memory item and populate KG.
    
    Uses deterministic pattern extraction first, then optionally enhances
    with LLM-based enrichment if MILTON_KG_LLM_ENRICH_ENABLED=true.
    
    Never raises exceptions - logs errors and continues.
    
    Args:
        item: Memory item to extract from
        memory_id: ID of the stored memory item
    """
    try:
        from .kg.extract import extract_entities_and_edges
        from .kg.api import upsert_entity, upsert_edge
        from .kg.enrich_llm import propose_graph_updates
        
        # Convert MemoryItem to dict for extractors
        memory_dict = {
            "id": memory_id,
            "content": item.content,
            "type": item.type,
            "ts": item.ts,
            "tags": item.tags,
            "agent": item.agent,
            "source": item.source,
        }
        
        # Phase 1: Deterministic pattern extraction (always runs)
        entities, edge_specs = extract_entities_and_edges(memory_dict)
        
        # Phase 2: Optional LLM enrichment (gated behind env flag)
        try:
            llm_updates = propose_graph_updates(memory_dict)
            # Merge LLM-proposed entities
            for llm_entity in llm_updates.get("entities", []):
                # Convert to Entity-like dict for processing
                from .kg.schema import Entity
                ent = Entity(
                    id="",  # Will be generated
                    type=llm_entity["type"],
                    name=llm_entity["name"],
                    metadata={
                        "source": "llm_enrichment",
                        "aliases": llm_entity.get("aliases", []),
                        **llm_entity.get("metadata", {}),
                    },
                    created_ts=_now_utc(),
                    updated_ts=_now_utc(),
                )
                entities.append(ent)
            
            # Merge LLM-proposed edges (as edge specs)
            for llm_edge in llm_updates.get("edges", []):
                # Create edge spec tuple: (subj_id, predicate, obj_id, weight, evidence)
                from .kg.schema import _normalize_name
                subj_key = f"{llm_edge['subject_type']}:{_normalize_name(llm_edge['subject_name'])}"
                obj_key = f"{llm_edge['object_type']}:{_normalize_name(llm_edge['object_name'])}"
                evidence = {
                    "memory_id": memory_id,
                    "src": "llm_enrichment",
                    "timestamp": _now_utc().isoformat(),
                    "reason": llm_edge.get("reason_short", ""),
                }
                edge_specs.append((subj_key, llm_edge["predicate"], obj_key, llm_edge["weight"], evidence))
        except Exception as llm_exc:
            logger.debug(f"LLM enrichment phase failed (continuing with deterministic only): {llm_exc}")
        
        if not entities and not edge_specs:
            return  # Nothing to add
        
        # Upsert entities first (to ensure they exist for edges)
        entity_id_map = {}  # Map from type:name to actual UUID
        for entity in entities:
            try:
                # Use custom ID if provided (e.g., USER_ENTITY_ID)
                actual_id = upsert_entity(
                    type=entity.type,
                    name=entity.name,
                    metadata=entity.metadata,
                    entity_id=entity.id if entity.id.startswith("entity:") else None
                )
                # Map both the entity ID and type:normalized_name to actual ID
                entity_id_map[entity.id] = actual_id
                # Also map type:normalized_name format used in edge_specs
                from .kg.schema import _normalize_name
                normalized_key = f"{entity.type}:{_normalize_name(entity.name)}"
                entity_id_map[normalized_key] = actual_id
            except Exception as exc:
                logger.debug(f"Failed to upsert entity {entity.name}: {exc}")
                continue
        
        # Create edges
        for subj_id, predicate, obj_id, weight, evidence in edge_specs:
            try:
                # Resolve actual entity IDs (or use as-is if not in map)
                actual_subj = entity_id_map.get(subj_id, subj_id)
                actual_obj = entity_id_map.get(obj_id, obj_id)
                
                upsert_edge(
                    subject_id=actual_subj,
                    predicate=predicate,
                    object_id=actual_obj,
                    weight=weight,
                    evidence=evidence
                )
            except Exception as exc:
                logger.debug(f"Failed to upsert edge {subj_id}->{predicate}->{obj_id}: {exc}")
                continue
        
        logger.debug(f"KG enrichment: {len(entities)} entities, {len(edge_specs)} edges from memory {memory_id}")
    
    except ImportError:
        # KG module not available - silently skip
        pass
    except Exception as exc:
        # Log but never fail memory write
        logger.warning(f"KG enrichment failed for memory {memory_id}: {exc}")
        pass


def get_user_profile(
    *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> UserProfile:
    """Return the latest user profile, or an empty profile."""
    backend = backend or get_backend(repo_root=repo_root)
    profile = backend.get_user_profile()
    if profile is None:
        profile = UserProfile()
    return profile


def upsert_user_profile(
    patch: dict, evidence_ids: list[str], *, repo_root: Optional[Path] = None, backend: Optional[Any] = None
) -> UserProfile:
    """Merge a profile patch with evidence and append as a new profile version."""
    if not evidence_ids:
        raise ValueError("evidence_ids must be provided for profile updates")

    backend = backend or get_backend(repo_root=repo_root)
    base = backend.get_user_profile() or UserProfile()

    allowed = {"preferences", "stable_facts", "do_not_assume"}
    unknown = set(patch) - allowed
    if unknown:
        raise ValueError(f"Unsupported profile fields: {sorted(unknown)}")

    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    updates = {key: _as_list(patch.get(key)) for key in allowed}

    merged = UserProfile(
        preferences=base.preferences + updates["preferences"],
        stable_facts=base.stable_facts + updates["stable_facts"],
        do_not_assume=base.do_not_assume + updates["do_not_assume"],
        last_updated=_now_utc(),
        evidence_ids=base.evidence_ids + evidence_ids,
    )
    return backend.upsert_user_profile(merged)
