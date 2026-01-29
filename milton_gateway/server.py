"""Milton Chat Gateway - OpenAI-compatible FastAPI server for Open WebUI integration."""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Mapping, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env")

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .llm_client import LLMClient
from milton_orchestrator.state_paths import resolve_state_dir
from .command_processor import CommandProcessor, CommandResult
from .models import (
    AddMemoryRequest,
    AddSnapshotRequest,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    DeltaContent,
    ErrorDetail,
    ErrorResponse,
    MemoryListResponse,
    MemoryOperationResponse,
    MemoryResponse,
    ModelInfo,
    ModelsResponse,
    SnapshotListResponse,
    SnapshotOperationResponse,
    SnapshotResponse,
    StreamChoice,
    UpdateMemoryRequest,
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

_ACTION_INTERNAL_TAG = "[[MILTON_INTERNAL]]"


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


# Global LLM client, command processor, and memory store instances
_llm_client: LLMClient | None = None
_command_processor: CommandProcessor | None = None
_memory_store = None
_declarative_memory_store = None
_activity_snapshot_store = None


def get_activity_snapshot_store():
    """Get or initialize the activity snapshot store."""
    global _activity_snapshot_store
    if _activity_snapshot_store is None:
        from milton_orchestrator.activity_snapshots import ActivitySnapshotStore
        from milton_orchestrator.state_paths import resolve_state_dir
        import os
        
        state_dir = resolve_state_dir()
        db_path = state_dir / "activity_snapshots.sqlite3"
        
        # Get retention settings from environment
        retention_days = os.getenv("ACTIVITY_RETENTION_DAYS")
        max_per_device = os.getenv("ACTIVITY_MAX_PER_DEVICE")
        
        _activity_snapshot_store = ActivitySnapshotStore(
            db_path,
            retention_days=int(retention_days) if retention_days else None,
            max_per_device=int(max_per_device) if max_per_device else None,
        )
        logger.info(f"Initialized activity snapshot store at {db_path}")
    return _activity_snapshot_store


def get_declarative_memory_store():
    """Get or initialize the declarative memory store."""
    global _declarative_memory_store
    if _declarative_memory_store is None:
        from milton_orchestrator.declarative_memory import DeclarativeMemoryStore
        from milton_orchestrator.state_paths import resolve_state_dir
        state_dir = resolve_state_dir()
        db_path = state_dir / "declarative_memory.sqlite3"
        _declarative_memory_store = DeclarativeMemoryStore(db_path)
        logger.info(f"Initialized declarative memory store at {db_path}")
    return _declarative_memory_store


def get_memory_store():
    """Get or initialize the chat memory store."""
    global _memory_store
    if _memory_store is None:
        from storage.chat_memory import ChatMemoryStore
        from milton_orchestrator.state_paths import resolve_state_dir
        state_dir = resolve_state_dir()
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
    global _llm_client, _command_processor, _memory_store, _declarative_memory_store, _activity_snapshot_store
    if _llm_client is not None:
        await _llm_client.close()
    if _command_processor is not None:
        await _command_processor.close()
    if _memory_store is not None:
        _memory_store.close()
    if _declarative_memory_store is not None:
        _declarative_memory_store.close()
    if _activity_snapshot_store is not None:
        _activity_snapshot_store.close()
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


@app.get("/memory/status")
async def memory_status():
    """
    Memory system status endpoint.

    Returns memory backend mode, availability, degradation state,
    and last retrieval statistics.
    """
    from memory.status import get_memory_status

    status = get_memory_status()

    response = {
        "mode": status.mode,
        "backend_available": status.backend_available,
        "degraded": status.degraded,
        "detail": status.detail,
        "warnings": status.warnings,
    }

    if status.last_retrieval:
        response["last_retrieval"] = {
            "query": status.last_retrieval.query,
            "count": status.last_retrieval.count,
            "timestamp": status.last_retrieval.timestamp.isoformat(),
            "mode": status.last_retrieval.mode,
            "duration_ms": status.last_retrieval.duration_ms,
        }
    else:
        response["last_retrieval"] = None

    return response


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
    action_summary = None
    action_context = None  # Truth gate: track what was actually executed
    skip_auto_store = False

    if messages and messages[-1]["role"] == "user":
        user_message = messages[-1]["content"]

        logger.info(f"🔍 Processing user message: {user_message[:100]}...")

        # Skip internal system prompts and internal tags
        skip_planning = (
            user_message.strip().startswith("### Task:")
            or _ACTION_INTERNAL_TAG in user_message
        )

        if user_message.strip().startswith("/"):
            # Set session_id for the command processor
            command_processor.session_id = thread_id
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

        if not skip_planning:
            from milton_gateway.action_planner import extract_action_plan, should_use_llm_fallback
            from milton_gateway.action_executor import execute_action_plan

            # Use timezone from request or default to America/Chicago
            user_timezone = chat_request.timezone or "America/Chicago"

            plan = extract_action_plan(
                user_message,
                datetime.now(timezone.utc).isoformat(),
                user_timezone,
            )
            
            # Build action context for all cases
            action_context = None
            
            if plan.get("action") == "CLARIFY":
                # Short-circuit: return clarification question immediately
                question = plan.get("payload", {}).get("question", "Could you clarify?")
                response_text = question
                try:
                    memory_store.append_turn(thread_id, "user", user_message)
                    memory_store.append_turn(thread_id, "assistant", response_text)
                except Exception as e:
                    logger.warning(f"Failed to store clarification in conversation history: {e}")

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
            
            elif plan.get("action") == "NOOP":
                fallback_used = False
                
                # Check if LLM fallback should be attempted
                if should_use_llm_fallback(plan, user_message):
                    logger.info(f"🔄 Attempting LLM fallback for NOOP case")
                    
                    try:
                        from milton_gateway.llm_intent_classifier import (
                            classify_intent_with_llm,
                            should_execute_classification,
                            convert_classification_to_plan
                        )
                        
                        # Call LLM classifier
                        classification = await classify_intent_with_llm(
                            user_message,
                            llm_client,
                            datetime.now(timezone.utc).isoformat(),
                            "America/Chicago",
                        )
                        
                        if classification and should_execute_classification(classification):
                            # Convert to action plan format
                            fallback_plan = convert_classification_to_plan(
                                classification,
                                "America/Chicago"
                            )
                            
                            logger.info(f"✅ LLM fallback succeeded: {fallback_plan.get('action')}")
                            logger.info(f"📋 Fallback plan: original_plan=NOOP, "
                                      f"fallback_action={fallback_plan.get('action')}, "
                                      f"confidence={fallback_plan.get('confidence')}")
                            
                            # Execute the fallback plan
                            exec_result = execute_action_plan(
                                fallback_plan,
                                {"timezone": "America/Chicago", "state_dir": str(resolve_state_dir())},
                            )
                            action_summary = _format_action_summary(fallback_plan, exec_result)
                            action_context = _build_action_context(fallback_plan, exec_result)
                            skip_auto_store = True
                            fallback_used = True
                            
                            logger.info(f"✅ Fallback action executed: {fallback_plan.get('action')} -> {exec_result.get('status')}")
                        else:
                            # Classification failed safety gates - check for deterministic response
                            logger.info(f"🚫 LLM fallback did not meet safety gates")
                            intent_hint = _detect_action_intent(user_message)
                            if intent_hint:
                                # Return deterministic NOOP response without calling LLM
                                logger.info(f"🛑 Deterministic NOOP: detected intent={intent_hint}, blocking LLM call")
                                return _build_deterministic_noop_response(
                                    user_message,
                                    intent_hint,
                                    plan,
                                    thread_id,
                                    chat_request,
                                )
                            else:
                                # Not action-like, proceed with LLM for normal chat
                                action_context = _build_action_context(plan, exec_result=None)
                                reason = plan.get("payload", {}).get("reason", "no_action_detected")
                                logger.info(f"🚫 NOOP: {reason} - will inject truth gate into system prompt")
                    
                    except Exception as e:
                        logger.error(f"LLM fallback error: {e}", exc_info=True)
                        # Check if we should return deterministic response
                        intent_hint = _detect_action_intent(user_message)
                        if intent_hint:
                            logger.info(f"🛑 Deterministic NOOP after fallback error: intent={intent_hint}")
                            return _build_deterministic_noop_response(
                                user_message,
                                intent_hint,
                                plan,
                                thread_id,
                                chat_request,
                            )
                        else:
                            # Fall through to normal NOOP handling with truth gate
                            action_context = _build_action_context(plan, exec_result=None)
                            reason = plan.get("payload", {}).get("reason", "no_action_detected")
                            logger.info(f"🚫 NOOP (fallback failed): {reason} - will inject truth gate")
                else:
                    # Fallback not triggered - check if action-like request
                    intent_hint = _detect_action_intent(user_message)
                    if intent_hint:
                        # Return deterministic NOOP response without calling LLM
                        logger.info(f"🛑 Deterministic NOOP: detected intent={intent_hint}, no fallback triggered, blocking LLM call")
                        return _build_deterministic_noop_response(
                            user_message,
                            intent_hint,
                            plan,
                            thread_id,
                            chat_request,
                        )
                    else:
                        # Not action-like, proceed with LLM for normal chat
                        action_context = _build_action_context(plan, exec_result=None)
                        reason = plan.get("payload", {}).get("reason", "no_action_detected")
                        logger.info(f"🚫 NOOP: {reason} - proceeding with LLM (not action-like)")
            
            elif plan.get("action") != "NOOP":
                # Execute the action
                exec_result = execute_action_plan(
                    plan,
                    {"timezone": "America/Chicago", "state_dir": str(resolve_state_dir())},
                )
                action_summary = _format_action_summary(plan, exec_result)
                action_context = _build_action_context(plan, exec_result)
                skip_auto_store = True
                
                logger.info(f"✅ Action executed: {plan.get('action')} -> {exec_result.get('status')}")

    # Not a command - proceed with normal LLM flow
    # Inject system prompt if not already present
    has_system = any(m["role"] == "system" for m in messages)
    if not has_system:
        system_prompt = load_system_prompt()

        # Extract user query for memory retrieval
        user_query = messages[-1]["content"] if messages and messages[-1]["role"] == "user" else ""

        # Load recent conversation history, memory facts, and semantic memory
        try:
            history_context = _build_history_context(memory_store, thread_id, user_query=user_query)
            if history_context:
                system_prompt = f"{system_prompt}\n\n{history_context}"
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
        
        # TRUTH GATE: Inject action context if action was planned
        if action_context is not None:
            system_prompt = _inject_action_context_into_prompt(system_prompt, action_context)
            logger.info(f"🛡️ Truth gate: Injected action context (executed={action_context.get('action_executed')})")

        messages.insert(0, {"role": "system", "content": system_prompt})
        logger.debug("Injected Milton system prompt with conversation history")
    
    # Check if conversation needs summarization
    from .conversation_summarizer import should_summarize, summarize_conversation
    
    if should_summarize(messages, max_tokens=8192):
        logger.info("Conversation approaching context limit, summarizing...")
        try:
            messages, summary = await summarize_conversation(messages, llm_client, keep_recent=10)
            logger.info(f"Summarized conversation: {len(messages)} messages remain")
        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
            # Continue with original messages

    # Use default max_tokens if not specified
    max_tokens = chat_request.max_tokens or config["max_tokens_default"]
    
    # Cap max_tokens to prevent context overflow
    # Rough estimate: 1 token ≈ 4 chars, leave 20% buffer for model context (8192 for llama)
    model_max_context = 8192
    estimated_input_tokens = sum(len(msg.get("content", "")) for msg in messages) // 4
    safe_max_tokens = min(max_tokens, model_max_context - estimated_input_tokens - 200)
    
    if safe_max_tokens < 100:
        safe_max_tokens = 100  # Minimum reasonable response
        logger.warning(f"Input very large ({estimated_input_tokens} tokens), capping output to {safe_max_tokens}")
    elif safe_max_tokens < max_tokens:
        logger.info(f"Reduced max_tokens from {max_tokens} to {safe_max_tokens} to fit context window")
    
    max_tokens = safe_max_tokens

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
                action_summary=action_summary,
                skip_auto_store=skip_auto_store,
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
            action_summary=action_summary,
            skip_auto_store=skip_auto_store,
        )


