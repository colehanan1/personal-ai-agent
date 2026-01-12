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
