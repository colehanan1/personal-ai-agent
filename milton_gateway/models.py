"""Pydantic models for OpenAI-compatible API requests and responses."""

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


# Request models
class ChatMessage(BaseModel):
    """A single message in a chat conversation."""
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = False
    user: Optional[str] = None
    conversation_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    client_id: Optional[str] = None
    # Additional params Open WebUI might send (ignored but accepted)
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[list[str] | str] = None


# Response models
class ChatCompletionChoice(BaseModel):
    """A single choice in a chat completion response."""
    index: int = 0
    message: ChatMessage
    finish_reason: Literal["stop", "length", "content_filter"] = "stop"


class UsageInfo(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# Streaming models
class DeltaContent(BaseModel):
    """Delta content for streaming responses."""
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    """A single choice in a streaming response chunk."""
    index: int = 0
    delta: DeltaContent
    finish_reason: Optional[Literal["stop", "length", "content_filter"]] = None


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming chunk."""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


# Models endpoint response
class ModelInfo(BaseModel):
    """Information about a single model."""
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "milton"


class ModelsResponse(BaseModel):
    """Response for /v1/models endpoint."""
    object: str = "list"
    data: list[ModelInfo]


# Error response
class ErrorDetail(BaseModel):
    """Error detail for API errors."""
    message: str
    type: str = "server_error"
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response."""
    error: ErrorDetail


# Declarative Memory models
class AddMemoryRequest(BaseModel):
    """Request to add a declarative memory."""
    content: str
    tags: list[str] = Field(default_factory=list)
    source: Literal["webui", "phone", "voice", "api"] = "api"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    context_ref: Optional[str] = None


class UpdateMemoryRequest(BaseModel):
    """Request to update a declarative memory."""
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    context_ref: Optional[str] = None


class MemoryResponse(BaseModel):
    """Response with a single declarative memory."""
    id: str
    content: str
    tags: list[str]
    source: str
    confidence: Optional[float]
    context_ref: Optional[str]
    created_at: int
    updated_at: int


class MemoryListResponse(BaseModel):
    """Response with a list of declarative memories."""
    memories: list[MemoryResponse]
    count: int


class MemoryOperationResponse(BaseModel):
    """Response for memory operations (add/update/delete)."""
    success: bool
    message: str
    memory_id: Optional[str] = None


# Activity Snapshot models
class AddSnapshotRequest(BaseModel):
    """Request to add an activity snapshot."""
    model_config = {"extra": "forbid"}  # Reject unknown fields
    
    device_id: str
    device_type: Literal["mac", "pc", "pi", "phone"]
    captured_at: int
    active_app: Optional[str] = None
    window_title: Optional[str] = None
    project_path: Optional[str] = None
    git_branch: Optional[str] = None
    recent_files: Optional[list[str]] = Field(default=None, max_length=10)
    notes: Optional[str] = Field(default=None, max_length=500)


class SnapshotResponse(BaseModel):
    """Response with a single activity snapshot."""
    id: str
    device_id: str
    device_type: str
    captured_at: int
    active_app: Optional[str]
    window_title: Optional[str]
    project_path: Optional[str]
    git_branch: Optional[str]
    recent_files: list[str]
    notes: Optional[str]
    created_at: int


class SnapshotListResponse(BaseModel):
    """Response with a list of activity snapshots."""
    snapshots: list[SnapshotResponse]
    count: int


class SnapshotOperationResponse(BaseModel):
    """Response for snapshot operations (add)."""
    success: bool
    message: str
    snapshot_id: Optional[str] = None