def _build_memory_retrieval_context(user_query: str, max_items: int = 5) -> str:
    """
    Build memory context from retrieval system (Weaviate/JSONL).

    This queries the semantic memory store and records retrieval stats.
    Controlled by MILTON_GATEWAY_MEMORY_RETRIEVAL env var (default: enabled).

    Args:
        user_query: User's message to query against
        max_items: Maximum number of memory items to retrieve

    Returns:
        Formatted memory context string, or empty string if disabled/failed
    """
    # Check if memory retrieval is enabled (default: yes)
    enabled = os.getenv("MILTON_GATEWAY_MEMORY_RETRIEVAL", "1").lower() in ("1", "true", "yes", "on")
    if not enabled:
        logger.debug("Memory retrieval disabled via MILTON_GATEWAY_MEMORY_RETRIEVAL=0")
        return ""

    try:
        from memory.retrieve import query_relevant_hybrid
        from memory.status import record_retrieval

        # Query semantic memory
        memories = query_relevant_hybrid(
            user_query,
            limit=max_items,
            recency_bias=0.5,
            semantic_weight=0.5,
            mode="hybrid",
        )

        # Record retrieval stats (makes /memory/status observable)
        record_retrieval(query=user_query, count=len(memories), mode="hybrid")

        if not memories:
            logger.debug("No relevant memories found")
            return ""

        # Format memory context
        parts = ["", "### Relevant Memory Context:", ""]
        for mem in memories:
            # Truncate long content
            content = mem.content if len(mem.content) <= 150 else mem.content[:150] + "..."
            parts.append(f"- {content}")

        logger.info(f"Retrieved {len(memories)} memory items for query: {user_query[:50]}...")
        return "\n".join(parts)

    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        # Record failed retrieval
        try:
            from memory.status import record_retrieval
            record_retrieval(query=user_query, count=0, mode="error")
        except:
            pass
        return ""


