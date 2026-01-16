"""Milton Chat Gateway - OpenAI-compatible FastAPI server for Open WebUI integration."""

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Mapping

from dotenv import load_dotenv

# Load environment variables from .env file
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env")

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .llm_client import LLMClient
from .command_processor import CommandProcessor, CommandResult
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

_SESSION_COOKIE_NAME = "milton_chat_session_id"
_THREAD_ID_FIELDS = (
    "conversation_id",
    "chat_id",
    "thread_id",
    "session_id",
    "client_id",
)
_THREAD_ID_HEADER_KEYS = (
    "x-conversation-id",
    "x-chat-id",
    "x-thread-id",
    "x-session-id",
    "x-client-id",
)


# Configuration from environment
def get_config() -> dict:
    """Get gateway configuration from environment."""
    return {
        "host": os.getenv("MILTON_CHAT_HOST", "0.0.0.0"),  # Bind to all interfaces for Tailscale access
        "port": int(os.getenv("MILTON_CHAT_PORT", "8081")),
        "model_id": os.getenv("MILTON_CHAT_MODEL_ID", "milton-local"),
        "llm_api_url": os.getenv("LLM_API_URL", "http://localhost:8000"),
        "llm_model": os.getenv("LLM_MODEL", "llama31-8b-instruct"),
        "max_tokens_default": int(os.getenv("MILTON_CHAT_MAX_TOKENS", "1024")),
        "milton_api_url": os.getenv("MILTON_API_URL", "http://localhost:8001"),
    }


# Default Milton system prompt for chat
MILTON_SYSTEM_PROMPT = """You are Milton, Cole's personal AI assistant.

You are concise, helpful, and action-oriented. You remember context within this conversation.
Respond directly without excessive preamble. Keep responses focused and practical.
If you don't know something, say so briefly rather than speculating at length.

Do NOT repeat yourself or ask variations of the same question multiple times.
Give ONE clear, complete response and then wait for user input.

## CAPABILITY BOUNDARIES - CRITICAL

**You MUST be honest about what you can and cannot do. NEVER claim to have done something you didn't actually do.**

### WHAT YOU CAN DO (via this chat interface)
- Answer questions conversationally
- Help brainstorm, plan, and think through problems
- Provide information from your training data
- Remember context within THIS conversation only

### WHAT YOU CANNOT DO (limitations of this interface)
- Modify the morning/evening briefings directly - they are generated programmatically
- Write files or execute code on the system
- Send notifications or emails
- Access external websites or APIs in real-time
- Remember conversations after this session ends
- Execute tasks immediately - tasks are queued for overnight processing

### WHAT TO DO WHEN ASKED FOR SOMETHING YOU CANNOT DO

1. **Be honest**: Say "I cannot do that through this chat interface"
2. **Explain why**: Briefly explain the limitation
3. **Offer alternatives**: Suggest what you CAN do instead

**WRONG responses (NEVER do this):**
- "I've added that to your morning briefing" (you cannot)
- "I've set a reminder for 10 AM" (you cannot from chat alone)
- "I've saved that to your notes" (you cannot)

**CORRECT responses:**
- "I cannot modify the morning briefing directly from this chat. The briefing is generated automatically. To add custom items, you could use the API endpoint POST /api/briefing/items, or I can help you remember this topic for when you're at your computer."
- "I cannot set reminders through this chat interface. You can create reminders via the API at POST /api/reminders, or tell me what you want to remember and I'll help you think through it."

### AVAILABLE API ENDPOINTS (for reference, not callable from chat)
- POST /api/briefing/items - Add custom briefing items
- POST /api/reminders - Create reminders
- GET /api/briefing/items - List briefing items
- GET /api/reminders - List reminders

When in doubt, be honest about limitations rather than pretending to do something you cannot."""


