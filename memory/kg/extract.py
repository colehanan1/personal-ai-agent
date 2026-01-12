"""Entity and relation extraction from memory items.

Deterministic heuristic-based extraction that converts memory items
into KG entities and edges. No LLM calls - pure pattern matching.

Design:
- Extract entities: projects, people, tools, paths, dates, concepts
- Extract relations: works_on, prefers, decided, uses, references, located_at
- Never fail: log errors and return empty results
- Fast: <10ms per memory item
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

from .schema import Edge, Entity

logger = logging.getLogger(__name__)

# Stable user entity ID for all user-related relations
USER_ENTITY_ID = "entity:user:primary"
USER_ENTITY_TYPE = "person"
USER_ENTITY_NAME = "User"


def _clean_text(text: str) -> str:
    """Clean and normalize text for entity names."""
    return text.strip()


def _extract_project_names(content: str) -> list[str]:
    """Extract project names from content.
    
    Patterns:
    - "project X", "Project X"
    - Capitalized multi-word names after "working on", "building"
    - Tags like "project:name"
    """
    projects = []
    
    # Pattern: "project X" or "Project X"
    for match in re.finditer(r'\bproject\s+([A-Z][A-Za-z0-9_\s-]+)', content, re.IGNORECASE):
        name = match.group(1).strip()
        # Stop at common delimiters
        name = re.split(r'\s+using\s+|\s+with\s+|[.,!?\n]', name, maxsplit=1)[0].strip()
        if len(name) > 2:  # Skip very short names
            projects.append(name)
    
    # Extract from "working on X" or "building X" patterns
    for match in re.finditer(r'\b(?:working on|building)\s+([A-Z][\w\s-]+?)(?:\s+using|\s+with|[.,!?\n]|$)', content, re.IGNORECASE):
        name = match.group(1).strip()
        if len(name) > 2 and len(name) < 50:
            projects.append(name)
    
    return list(set(projects))


def _extract_tool_names(content: str) -> list[str]:
    """Extract tool/technology names from content.
    
    Known tools: Python, SQLite, Weaviate, Docker, Git, Postgres, etc.
    """
    # Common tools/technologies (expandable)
    known_tools = {
        "python", "javascript", "typescript", "java", "rust", "go",
        "sqlite", "postgres", "mysql", "mongodb", "redis",
        "weaviate", "docker", "kubernetes", "git", "github",
        "react", "vue", "angular", "flask", "django", "fastapi",
        "vscode", "vim", "emacs", "pycharm",
        "linux", "ubuntu", "macos", "windows"
    }
    
    tools = []
    content_lower = content.lower()
    
    for tool in known_tools:
        # Look for tool mentions (word boundaries)
        pattern = r'\b' + re.escape(tool) + r'\b'
        if re.search(pattern, content_lower):
            # Preserve capitalization from known_tools
            tools.append(tool.capitalize())
    
    return list(set(tools))


def _extract_file_paths(content: str) -> list[str]:
    """Extract file paths from content.
    
    Patterns:
    - /absolute/path/to/file
    - ./relative/path
    - ~/home/path
    - Windows paths C:\\path\\to\\file
    """
    paths = []
    
    # Unix-style paths
    for match in re.finditer(r'(?:^|\s)([~/.]?/?[\w\-./]+\.\w+)', content):
        path = match.group(1)
        if '/' in path or path.startswith('.'):
            paths.append(path)
    
    # Absolute paths
    for match in re.finditer(r'(/[\w\-./]+)', content):
        path = match.group(1)
        if path.count('/') >= 2:  # At least /dir/something
            paths.append(path)
    
    return list(set(paths))


def _extract_preference_relations(content: str, memory_id: str, timestamp: datetime) -> list[tuple[str, str, str, dict]]:
    """Extract preference relations from content.
    
    Patterns:
    - "I prefer X"
    - "prefer X over Y"
    - "like X"
    - "love X"
    
    Returns:
        List of (subject_id, predicate, object_name, evidence) tuples
    """
    relations = []
    content_lower = content.lower()
    
    # Pattern: "prefer X"
    prefer_matches = re.finditer(r'\bprefer(?:s)?\s+([^.,!?\n]+?)(?:\s+over|\s+to|[.,!?\n]|$)', content_lower)
    for match in prefer_matches:
        preference = _clean_text(match.group(1))
        if len(preference) > 2 and len(preference) < 100:
            relations.append((
                USER_ENTITY_ID,
                "prefers",
                preference,
                {"src": "memory", "memory_id": memory_id, "pattern": "prefer", "timestamp": timestamp.isoformat()}
            ))
    
    # Pattern: "I like X"
    like_matches = re.finditer(r'\b(?:I\s+)?like\s+([^.,!?\n]+?)(?:[.,!?\n]|$)', content_lower)
    for match in like_matches:
        liked = _clean_text(match.group(1))
        if len(liked) > 2 and len(liked) < 100:
            relations.append((
                USER_ENTITY_ID,
                "prefers",
                liked,
                {"src": "memory", "memory_id": memory_id, "pattern": "like", "timestamp": timestamp.isoformat()}
            ))
    
    return relations


def _extract_decision_relations(content: str, memory_id: str, timestamp: datetime) -> list[tuple[str, str, str, dict]]:
    """Extract decision relations from content.
    
    Patterns:
    - "decided to X"
    - "chose X"
    - "selected X"
    
    Returns:
        List of (subject_id, predicate, object_name, evidence) tuples
    """
    relations = []
    content_lower = content.lower()
    
    # Pattern: "decided to X"
    decided_matches = re.finditer(r'\bdecided?\s+to\s+([^.,!?\n]+?)(?:[.,!?\n]|$)', content_lower)
    for match in decided_matches:
        decision = _clean_text(match.group(1))
        if len(decision) > 2 and len(decision) < 100:
            relations.append((
                USER_ENTITY_ID,
                "decided",
                decision,
                {"src": "memory", "memory_id": memory_id, "pattern": "decided", "timestamp": timestamp.isoformat()}
            ))
    
    # Pattern: "chose X"
    chose_matches = re.finditer(r'\bchose\s+([^.,!?\n]+?)(?:[.,!?\n]|$)', content_lower)
    for match in chose_matches:
        choice = _clean_text(match.group(1))
        if len(choice) > 2 and len(choice) < 100:
            relations.append((
                USER_ENTITY_ID,
                "decided",
                choice,
                {"src": "memory", "memory_id": memory_id, "pattern": "chose", "timestamp": timestamp.isoformat()}
            ))
    
    return relations


def _extract_work_relations(content: str, memory_id: str, timestamp: datetime) -> list[tuple[str, str, str, dict]]:
    """Extract work/project relations from content.
    
    Patterns:
    - "working on X"
    - "work on X"
    - "building X"
    
    Returns:
        List of (subject_id, predicate, object_name, evidence) tuples
    """
    relations = []
    content_lower = content.lower()
    
    # Pattern: "working on X" or "work on X" (case-insensitive, capture original case)
    working_matches = re.finditer(r'\bwork(?:ing)?\s+on\s+([A-Z][\w\s-]+?)(?:[.,!?\n]|$)', content, re.IGNORECASE)
    for match in working_matches:
        project = _clean_text(match.group(1))
        # Stop at common delimiters
        project = re.split(r'\s+using\s+|\s+with\s+', project, maxsplit=1)[0].strip()
        if len(project) > 2 and len(project) < 100:
            relations.append((
                USER_ENTITY_ID,
                "works_on",
                project,
                {"src": "memory", "memory_id": memory_id, "pattern": "working_on", "timestamp": timestamp.isoformat()}
            ))
    
    # Pattern: "building X"
    building_matches = re.finditer(r'\bbuilding\s+([A-Z][\w\s-]+?)(?:[.,!?\n]|$)', content, re.IGNORECASE)
    for match in building_matches:
        project = _clean_text(match.group(1))
        project = re.split(r'\s+using\s+|\s+with\s+', project, maxsplit=1)[0].strip()
        if len(project) > 2 and len(project) < 100:
            relations.append((
                USER_ENTITY_ID,
                "works_on",
                project,
                {"src": "memory", "memory_id": memory_id, "pattern": "building", "timestamp": timestamp.isoformat()}
            ))
    
    return relations


def _extract_usage_relations(content: str, memory_id: str, timestamp: datetime, projects: list[str]) -> list[tuple[str, str, str, dict]]:
    """Extract tool usage relations.
    
    Patterns:
    - "use X" (if project context available)
    - "using X"
    
    Returns:
        List of (subject_id, predicate, object_name, evidence) tuples
    """
    relations = []
    content_lower = content.lower()
    
    # Pattern: "using X" or "use X"
    use_matches = re.finditer(r'\busing?\s+([A-Z][A-Za-z0-9]+)', content)
    for match in use_matches:
        tool = _clean_text(match.group(1))
        if len(tool) > 2:
            # If we have project context, create project->uses->tool
            if projects:
                for project in projects:
                    relations.append((
                        f"project:{project.lower()}",  # Project entity ID
                        "uses",
                        tool,
                        {"src": "memory", "memory_id": memory_id, "pattern": "using", "timestamp": timestamp.isoformat()}
                    ))
            else:
                # Otherwise user uses tool
                relations.append((
                    USER_ENTITY_ID,
                    "uses",
                    tool,
                    {"src": "memory", "memory_id": memory_id, "pattern": "using", "timestamp": timestamp.isoformat()}
                ))
    
    return relations


def extract_entities_and_edges(
    memory_item: dict[str, Any]
) -> tuple[list[Entity], list[tuple[str, str, str, float, dict]]]:
    """Extract entities and edges from a memory item.
    
    Args:
        memory_item: Memory item dict with keys: id, content, type, ts, tags, etc.
    
    Returns:
        Tuple of (entities, edges) where:
        - entities: List of Entity objects to upsert
        - edges: List of (subject_id, predicate, object_id, weight, evidence) tuples
    
    Note:
        Never raises exceptions - logs errors and returns empty results.
    """
    try:
        content = str(memory_item.get("content", ""))
        if not content.strip():
            return [], []
        
        memory_id = str(memory_item.get("id", "unknown"))
        memory_type = str(memory_item.get("type", "crumb"))
        timestamp = memory_item.get("ts", datetime.now())
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now()
        
        entities: list[Entity] = []
        edge_specs: list[tuple[str, str, str, float, dict]] = []
        
        # Always ensure user entity exists
        entities.append(Entity(
            id=USER_ENTITY_ID,
            type=USER_ENTITY_TYPE,
            name=USER_ENTITY_NAME,
            metadata={"description": "Primary user of the system"}
        ))
        
        # Extract project names
        projects = _extract_project_names(content)
        for project_name in projects:
            entities.append(Entity(
                type="project",
                name=project_name,
                metadata={"source": "memory_extraction", "memory_id": memory_id}
            ))
        
        # Extract tool names
        tools = _extract_tool_names(content)
        for tool_name in tools:
            entities.append(Entity(
                type="tool",
                name=tool_name,
                metadata={"source": "memory_extraction", "memory_id": memory_id}
            ))
        
        # Extract file paths
        paths = _extract_file_paths(content)
        for path in paths:
            entities.append(Entity(
                type="path",
                name=path,
                metadata={"source": "memory_extraction", "memory_id": memory_id}
            ))
        
        # Extract relations based on memory type and content patterns
        
        # Preference relations
        if memory_type in ("preference", "fact", "crumb"):
            pref_relations = _extract_preference_relations(content, memory_id, timestamp)
            for subj_id, pred, obj_name, evidence in pref_relations:
                # Create entity for preference object
                entities.append(Entity(
                    type="concept",
                    name=obj_name,
                    metadata={"source": "preference", "memory_id": memory_id}
                ))
                edge_specs.append((subj_id, pred, f"concept:{obj_name.lower()}", 0.7, evidence))
        
        # Decision relations
        if memory_type in ("decision", "fact", "crumb"):
            decision_relations = _extract_decision_relations(content, memory_id, timestamp)
            for subj_id, pred, obj_name, evidence in decision_relations:
                entities.append(Entity(
                    type="decision",
                    name=obj_name,
                    metadata={"source": "decision", "memory_id": memory_id}
                ))
                edge_specs.append((subj_id, pred, f"decision:{obj_name.lower()}", 0.8, evidence))
        
        # Work/project relations
        if memory_type in ("project", "crumb", "fact"):
            work_relations = _extract_work_relations(content, memory_id, timestamp)
            for subj_id, pred, obj_name, evidence in work_relations:
                # Create project entity if not already extracted
                if obj_name not in projects:
                    entities.append(Entity(
                        type="project",
                        name=obj_name,
                        metadata={"source": "work_relation", "memory_id": memory_id}
                    ))
                edge_specs.append((subj_id, pred, f"project:{obj_name.lower()}", 0.8, evidence))
        
        # Tool usage relations
        usage_relations = _extract_usage_relations(content, memory_id, timestamp, projects)
        for subj_id, pred, obj_name, evidence in usage_relations:
            # Tool entity might already be extracted, that's fine (upsert handles it)
            edge_specs.append((subj_id, pred, f"tool:{obj_name.lower()}", 0.6, evidence))
        
        # Path reference relations
        for path in paths:
            edge_specs.append((
                f"memory:{memory_id}",
                "references",
                f"path:{path}",
                0.5,
                {"src": "memory", "memory_id": memory_id, "pattern": "path", "timestamp": timestamp.isoformat()}
            ))
        
        logger.debug(
            f"Extracted {len(entities)} entities and {len(edge_specs)} edges from memory {memory_id}"
        )
        
        return entities, edge_specs
    
    except Exception as exc:
        logger.warning(f"Error extracting entities/edges from memory: {exc}", exc_info=True)
        return [], []