async def _auto_store_facts(assistant_response: str, user_message: str, thread_id: str):
    """Automatically extract and store facts when assistant claims to store something.
    
    Args:
        assistant_response: What Milton said
        user_message: What user said
        thread_id: Session/thread ID
    """
    try:
        from .auto_fact_extractor import detect_storage_intent
        import httpx
        
        cfg = get_config()
        actions = detect_storage_intent(assistant_response, user_message)
        
        if not actions:
            return
        
        logger.info(f"Auto-extracting {len(actions)} storage actions from conversation")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for action in actions:
                if action["type"] == "memory":
                    # Store fact via Milton API
                    fact_data = action["data"]
                    key = fact_data.get("key")
                    value = fact_data.get("value")
                    
                    if key and value:
                        try:
                            response = await client.post(
                                f"{cfg['milton_api_url']}/api/memory",
                                json={"key": key, "value": value, "session_id": thread_id}
                            )
                            if response.is_success:
                                logger.info(f"✓ Auto-stored fact: {key} = {value[:50]}...")
                            else:
                                logger.warning(f"Failed to store fact {key}: {response.status_code}")
                        except Exception as e:
                            logger.error(f"Error storing fact {key}: {e}")
                
                elif action["type"] == "reminder":
                    # Create reminder via Milton API
                    reminder_data = action["data"]
                    text = reminder_data.get("text")
                    time_expr = reminder_data.get("time_expression")
                    
                    if text and time_expr:
                        try:
                            # Parse time expression to due date
                            import dateparser
                            due_date = dateparser.parse(time_expr)
                            
                            if due_date:
                                response = await client.post(
                                    f"{cfg['milton_api_url']}/api/reminders",
                                    json={
                                        "text": text,
                                        "due_date": due_date.isoformat(),
                                        "channel": ["ntfy"]
                                    }
                                )
                                if response.is_success:
                                    logger.info(f"✓ Auto-created reminder: {text} @ {time_expr}")
                                else:
                                    logger.warning(f"Failed to create reminder: {response.status_code}")
                        except Exception as e:
                            logger.error(f"Error creating reminder: {e}")
    
    except Exception as e:
        logger.error(f"Auto-storage failed: {e}")


