"""Structured memory schemas for Milton."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator

MemoryType = Literal["fact", "preference", "project", "decision", "crumb"]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


class MemoryItem(BaseModel):
    """Atomic memory entry stored in short-term memory."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=_now_utc)
    agent: str = Field(min_length=1)
    type: MemoryType
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    request_id: Optional[str] = None

    @field_validator("ts")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        cleaned = _clean_list([str(item).strip().lower() for item in value or []])
        return cleaned


class UserProfile(BaseModel):
    """Long-term user profile summary."""

    model_config = ConfigDict(extra="forbid")

    preferences: list[str] = Field(default_factory=list)
    stable_facts: list[str] = Field(default_factory=list)
    do_not_assume: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=_now_utc)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("last_updated")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("preferences", "stable_facts", "do_not_assume", "evidence_ids")
    @classmethod
    def _clean_values(cls, value: list[str]) -> list[str]:
        return _clean_list(value or [])


class ProjectMemory(BaseModel):
    """Long-term project summary keyed by project tag."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(min_length=1)
    goals: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("goals", "blockers", "next_steps", "evidence_ids")
    @classmethod
    def _clean_values(cls, value: list[str]) -> list[str]:
        return _clean_list(value or [])