def load_system_prompt() -> str:
    """Load system prompt from file or use default.
    
    Priority:
    1. MILTON_CHAT_SYSTEM_PROMPT env var (file path)
    2. Prompts/SHARED_CONTEXT.md (if exists)
    3. Hardcoded MILTON_SYSTEM_PROMPT
    """
    # Check env var first
    prompt_path = os.getenv("MILTON_CHAT_SYSTEM_PROMPT")
    if prompt_path and os.path.exists(prompt_path):
        try:
            with open(prompt_path) as f:
                logger.info(f"Loaded system prompt from {prompt_path}")
                return f.read().strip()
        except Exception as e:
            logger.warning(f"Failed to load system prompt from {prompt_path}: {e}")
    
    # Try SHARED_CONTEXT.md
    shared_context_path = os.path.join(os.path.dirname(__file__), "..", "Prompts", "SHARED_CONTEXT.md")
    if os.path.exists(shared_context_path):
        try:
            with open(shared_context_path) as f:
                content = f.read().strip()
                logger.info(f"Loaded SHARED_CONTEXT.md from {shared_context_path}")
                # Add chat-specific instructions
                return f"""{content}

---

## INTERACTIVE CHAT CAPABILITIES (via Milton Gateway)

You are currently operating through the Milton Gateway at http://100.117.64.117:8081/
which bridges to the Milton API at http://100.117.64.117:8001/.

### SLASH COMMANDS YOU CAN EXECUTE

You now have special slash commands that directly call Milton API:

**Briefing Items:**
- `/briefing add <text>` - Add item to morning briefing
- `/briefing add <text> | priority:<0-10>` - Add with priority
- `/briefing add <text> | due:<date>` - Add with due date (YYYY-MM-DD, tomorrow, monday, etc.)
- `/briefing list` - Show active briefing items

**Reminders:**
- `/reminder add <text> | at:<time>` - Create a reminder
- `/reminder list` - Show scheduled reminders

**Example:**
User: "/briefing add Review GitHub notifications | priority:10 | due:tomorrow"
You should explain: "I'll add that to your morning briefing..." and the system will execute it.

When a user asks to add something to their briefing, you can now say:
"I can add that for you. Use: `/briefing add <your text>`" or execute it yourself if they use the command.

Be honest: You can ONLY execute these specific slash commands. You cannot write files, 
execute arbitrary code, or access services beyond the Milton API."""
        except Exception as e:
            logger.warning(f"Failed to load SHARED_CONTEXT.md: {e}")
    
    # Fallback to hardcoded
    return MILTON_SYSTEM_PROMPT


# Global LLM client and command processor instances
_llm_client: LLMClient | None = None
_command_processor: CommandProcessor | None = None
_memory_store = None


def get_memory_store():
    """Get or initialize the chat memory store."""
    global _memory_store
    if _memory_store is None:
        from storage.chat_memory import ChatMemoryStore
        state_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR") or Path.home() / ".local" / "state" / "milton"
        state_dir = Path(state_dir)
        db_path = state_dir / "chat_memory.sqlite3"
        _memory_store = ChatMemoryStore(db_path)
        logger.info(f"Initialized chat memory store at {db_path}")
    return _memory_store