async def _smart_extract_and_store_facts(user_message: str, session_id: str):
    """Automatically extract and store facts from user's natural conversation.
    Also detects and creates reminders from natural language.
    
    Args:
        user_message: What the user said
        session_id: Session/thread ID
    """
    try:
        from .smart_fact_extractor import extract_facts_from_message
        from .reminder_detector import ReminderDetector
        from storage.chat_memory import ChatMemoryStore
        from milton_orchestrator.state_paths import resolve_state_dir
        
        # Extract facts from message
        facts = extract_facts_from_message(user_message)
        
        if facts:
            logger.info(f"📝 Smart extraction found {len(facts)} facts in message")
            
            # Store each fact
            state_dir = resolve_state_dir()
            memory_db = state_dir / "chat_memory.sqlite3"
            memory_store = ChatMemoryStore(memory_db)
            
            for fact in facts:
                key = fact["key"]
                value = fact["value"]
                category = fact.get("category", "general")
                
                try:
                    # Store in memory store
                    memory_store.upsert_fact(key, value)
                    logger.info(f"✓ Auto-stored: {key} = {value[:50]}... [{category}]")
                except Exception as e:
                    logger.error(f"Failed to auto-store fact {key}: {e}")
            
            memory_store.close()
        
        # Check for reminder requests
        detector = ReminderDetector()
        reminder = detector.detect_reminder_request(user_message)
        
        if reminder:
            logger.info(f"⏰ Detected reminder request: {reminder['type']} on {reminder['day']} at {reminder['time']}")
            
            # Create reminder via API
            try:
                # Build natural language time expression for API
                # Format: "sunday 8am" (next occurrence)
                day = reminder["day"]
                time = reminder["time"]
                
                # Map time to hour
                time_map = {"morning": "8am", "afternoon": "2pm", "evening": "6pm"}
                hour = time_map.get(time.lower(), "8am")
                
                remind_at_expr = f"{day} {hour}"
                
                # Build reminder message
                task = reminder["task"]
                reminder_msg = f"Meal prep: {task}"
                
                # Create weekly reminder via internal API
                import httpx
                api_url = os.getenv("MILTON_API_URL", "http://localhost:8001")
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{api_url}/api/reminders",
                        json={
                            "message": reminder_msg,
                            "remind_at": remind_at_expr,
                            "kind": "REMIND",
                            "timezone": "America/New_York"
                        },
                        timeout=10.0
                    )
                    
                    if response.status_code == 201:
                        logger.info(f"✓ Created weekly reminder: {remind_at_expr}")
                    else:
                        logger.warning(f"Failed to create reminder: {response.status_code} - {response.text}")
                        
            except Exception as e:
                logger.error(f"Error creating reminder: {e}")
    
    except Exception as e:
        logger.error(f"Smart fact extraction/reminder detection failed: {e}")


def _build_history_context(memory_store, thread_id: str, max_turns: int = 10, user_query: str = "") -> str:
    """Build conversation history context for system prompt.

    Args:
        memory_store: ChatMemoryStore instance
        thread_id: Thread identifier
        max_turns: Maximum number of recent turns to include (default: 10)
        user_query: Optional user query for memory retrieval

    Returns:
        Formatted history context string, or empty string if no history
    """
    try:
        # Load recent conversation turns
        turns = memory_store.get_recent_turns(thread_id, limit=max_turns)

        # Load memory facts
        facts = memory_store.get_all_facts()

        # Load semantic memory (if enabled)
        memory_context = ""
        if user_query:
            memory_context = _build_memory_retrieval_context(user_query)

        if not turns and not facts and not memory_context:
            return ""

        parts = ["---", "", "## CONVERSATION MEMORY"]

        # Add explicit memory facts
        if facts:
            parts.append("")
            parts.append("### Stored Facts (via /remember):")
            for fact in facts:
                parts.append(f"- **{fact.key}**: {fact.value}")

        # Add semantic memory retrieval
        if memory_context:
            parts.append(memory_context)

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


