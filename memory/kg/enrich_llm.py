"""
Optional LLM-based knowledge graph enrichment.

Proposes additional entities and edges beyond deterministic extraction.
Strictly gated behind environment flags, never required for KG operation.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# Environment flag configuration
def _is_llm_enrichment_enabled() -> bool:
    """Check if LLM enrichment is enabled via environment variable."""
    value = os.getenv("MILTON_KG_LLM_ENRICH_ENABLED", "false")
    return value.lower() in ("1", "true", "yes", "on")


def _get_max_edges() -> int:
    """Get maximum edges limit from environment, default 10."""
    try:
        return int(os.getenv("MILTON_KG_LLM_ENRICH_MAX_EDGES", "10"))
    except ValueError:
        logger.warning("Invalid MILTON_KG_LLM_ENRICH_MAX_EDGES, using default 10")
        return 10


def _get_llm_config() -> Dict[str, Any]:
    """Get LLM configuration from environment."""
    return {
        "url": os.getenv("LLM_API_URL", "http://localhost:8000"),
        "model": os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
        "api_key": (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        ),
        "timeout": 30,  # Shorter timeout for enrichment
    }


# Prompt template for entity/edge extraction
ENRICHMENT_PROMPT = """You are a knowledge graph enrichment assistant. Given a memory item, extract additional entities and relationships that go beyond simple pattern matching.

Focus on:
- Implicit relationships between concepts
- Semantic connections not captured by keywords
- Domain-specific entities (technologies, methodologies, etc.)
- Causal or temporal relationships

Avoid:
- Inferring unknown personal information (names, addresses, etc.)
- Speculating about facts not stated or implied
- Creating low-confidence edges (weight < 0.5)

Memory item:
Type: {memory_type}
Content: {content}
Tags: {tags}

Output valid JSON with this exact schema:
{{
  "entities": [
    {{"type": "concept|project|tool|decision|other", "name": "entity name", "aliases": ["optional", "list"], "metadata": {{"optional": "dict"}} }}
  ],
  "edges": [
    {{"subject_name": "entity1", "subject_type": "concept", "predicate": "relates_to|depends_on|part_of|enables|blocks|other", "object_name": "entity2", "object_type": "tool", "weight": 0.8, "reason_short": "why this edge exists"}}
  ]
}}

Output only JSON, no other text."""


def _call_llm(messages: List[Dict[str, str]], config: Dict[str, Any]) -> str:
    """
    Call LLM with error handling.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        config: LLM configuration dict
        
    Returns:
        LLM response text
        
    Raises:
        RuntimeError: If LLM call fails
    """
    url = f"{config['url']}/v1/chat/completions"
    headers = {}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    
    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": 1500,  # Reasonable limit for JSON output
        "temperature": 0.3,  # Lower temperature for structured output
    }
    
    try:
        response = requests.post(
            url, json=payload, timeout=config["timeout"], headers=headers
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot connect to LLM at {config['url']}: {e}")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"LLM request timed out after {config['timeout']}s")
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")


def _validate_and_sanitize(
    raw_output: str, max_edges: int
) -> Tuple[List[Dict], List[Dict]]:
    """
    Validate and sanitize LLM JSON output.
    
    Args:
        raw_output: Raw LLM response text
        max_edges: Maximum number of edges to return
        
    Returns:
        Tuple of (entities, edges) lists, both potentially empty if validation fails
    """
    try:
        # Extract JSON from response (handle markdown code blocks)
        json_str = raw_output.strip()
        if json_str.startswith("```"):
            # Remove markdown code fence
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            json_str = json_str.strip()
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
        
        data = json.loads(json_str)
        
        # Validate schema
        if not isinstance(data, dict):
            logger.warning("LLM output is not a dict, discarding")
            return [], []
        
        entities = data.get("entities", [])
        edges = data.get("edges", [])
        
        if not isinstance(entities, list) or not isinstance(edges, list):
            logger.warning("LLM output entities/edges not lists, discarding")
            return [], []
        
        # Validate and sanitize entities
        valid_entities = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if "type" not in ent or "name" not in ent:
                continue
            # Basic PII check: reject entities with suspicious patterns
            name = str(ent["name"]).lower()
            if any(pattern in name for pattern in ["@", ".com", "phone", "email", "address"]):
                logger.debug(f"Rejecting entity with potential PII: {ent['name']}")
                continue
            valid_entities.append({
                "type": str(ent["type"]),
                "name": str(ent["name"]),
                "aliases": [str(a) for a in ent.get("aliases", [])],
                "metadata": dict(ent.get("metadata", {})),
            })
        
        # Validate and sanitize edges
        valid_edges = []
        for edge in edges[:max_edges]:  # Hard cap
            if not isinstance(edge, dict):
                continue
            required = ["subject_name", "subject_type", "predicate", "object_name", "object_type"]
            if not all(k in edge for k in required):
                continue
            # Validate weight
            try:
                weight = float(edge.get("weight", 0.7))
                if weight < 0.5 or weight > 1.0:  # Enforce minimum confidence
                    logger.debug(f"Rejecting edge with weight {weight}")
                    continue
            except (ValueError, TypeError):
                continue
            
            valid_edges.append({
                "subject_name": str(edge["subject_name"]),
                "subject_type": str(edge["subject_type"]),
                "predicate": str(edge["predicate"]),
                "object_name": str(edge["object_name"]),
                "object_type": str(edge["object_type"]),
                "weight": weight,
                "reason_short": str(edge.get("reason_short", "")),
            })
        
        logger.debug(f"Validated {len(valid_entities)} entities, {len(valid_edges)} edges from LLM")
        return valid_entities, valid_edges
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM JSON output: {e}")
        return [], []
    except Exception as e:
        logger.warning(f"Error validating LLM output: {e}")
        return [], []


def propose_graph_updates(
    memory_item: Dict[str, Any], db_path: Optional[str] = None
) -> Dict[str, List]:
    """
    Propose additional KG entities and edges using LLM.
    
    This function is strictly optional and gated behind MILTON_KG_LLM_ENRICH_ENABLED.
    If disabled or if any error occurs, returns empty results.
    
    Args:
        memory_item: Dict representation of MemoryItem (must have 'type', 'content', 'tags')
        db_path: Optional database path (unused, for API consistency)
        
    Returns:
        Dict with keys:
            - "entities": List of entity dicts with {type, name, aliases?, metadata?}
            - "edges": List of edge dicts with {subject_name, subject_type, predicate, 
                       object_name, object_type, weight, reason_short}
        Returns {"entities": [], "edges": []} if disabled or on any error.
    """
    # Check if enrichment is enabled
    if not _is_llm_enrichment_enabled():
        logger.debug("LLM enrichment disabled, skipping")
        return {"entities": [], "edges": []}
    
    try:
        # Build prompt
        prompt = ENRICHMENT_PROMPT.format(
            memory_type=memory_item.get("type", "unknown"),
            content=memory_item.get("content", ""),
            tags=", ".join(memory_item.get("tags", [])),
        )
        
        messages = [{"role": "user", "content": prompt}]
        
        # Call LLM
        config = _get_llm_config()
        logger.debug(f"Calling LLM for KG enrichment (model: {config['model']})")
        raw_output = _call_llm(messages, config)
        
        # Validate and sanitize
        max_edges = _get_max_edges()
        entities, edges = _validate_and_sanitize(raw_output, max_edges)
        
        return {"entities": entities, "edges": edges}
        
    except Exception as e:
        # Never fail - log and return empty
        logger.debug(f"LLM enrichment failed (gracefully): {e}")
        return {"entities": [], "edges": []}