def get_llm_client() -> LLMClient:
    """Get or create the LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def get_command_processor() -> CommandProcessor:
    """Get or create the command processor."""
    global _command_processor
    if _command_processor is None:
        config = get_config()
        _command_processor = CommandProcessor(milton_api_base_url=config["milton_api_url"])
    return _command_processor


def _resolve_thread_id(
    chat_request: ChatCompletionRequest,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> tuple[str, str | None, str]:
    """Resolve a stable thread id without deriving from message content."""
    for field in _THREAD_ID_FIELDS:
        value = getattr(chat_request, field, None)
        if value:
            return str(value), None, f"body:{field}"

    if headers:
        header_map = {key.lower(): value for key, value in headers.items()}
        for key in _THREAD_ID_HEADER_KEYS:
            value = header_map.get(key)
            if value:
                return value.strip(), None, f"header:{key}"

    if cookies:
        session_id = cookies.get(_SESSION_COOKIE_NAME)
        if session_id:
            return session_id, None, "cookie"

    session_id = uuid.uuid4().hex
    return session_id, session_id, "cookie:new"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Milton Chat Gateway starting up...")
    config = get_config()
    logger.info(f"Gateway config: host={config['host']}, port={config['port']}")
    logger.info(f"LLM backend: {config['llm_api_url']}, model={config['llm_model']}")
    logger.info(f"Milton API: {config['milton_api_url']}")
    yield
    # Cleanup
    global _llm_client, _command_processor, _memory_store
    if _llm_client is not None:
        await _llm_client.close()
    if _command_processor is not None:
        await _command_processor.close()
    if _memory_store is not None:
        _memory_store.close()
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
async def chat_completions(
    chat_request: ChatCompletionRequest,
    raw_request: Request,
    response: Response,
):
    """
    Chat completions endpoint (OpenAI-compatible).

    Supports both streaming and non-streaming responses.
    Also processes slash commands for Milton API integration.
    Stores conversation history for persistent memory across sessions.
    """
    config = get_config()
    llm_client = get_llm_client()
    command_processor = get_command_processor()
    memory_store = get_memory_store()

    # Convert Pydantic messages to dicts
    messages = [{"role": m.role, "content": m.content} for m in chat_request.messages]

    thread_id, new_session_id, thread_source = _resolve_thread_id(
        chat_request, headers=raw_request.headers, cookies=raw_request.cookies
    )
    if new_session_id and not chat_request.stream:
        response.set_cookie(
            _SESSION_COOKIE_NAME,
            new_session_id,
            httponly=True,
            samesite="Lax",
        )

    logger.debug(f"Thread ID: {thread_id} (source: {thread_source})")

    # Check if the last user message is a command
    if messages and messages[-1]["role"] == "user":
        user_message = messages[-1]["content"]
        command_result = await command_processor.process_message(user_message)
        
        if command_result.is_command:
            # This was a command - return the result directly without calling LLM
            if command_result.error:
                response_text = f"❌ Error: {command_result.error}"
            else:
                response_text = command_result.response
            
            logger.info(f"Command processed: {user_message[:50]}... -> {response_text[:50]}...")
            
            # Store command and response in conversation history
            try:
                memory_store.append_turn(thread_id, "user", user_message)
                memory_store.append_turn(thread_id, "assistant", response_text)
            except Exception as e:
                logger.warning(f"Failed to store command in conversation history: {e}")
            
            return ChatCompletionResponse(
                model=config["model_id"],
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=response_text),
                        finish_reason="stop",
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                ),
            )

    # Not a command - proceed with normal LLM flow
    # Inject system prompt if not already present
    has_system = any(m["role"] == "system" for m in messages)
    if not has_system:
        system_prompt = load_system_prompt()
        
        # Load recent conversation history and memory facts
        try:
            history_context = _build_history_context(memory_store, thread_id)
            if history_context:
                system_prompt = f"{system_prompt}\n\n{history_context}"
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
        
        messages.insert(0, {"role": "system", "content": system_prompt})
        logger.debug("Injected Milton system prompt with conversation history")

    # Use default max_tokens if not specified
    max_tokens = chat_request.max_tokens or config["max_tokens_default"]

    logger.info(
        f"Chat request: model={chat_request.model}, messages={len(messages)}, "
        f"stream={chat_request.stream}, max_tokens={max_tokens}"
    )

    if chat_request.stream:
        stream_response = StreamingResponse(
            stream_chat_response(
                llm_client,
                messages,
                chat_request.temperature,
                max_tokens,
                config["model_id"],
                thread_id,
                memory_store,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
        if new_session_id:
            stream_response.set_cookie(
                _SESSION_COOKIE_NAME,
                new_session_id,
                httponly=True,
                samesite="Lax",
            )
        return stream_response
    else:
        return await blocking_chat_response(
            llm_client,
            messages,
            chat_request.temperature,
            max_tokens,
            config["model_id"],
            thread_id,
            memory_store,
        )


def _build_history_context(memory_store, thread_id: str, max_turns: int = 10) -> str:
    """Build conversation history context for system prompt.
    
    Args:
        memory_store: ChatMemoryStore instance
        thread_id: Thread identifier
        max_turns: Maximum number of recent turns to include (default: 10)
    
    Returns:
        Formatted history context string, or empty string if no history
    """
    try:
        # Load recent conversation turns
        turns = memory_store.get_recent_turns(thread_id, limit=max_turns)
        
        # Load memory facts
        facts = memory_store.get_all_facts()
        
        if not turns and not facts:
            return ""
        
        parts = ["---", "", "## CONVERSATION MEMORY"]
        
        # Add explicit memory facts
        if facts:
            parts.append("")
            parts.append("### Stored Facts (via /remember):")
            for fact in facts:
                parts.append(f"- **{fact.key}**: {fact.value}")
        
        # Add recent conversation history
        if turns:
            parts.append("")
            parts.append(f"### Recent Conversation History ({len(turns)} turns):")
            parts.append("```")
            for turn in turns:
                # Truncate long messages
                content = turn.content if len(turn.content) <= 200 else turn.content[:200] + "..."
                parts.append(f"{turn.role.upper()}: {content}")
            parts.append("```")
            parts.append("")
            parts.append("*You can reference this history naturally in your responses.*")
        
        return "\n".join(parts)
    
    except Exception as e:
        logger.exception(f"Error building history context: {e}")
        return ""


async def blocking_chat_response(
    llm_client: LLMClient,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    model_id: str,
    thread_id: str,
    memory_store,
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
        
        # Store conversation turn in memory
        try:
            # Find last user message to store
            for msg in reversed(messages):
                if msg["role"] == "user":
                    memory_store.append_turn(thread_id, "user", msg["content"])
                    break
            memory_store.append_turn(thread_id, "assistant", content)
        except Exception as e:
            logger.warning(f"Failed to store conversation turn: {e}")

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
    thread_id: str,
    memory_store,
) -> AsyncIterator[str]:
    """
    Generate a streaming chat response using SSE.

    Yields OpenAI-compatible SSE events:
    - data: {chunk_json}
    - data: [DONE]
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    accumulated_content = []  # Track full response for storage

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
                    
                    # Accumulate content for storage
                    if content:
                        accumulated_content.append(content)

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
        
        # Store conversation turn in memory after streaming completes
        try:
            full_response = "".join(accumulated_content)
            if full_response:
                # Find last user message to store
                for msg in reversed(messages):
                    if msg["role"] == "user":
                        memory_store.append_turn(thread_id, "user", msg["content"])
                        break
                memory_store.append_turn(thread_id, "assistant", full_response)
        except Exception as e:
            logger.warning(f"Failed to store streaming conversation turn: {e}")

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