def _build_action_context(plan: dict, exec_result: dict | None = None) -> dict:
    """Build structured action context for LLM truth gate.
    
    Returns a dict with:
        - action_detected: bool
        - action_executed: bool  
        - action_type: str | None
        - reason: str (e.g., "no_action_detected", "missing_fields", "execution_failed", "executed_ok")
        - details: dict with action-specific metadata
    """
    action = plan.get("action")
    payload = plan.get("payload") or {}
    
    # No action detected
    if action == "NOOP":
        reason = payload.get("reason", "no_action_detected")
        return {
            "action_detected": False,
            "action_executed": False,
            "action_type": None,
            "reason": reason,
            "details": {},
        }
    
    # Action detected but needs clarification
    if action == "CLARIFY":
        question = payload.get("question", "")
        return {
            "action_detected": True,
            "action_executed": False,
            "action_type": action,
            "reason": "needs_clarification",
            "details": {"question": question},
        }
    
    # Action was detected but not executed yet (exec_result is None)
    if exec_result is None:
        return {
            "action_detected": True,
            "action_executed": False,
            "action_type": action,
            "reason": "not_executed",
            "details": payload,
        }
    
    # Action was attempted - check execution result
    if not isinstance(exec_result, dict) or exec_result.get("status") != "ok":
        errors = exec_result.get("errors", []) if isinstance(exec_result, dict) else []
        return {
            "action_detected": True,
            "action_executed": False,
            "action_type": action,
            "reason": "execution_failed",
            "details": {"errors": errors, "payload": payload},
        }
    
    # Action executed successfully
    artifacts = exec_result.get("artifacts", {})
    return {
        "action_detected": True,
        "action_executed": True,
        "action_type": action,
        "reason": "executed_ok",
        "details": artifacts,
    }


def _format_action_summary(plan: dict, exec_result: dict) -> str:
    """Create a short action summary for the user."""
    if not isinstance(exec_result, dict) or exec_result.get("status") != "ok":
        return "Action summary: Unable to execute the requested action."

    action = plan.get("action")
    payload = plan.get("payload") or {}

    if action == "CREATE_MEMORY":
        key = _summary_text(payload.get("key") or "memory")
        return f"Action summary: Saved memory: {key}"
    if action == "CREATE_REMINDER":
        title = _summary_text(payload.get("title") or "reminder")
        when = _summary_text(payload.get("when") or "")
        if when:
            return f"Action summary: Created reminder: {title} ({when})"
        return f"Action summary: Created reminder: {title}"
    if action == "CREATE_GOAL":
        title = _summary_text(payload.get("title") or "goal")
        return f"Action summary: Added goal: {title}"

    return "Action summary: Action completed."


def _inject_action_context_into_prompt(system_prompt: str, action_context: dict) -> str:
    """Inject action execution context into system prompt for truth gate enforcement.
    
    This ensures the LLM knows exactly what was and wasn't executed.
    """
    action_executed = action_context.get("action_executed", False)
    action_detected = action_context.get("action_detected", False)
    action_type = action_context.get("action_type")
    reason = action_context.get("reason", "unknown")
    details = action_context.get("details", {})
    
    # Build the action status message
    action_status = "\n\n## ACTION EXECUTION STATUS (CRITICAL - READ THIS)\n\n"
    
    if not action_detected:
        action_status += "**NO ACTION WAS DETECTED OR EXECUTED in the user's message.**\n\n"
        action_status += f"Reason: {reason}\n\n"
        action_status += "If the user appears to be requesting an action (like creating a reminder, goal, or saving information), "
        action_status += "you MUST:\n"
        action_status += "1. Acknowledge that NO action was executed\n"
        action_status += "2. Explain that their phrasing wasn't recognized by the action parser\n"
        action_status += "3. Provide an example of correct phrasing (e.g., 'remind me to X tomorrow at 9am')\n"
        action_status += "4. Offer to help them rephrase it correctly\n\n"
        action_status += "**DO NOT claim or imply that any action was taken.**\n"
    
    elif not action_executed:
        action_status += f"**AN ACTION WAS DETECTED ({action_type}) BUT NOT EXECUTED.**\n\n"
        action_status += f"Reason: {reason}\n\n"
        
        if reason == "needs_clarification":
            question = details.get("question", "")
            action_status += f"The system needs clarification: {question}\n\n"
            action_status += "You MUST:\n"
            action_status += "1. Acknowledge that the action was NOT executed\n"
            action_status += "2. Ask the clarifying question to get missing information\n"
            action_status += "3. NOT claim that anything was saved/created/executed\n"
        
        elif reason == "execution_failed":
            errors = details.get("errors", [])
            action_status += f"Execution failed with errors: {errors}\n\n"
            action_status += "You MUST:\n"
            action_status += "1. Acknowledge that the action FAILED\n"
            action_status += "2. Explain what went wrong\n"
            action_status += "3. Suggest how to fix it\n"
            action_status += "4. NOT claim success\n"
        
        else:
            action_status += "You MUST:\n"
            action_status += "1. Acknowledge that the action was detected but NOT executed\n"
            action_status += "2. Explain why (if known)\n"
            action_status += "3. NOT claim that anything was saved/created/executed\n"
    
    else:
        # Action executed successfully
        action_status += f"**ACTION WAS SUCCESSFULLY EXECUTED: {action_type}**\n\n"
        action_status += f"Details: {details}\n\n"
        action_status += "You SHOULD:\n"
        action_status += "1. Confirm that the action was completed\n"
        action_status += "2. Reference specific IDs or details from the execution\n"
        action_status += "3. Be confident in stating what was done\n"
    
    return f"{system_prompt}{action_status}"


