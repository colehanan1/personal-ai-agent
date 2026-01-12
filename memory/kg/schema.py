"""Knowledge Graph data model and types.

A minimal, local-first knowledge graph for storing entities (people, projects, 
concepts) and their relationships. Designed to be independent of Weaviate and 
other memory tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def _now_utc() -> datetime:
    """Current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


def _normalize_name(name: str) -> str:
    """Normalize entity name for consistent lookups (lowercase, trimmed)."""
    return name.strip().lower()


@dataclass
class Entity:
    """A node in the knowledge graph (person, project, concept, etc)."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""  # e.g., "person", "project", "concept", "tool"
    name: str = ""
    normalized_name: str = field(init=False)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_ts: datetime = field(default_factory=_now_utc)
    updated_ts: datetime = field(default_factory=_now_utc)
    
    def __post_init__(self) -> None:
        """Set normalized name after initialization."""
        self.normalized_name = _normalize_name(self.name)


@dataclass
class Edge:
    """A directed relationship between two entities."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    subject_id: str = ""  # entity ID of the subject
    predicate: str = ""   # relationship type: "works_on", "uses", "knows", etc
    object_id: str = ""   # entity ID of the object
    weight: float = 1.0   # relationship strength/confidence (0.0-1.0)
    evidence: dict[str, Any] = field(default_factory=dict)  # provenance info
    created_ts: datetime = field(default_factory=_now_utc)
    
    def __post_init__(self) -> None:
        """Validate edge fields."""
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"Edge weight must be 0.0-1.0, got {self.weight}")
