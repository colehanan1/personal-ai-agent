"""
Knowledge Graph context injection for NEXUS.

Enriches NEXUS context packets with structured entity and relationship data
from the Knowledge Graph, enabling "connected" answers about projects, goals,
tools, and people.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KGContextPacket:
    """Compact KG context packet for NEXUS injection.
    
    Structured summary of relevant entities and relationships,
    capped for token efficiency.
    """
    entities: List[Tuple[str, str]] = field(default_factory=list)  # [(name, type)]
    relationships: List[Tuple[str, str, str, str]] = field(default_factory=list)  # [(subj, pred, obj, evidence_id)]
    total_entities: int = 0
    total_edges: int = 0
    
    def to_prompt_section(self) -> str:
        """Format as compact prompt section for LLM context."""
        if not self.entities and not self.relationships:
            return ""
        
        lines = ["**Knowledge Graph Context:**"]
        
        if self.entities:
            # Show actual count displayed vs total
            displayed = min(len(self.entities), 10)
            lines.append(f"Entities ({displayed}/{self.total_entities}):")
            for name, etype in self.entities[:10]:  # Hard cap at 10 entities
                lines.append(f"  - {name} ({etype})")
        
        if self.relationships:
            # Show actual count displayed vs total
            displayed = min(len(self.relationships), 20)
            lines.append(f"Relationships ({displayed}/{self.total_edges}):")
            for subj, pred, obj, evidence in self.relationships[:20]:  # Hard cap at 20 edges
                if evidence:
                    lines.append(f"  - {subj} --{pred}--> {obj} [evidence: {evidence}]")
                else:
                    lines.append(f"  - {subj} --{pred}--> {obj}")
        
        return "\n".join(lines)
    
    def is_empty(self) -> bool:
        """Check if packet contains any data."""
        return len(self.entities) == 0 and len(self.relationships) == 0


def _is_kg_enabled() -> bool:
    """Check if KG context injection is enabled."""
    value = os.getenv("MILTON_KG_CONTEXT_ENABLED", "true")
    return value.lower() in ("1", "true", "yes", "on")


def _get_max_edges() -> int:
    """Get maximum edges to include in context."""
    try:
        return int(os.getenv("MILTON_KG_CONTEXT_MAX_EDGES", "20"))
    except ValueError:
        logger.warning("Invalid MILTON_KG_CONTEXT_MAX_EDGES, using default 20")
        return 20


def _get_max_chars() -> int:
    """Get maximum character length for KG context packet."""
    try:
        return int(os.getenv("MILTON_KG_CONTEXT_MAX_CHARS", "1500"))
    except ValueError:
        logger.warning("Invalid MILTON_KG_CONTEXT_MAX_CHARS, using default 1500")
        return 1500


def build_kg_context(query: str, top_k: int = 5) -> KGContextPacket:
    """
    Build KG context packet for NEXUS from user query.
    
    Process:
    1. Search entities matching query terms
    2. Take top K entities by relevance
    3. Expand 1-hop neighborhood
    4. Format as compact context packet
    
    Args:
        query: User query text
        top_k: Number of top entities to retrieve (default: 5)
        
    Returns:
        KGContextPacket with entities and relationships, or empty packet on failure
    """
    # Check if enabled
    if not _is_kg_enabled():
        logger.debug("KG context injection disabled")
        return KGContextPacket()
    
    try:
        from memory.kg.api import search_entities, neighbors
        from memory.kg.schema import Entity
        
        # Extract potential entity names from query
        # Simple approach: look for capitalized words and common nouns
        query_lower = query.lower()
        query_words = query.strip().split()
        
        # Search for entities matching query terms
        all_matches: List[Tuple[Entity, float]] = []  # (entity, score)
        
        # Try to match individual words
        for word in query_words:
            if len(word) < 3:  # Skip very short words
                continue
            matches = search_entities(name=word, limit=10)
            for entity in matches:
                # Simple scoring: how well the entity name matches
                name_lower = entity.name.lower()
                if name_lower == query_lower:
                    score = 1.0
                elif word.lower() in name_lower:
                    score = 0.8
                elif any(w.lower() in name_lower for w in query_words):
                    score = 0.6
                else:
                    score = 0.4
                all_matches.append((entity, score))
        
        # Also try full query as entity name
        full_matches = search_entities(name=query, limit=5)
        for entity in full_matches:
            all_matches.append((entity, 1.0))
        
        if not all_matches:
            logger.debug("No KG entities found for query")
            return KGContextPacket()
        
        # Deduplicate and sort by score
        seen_ids = set()
        unique_matches = []
        for entity, score in all_matches:
            if entity.id not in seen_ids:
                seen_ids.add(entity.id)
                unique_matches.append((entity, score))
        
        unique_matches.sort(key=lambda x: x[1], reverse=True)
        top_entities = [e for e, _ in unique_matches[:top_k]]
        
        # Build entity list
        entity_list = [(e.name, e.type) for e in top_entities]
        
        # Expand 1-hop neighborhood
        max_edges = _get_max_edges()
        relationship_list = []
        edge_count = 0
        
        for entity in top_entities:
            if edge_count >= max_edges:
                break
            
            # Get outgoing relationships
            try:
                outgoing = neighbors(entity.id, direction="outgoing", limit=10)
                for edge, target_entity in outgoing:
                    if edge_count >= max_edges:
                        break
                    
                    # Extract evidence ID from edge evidence if available
                    evidence_id = ""
                    if edge.evidence and isinstance(edge.evidence, dict):
                        evidence_id = edge.evidence.get("memory_id", "")
                    
                    relationship_list.append((
                        entity.name,
                        edge.predicate,
                        target_entity.name,
                        evidence_id
                    ))
                    edge_count += 1
            except Exception as e:
                logger.debug(f"Failed to get outgoing edges for {entity.name}: {e}")
            
            # Get incoming relationships
            if edge_count < max_edges:
                try:
                    incoming = neighbors(entity.id, direction="incoming", limit=5)
                    for edge, source_entity in incoming:
                        if edge_count >= max_edges:
                            break
                        
                        # Extract evidence ID
                        evidence_id = ""
                        if edge.evidence and isinstance(edge.evidence, dict):
                            evidence_id = edge.evidence.get("memory_id", "")
                        
                        relationship_list.append((
                            source_entity.name,
                            edge.predicate,
                            entity.name,
                            evidence_id
                        ))
                        edge_count += 1
                except Exception as e:
                    logger.debug(f"Failed to get incoming edges for {entity.name}: {e}")
        
        # Apply character limit
        max_chars = _get_max_chars()
        packet = KGContextPacket(
            entities=entity_list,
            relationships=relationship_list,
            total_entities=len(unique_matches),
            total_edges=edge_count,
        )
        
        # Check if packet exceeds character limit
        prompt_section = packet.to_prompt_section()
        if len(prompt_section) > max_chars:
            # First try truncating relationships
            while len(relationship_list) > 0 and len(packet.to_prompt_section()) > max_chars:
                relationship_list.pop()
                packet = KGContextPacket(
                    entities=entity_list,
                    relationships=relationship_list,
                    total_entities=len(unique_matches),
                    total_edges=edge_count,
                )
            
            # If still too long, truncate entities
            while len(entity_list) > 0 and len(packet.to_prompt_section()) > max_chars:
                entity_list.pop()
                packet = KGContextPacket(
                    entities=entity_list,
                    relationships=relationship_list,
                    total_entities=len(unique_matches),
                    total_edges=edge_count,
                )
        
        logger.debug(f"Built KG context: {len(entity_list)} entities, {len(relationship_list)} relationships")
        return packet
        
    except ImportError:
        # KG module not available
        logger.debug("KG module not available, skipping context injection")
        return KGContextPacket()
    except Exception as e:
        # Any other error - degrade gracefully
        logger.warning(f"Failed to build KG context: {e}")
        return KGContextPacket()