def _summary_text(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.encode("ascii", "ignore").decode("ascii")


def _detect_action_intent(text: str) -> Optional[str]:
    """Detect if text appears to request an action, return intent hint.
    
    This is a conservative heuristic used to decide if we should return
    a deterministic NOOP response instead of calling the LLM.
    
    Args:
        text: User's message text
        
    Returns:
        Intent hint ("reminder", "goal", "memory") or None if not action-like
    """
    text_lower = text.lower()
    
    # Check for reminder-related keywords
    reminder_keywords = [
        "reminder", "remind", "ping me", "nudge me", 
        "set a reminder", "create a reminder", "add a reminder",
        "schedule a reminder", "schedule", "notify me", "alert me"
    ]
    for keyword in reminder_keywords:
        if keyword in text_lower:
            return "reminder"
    
    # Check for goal-related keywords
    goal_keywords = [
        "goal", "add a goal", "set a goal", "create a goal",
        "track this", "tracking"
    ]
    for keyword in goal_keywords:
        if keyword in text_lower:
            return "goal"
    
    # Check for memory-related keywords
    memory_keywords = [
        "remember that", "save this", "store this", 
        "add to memory", "keep track of", "record this"
    ]
    for keyword in memory_keywords:
        if keyword in text_lower:
            return "memory"
    
    return None


def _build_deterministic_noop_response(
    user_text: str,
    intent_hint: Optional[str],
    plan: Dict[str, Any],
    thread_id: str,
    chat_request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """Build a deterministic response for NOOP cases without calling LLM.
    
    This prevents LLM hallucinations when no action was executed.
    
    Args:
        user_text: User's original message
        intent_hint: Detected intent type ("reminder", "goal", "memory", or None)
        plan: The NOOP plan from action planner
        thread_id: Conversation thread ID
        chat_request: Original chat request
        
    Returns:
        ChatCompletionResponse with deterministic content
    """
    reason = plan.get("payload", {}).get("reason", "no_action_detected")
    
    # Build response based on detected intent
    if intent_hint == "reminder":
        response_text = (
            "No reminder was created. I couldn't parse your request as a valid reminder command.\n\n"
            "To create a reminder, try one of these formats:\n"
            "• 'Remind me to <task> tomorrow at 4:30 PM'\n"
            "• 'Set a reminder for me to <task> on Friday at 2pm'\n"
            "• 'Create a reminder to <task> next week'\n\n"
            "Make sure to include both what you want to be reminded about and when."
        )
    elif intent_hint == "goal":
        response_text = (
            "No goal was created. I couldn't parse your request as a valid goal command.\n\n"
            "To create a goal, try:\n"
            "• 'Add a goal: <goal description>'\n"
            "• 'Create a goal to <accomplish something>'\n\n"
            "What would you like to achieve?"
        )
    elif intent_hint == "memory":
        response_text = (
            "No information was saved. I couldn't parse your request as a memory storage command.\n\n"
            "To save information, try:\n"
            "• 'Remember that <fact>'\n"
            "• 'Save this: <information>'\n"
            "• 'Store the fact that <fact>'\n\n"
            "What would you like me to remember?"
        )
    else:
        # Action-like but unclear intent
        response_text = (
            "No action was executed. I detected what might be an action request, "
            "but I couldn't determine what you wanted me to do.\n\n"
            "I can help you:\n"
            "• Create reminders (e.g., 'Remind me to X tomorrow at 4pm')\n"
            "• Add goals (e.g., 'Add a goal: Complete project Y')\n"
            "• Store information (e.g., 'Remember that I prefer Python')\n\n"
            "What would you like to do?"
        )
    
    # Add machine-readable action summary
    action_summary_line = (
        "\n\nACTION_SUMMARY: "
        '{"action_detected": false, "action_executed": false, '
        f'"reason": "{reason}", "intent_hint": "{intent_hint or "unknown"}"' + "}"
    )
    response_text += action_summary_line
    
    logger.info(f"🤖 Returning deterministic NOOP response (intent={intent_hint}, reason={reason})")
    
    # Build OpenAI-compatible response
    return ChatCompletionResponse(
        id=f"chatcmpl-{thread_id}-noop",
        created=int(datetime.now(timezone.utc).timestamp()),
        model=chat_request.model,
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


async def blocking_chat_response(
    llm_client: LLMClient,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    model_id: str,
    thread_id: str,
    memory_store,
    action_summary: str | None = None,
    skip_auto_store: bool = False,
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
        base_content = content
        if action_summary:
            content = f"{content}\n\n{action_summary}"
        usage = result.get("usage", {})
        
        # AUTO-EXTRACT FACTS: Check if assistant mentioned storing something
        user_message = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break
        
        if not skip_auto_store:
            await _auto_store_facts(base_content, user_message, thread_id)
        
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
    action_summary: str | None = None,
    skip_auto_store: bool = False,
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

        if action_summary:
            summary_chunk = ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=model_id,
                choices=[
                    StreamChoice(
                        index=0,
                        delta=DeltaContent(content=f"\n\n{action_summary}"),
                        finish_reason=None,
                    )
                ],
            )
            yield f"data: {summary_chunk.model_dump_json()}\n\n"
            accumulated_content.append(f"\n\n{action_summary}")

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
                user_message = ""
                for msg in reversed(messages):
                    if msg["role"] == "user":
                        user_message = msg["content"]
                        memory_store.append_turn(thread_id, "user", user_message)
                        break
                memory_store.append_turn(thread_id, "assistant", full_response)
                
                # AUTO-EXTRACT FACTS: Check if assistant mentioned storing something
                if not skip_auto_store:
                    await _auto_store_facts(full_response, user_message, thread_id)
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


# Declarative Memory API Endpoints
@app.post("/v1/memory/declarative")
async def add_declarative_memory(request: AddMemoryRequest) -> MemoryOperationResponse:
    """
    Add a new declarative memory (user-stated fact or intent).
    
    Args:
        request: Memory creation request
        
    Returns:
        Operation response with memory ID
    """
    try:
        store = get_declarative_memory_store()
        memory_id = store.add_memory(
            content=request.content,
            tags=request.tags,
            source=request.source,
            confidence=request.confidence,
            context_ref=request.context_ref,
        )
        logger.info(f"Added declarative memory {memory_id}")
        return MemoryOperationResponse(
            success=True,
            message="Memory added successfully",
            memory_id=memory_id,
        )
    except ValueError as e:
        logger.warning(f"Validation error adding memory: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding declarative memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to add memory")


@app.get("/v1/memory/declarative")
async def list_declarative_memories(limit: int = 100) -> MemoryListResponse:
    """
    List all declarative memories, newest first.
    
    Args:
        limit: Maximum number of results (default 100)
        
    Returns:
        List of memories
    """
    try:
        store = get_declarative_memory_store()
        memories = store.list_memories(limit=limit)
        return MemoryListResponse(
            memories=[
                MemoryResponse(
                    id=m.id,
                    content=m.content,
                    tags=m.tags,
                    source=m.source,
                    confidence=m.confidence,
                    context_ref=m.context_ref,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in memories
            ],
            count=len(memories),
        )
    except Exception as e:
        logger.error(f"Error listing memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to list memories")


@app.get("/v1/memory/declarative/search")
async def search_declarative_memory(
    query: Optional[str] = None,
    tags: Optional[str] = None,  # Comma-separated list
    limit: int = 100,
) -> MemoryListResponse:
    """
    Search declarative memories by content and/or tags.
    
    Args:
        query: Optional keyword to search in content
        tags: Optional comma-separated list of tags to filter by
        limit: Maximum number of results (default 100)
        
    Returns:
        List of matching memories
    """
    try:
        store = get_declarative_memory_store()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        memories = store.search_memory(query=query, tags=tag_list, limit=limit)
        return MemoryListResponse(
            memories=[
                MemoryResponse(
                    id=m.id,
                    content=m.content,
                    tags=m.tags,
                    source=m.source,
                    confidence=m.confidence,
                    context_ref=m.context_ref,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in memories
            ],
            count=len(memories),
        )
    except Exception as e:
        logger.error(f"Error searching memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to search memories")


@app.get("/v1/memory/declarative/{memory_id}")
async def get_declarative_memory(memory_id: str) -> MemoryResponse:
    """
    Get a declarative memory by ID.
    
    Args:
        memory_id: The memory ID
        
    Returns:
        Memory data
    """
    try:
        store = get_declarative_memory_store()
        memory = store.get_memory(memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return MemoryResponse(
            id=memory.id,
            content=memory.content,
            tags=memory.tags,
            source=memory.source,
            confidence=memory.confidence,
            context_ref=memory.context_ref,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory")


@app.put("/v1/memory/declarative/{memory_id}")
async def update_declarative_memory(
    memory_id: str, request: UpdateMemoryRequest
) -> MemoryOperationResponse:
    """
    Update an existing declarative memory.
    
    Args:
        memory_id: The memory ID to update
        request: Memory update request
        
    Returns:
        Operation response
    """
    try:
        store = get_declarative_memory_store()
        success = store.update_memory(
            memory_id=memory_id,
            content=request.content,
            tags=request.tags,
            confidence=request.confidence,
            context_ref=request.context_ref,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.info(f"Updated declarative memory {memory_id}")
        return MemoryOperationResponse(
            success=True,
            message="Memory updated successfully",
            memory_id=memory_id,
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating memory: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update memory")


@app.delete("/v1/memory/declarative/{memory_id}")
async def delete_declarative_memory(memory_id: str) -> MemoryOperationResponse:
    """
    Delete a declarative memory by ID.
    
    Args:
        memory_id: The memory ID to delete
        
    Returns:
        Operation response
    """
    try:
        store = get_declarative_memory_store()
        success = store.delete_memory(memory_id)
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.info(f"Deleted declarative memory {memory_id}")
        return MemoryOperationResponse(
            success=True,
            message="Memory deleted successfully",
            memory_id=memory_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete memory")


# Activity Snapshot API Endpoints

def check_activity_token(token: Optional[str] = None) -> None:
    """
    Check activity snapshot API token.
    
    Args:
        token: Token from X-MILTON-TOKEN header
        
    Raises:
        HTTPException: If auth is required and token is invalid
    """
    required_token = os.getenv("MILTON_ACTIVITY_TOKEN")
    
    # If no token is configured, auth is disabled (development mode)
    if not required_token:
        return
    
    # Token is required
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-MILTON-TOKEN header. Activity snapshot ingestion requires authentication.",
        )
    
    if token != required_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid X-MILTON-TOKEN. Access denied.",
        )


@app.post("/v1/activity/snapshot")
async def add_activity_snapshot(
    request: AddSnapshotRequest,
    raw_request: Request,
) -> SnapshotOperationResponse:
    """
    Add a new activity snapshot from a device.
    
    Requires X-MILTON-TOKEN header if MILTON_ACTIVITY_TOKEN is set.
    
    Args:
        request: Snapshot data
        raw_request: FastAPI Request for header access
        
    Returns:
        Operation response with snapshot ID
    """
    # Check auth token
    token = raw_request.headers.get("x-milton-token")
    check_activity_token(token)
    
    try:
        store = get_activity_snapshot_store()
        snapshot_id = store.add_snapshot(
            device_id=request.device_id,
            device_type=request.device_type,
            captured_at=request.captured_at,
            active_app=request.active_app,
            window_title=request.window_title,
            project_path=request.project_path,
            git_branch=request.git_branch,
            recent_files=request.recent_files,
            notes=request.notes,
        )
        
        # Trigger cleanup if configured
        store.cleanup_old()
        
        logger.info(f"Added activity snapshot {snapshot_id} from device {request.device_id}")
        return SnapshotOperationResponse(
            success=True,
            message="Snapshot added successfully",
            snapshot_id=snapshot_id,
        )
    except ValueError as e:
        logger.warning(f"Validation error adding snapshot: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding activity snapshot: {e}")
        raise HTTPException(status_code=500, detail="Failed to add snapshot")


@app.get("/v1/activity/recent")
async def get_recent_snapshots(
    device_id: Optional[str] = None,
    minutes: Optional[int] = None,
    limit: int = 100,
) -> SnapshotListResponse:
    """
    Get recent activity snapshots.
    
    Args:
        device_id: Optional device ID filter
        minutes: Optional time range in minutes (from now)
        limit: Maximum number of results (default 100)
        
    Returns:
        List of recent snapshots
    """
    try:
        store = get_activity_snapshot_store()
        snapshots = store.get_recent(
            device_id=device_id,
            minutes=minutes,
            limit=limit,
        )
        return SnapshotListResponse(
            snapshots=[
                SnapshotResponse(
                    id=s.id,
                    device_id=s.device_id,
                    device_type=s.device_type,
                    captured_at=s.captured_at,
                    active_app=s.active_app,
                    window_title=s.window_title,
                    project_path=s.project_path,
                    git_branch=s.git_branch,
                    recent_files=s.recent_files,
                    notes=s.notes,
                    created_at=s.created_at,
                )
                for s in snapshots
            ],
            count=len(snapshots),
        )
    except Exception as e:
        logger.error(f"Error retrieving snapshots: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve snapshots")


@app.get("/v1/activity/search")
async def search_snapshots(
    q: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 100,
) -> SnapshotListResponse:
    """
    Search activity snapshots by content.
    
    Args:
        q: Optional search query (searches all text fields)
        device_id: Optional device ID filter
        limit: Maximum number of results (default 100)
        
    Returns:
        List of matching snapshots
    """
    try:
        store = get_activity_snapshot_store()
        snapshots = store.search(
            query=q,
            device_id=device_id,
            limit=limit,
        )
        return SnapshotListResponse(
            snapshots=[
                SnapshotResponse(
                    id=s.id,
                    device_id=s.device_id,
                    device_type=s.device_type,
                    captured_at=s.captured_at,
                    active_app=s.active_app,
                    window_title=s.window_title,
                    project_path=s.project_path,
                    git_branch=s.git_branch,
                    recent_files=s.recent_files,
                    notes=s.notes,
                    created_at=s.created_at,
                )
                for s in snapshots
            ],
            count=len(snapshots),
        )
    except Exception as e:
        logger.error(f"Error searching snapshots: {e}")
        raise HTTPException(status_code=500, detail="Failed to search snapshots")


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
