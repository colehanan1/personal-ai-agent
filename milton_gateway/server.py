"""Milton Chat Gateway - OpenAI-compatible FastAPI server for Open WebUI integration."""

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .llm_client import LLMClient
from .models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    DeltaContent,
    ErrorDetail,
    ErrorResponse,
    ModelInfo,
    ModelsResponse,
    StreamChoice,
    UsageInfo,
)

logger = logging.getLogger(__name__)


# Configuration from environment
def get_config() -> dict:
    """Get gateway configuration from environment."""
    return {
        "host": os.getenv("MILTON_CHAT_HOST", "127.0.0.1"),
        "port": int(os.getenv("MILTON_CHAT_PORT", "8081")),
        "model_id": os.getenv("MILTON_CHAT_MODEL_ID", "milton-local"),
        "llm_api_url": os.getenv("LLM_API_URL", "http://localhost:8000"),
        "llm_model": os.getenv("LLM_MODEL", "llama31-8b-instruct"),
        "max_tokens_default": int(os.getenv("MILTON_CHAT_MAX_TOKENS", "1024")),
    }


# Default Milton system prompt for chat
MILTON_SYSTEM_PROMPT = """You are Milton, Cole's personal AI assistant.

You are concise, helpful, and action-oriented. You remember context within this conversation.
Respond directly without excessive preamble. Keep responses focused and practical.
If you don't know something, say so briefly rather than speculating at length.

Do NOT repeat yourself or ask variations of the same question multiple times.
Give ONE clear, complete response and then wait for user input."""


def load_system_prompt() -> str:
    """Load system prompt from file or use default."""
    prompt_path = os.getenv("MILTON_CHAT_SYSTEM_PROMPT")
    if prompt_path and os.path.exists(prompt_path):
        try:
            with open(prompt_path) as f:
                return f.read().strip()
        except Exception:
            pass
    return MILTON_SYSTEM_PROMPT


# Global LLM client instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create the LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Milton Chat Gateway starting up...")
    config = get_config()
    logger.info(f"Gateway config: host={config['host']}, port={config['port']}")
    logger.info(f"LLM backend: {config['llm_api_url']}, model={config['llm_model']}")
    yield
    # Cleanup
    if _llm_client is not None:
        await _llm_client.close()
    logger.info("Milton Chat Gateway shut down.")


# Create FastAPI app
app = FastAPI(
    title="Milton Chat Gateway",
    description="OpenAI-compatible Chat API for Open WebUI integration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for local LAN/Open WebUI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Convert exceptions to OpenAI-style error responses."""
    logger.exception(f"Unhandled error: {exc}")
    error = ErrorResponse(
        error=ErrorDetail(
            message=str(exc),
            type="server_error",
            code="internal_error",
        )
    )
    return JSONResponse(status_code=500, content=error.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTP exceptions to OpenAI-style error responses."""
    error = ErrorResponse(
        error=ErrorDetail(
            message=exc.detail,
            type="invalid_request_error" if exc.status_code < 500 else "server_error",
            code=str(exc.status_code),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=error.model_dump())


# Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_client = get_llm_client()
    llm_healthy = await llm_client.check_health()
    return {
        "status": "healthy" if llm_healthy else "degraded",
        "llm_backend": llm_healthy,
        "gateway": True,
    }


@app.get("/v1/models")
async def list_models() -> ModelsResponse:
    """List available models (OpenAI-compatible)."""
    config = get_config()
    model = ModelInfo(
        id=config["model_id"],
        object="model",
        created=int(time.time()),
        owned_by="milton",
    )
    return ModelsResponse(object="list", data=[model])


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Chat completions endpoint (OpenAI-compatible).

    Supports both streaming and non-streaming responses.
    """
    config = get_config()
    llm_client = get_llm_client()

    # Convert Pydantic messages to dicts
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Inject system prompt if not already present
    has_system = any(m["role"] == "system" for m in messages)
    if not has_system:
        system_prompt = load_system_prompt()
        messages.insert(0, {"role": "system", "content": system_prompt})
        logger.debug("Injected Milton system prompt")

    # Use default max_tokens if not specified
    max_tokens = request.max_tokens or config["max_tokens_default"]

    logger.info(
        f"Chat request: model={request.model}, messages={len(messages)}, "
        f"stream={request.stream}, max_tokens={max_tokens}"
    )

    if request.stream:
        return StreamingResponse(
            stream_chat_response(
                llm_client,
                messages,
                request.temperature,
                max_tokens,
                config["model_id"],
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
    else:
        return await blocking_chat_response(
            llm_client,
            messages,
            request.temperature,
            max_tokens,
            config["model_id"],
        )


async def blocking_chat_response(
    llm_client: LLMClient,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    model_id: str,
) -> ChatCompletionResponse:
    """Generate a non-streaming chat response."""
    try:
        result = await llm_client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        # Extract the assistant's response
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})

        return ChatCompletionResponse(
            model=model_id,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM API error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"LLM backend error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception(f"Chat completion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stream_chat_response(
    llm_client: LLMClient,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    model_id: str,
) -> AsyncIterator[str]:
    """
    Generate a streaming chat response using SSE.

    Yields OpenAI-compatible SSE events:
    - data: {chunk_json}
    - data: [DONE]
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    try:
        # First, send a role delta
        first_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_id,
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaContent(role="assistant", content=""),
                    finish_reason=None,
                )
            ],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        # Stream from LLM
        stream = await llm_client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for line in stream:
            if not line.startswith("data: "):
                continue

            data = line[6:]  # Remove "data: " prefix
            if data == "[DONE]":
                break

            try:
                chunk_data = json.loads(data)
                # Extract content delta from LLM response
                choices = chunk_data.get("choices", [])
                if choices and "delta" in choices[0]:
                    delta = choices[0]["delta"]
                    content = delta.get("content", "")
                    finish_reason = choices[0].get("finish_reason")

                    if content or finish_reason:
                        chunk = ChatCompletionChunk(
                            id=completion_id,
                            created=created,
                            model=model_id,
                            choices=[
                                StreamChoice(
                                    index=0,
                                    delta=DeltaContent(content=content if content else None),
                                    finish_reason=finish_reason,
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse streaming chunk: {data}")
                continue

        # Final chunk with finish_reason
        final_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_id,
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaContent(),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    except httpx.HTTPStatusError as e:
        logger.error(f"LLM streaming error: {e}")
        # Send error as final chunk
        error_chunk = {
            "error": {
                "message": f"LLM backend error: {e.response.status_code}",
                "type": "server_error",
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception(f"Streaming failed: {e}")
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "server_error",
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


def create_app() -> FastAPI:
    """Factory function to create the FastAPI app."""
    return app


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    uvicorn.run(
        "milton_gateway.server:app",
        host=config["host"],
        port=config["port"],
        reload=False,
    )
