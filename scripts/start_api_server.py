#!/usr/bin/env python3
"""
Milton API Server
Provides REST endpoints and WebSocket streaming for the dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv(dotenv_path=ROOT_DIR / ".env")

from agents.cortex import CORTEX
from agents.frontier import FRONTIER
from agents.nexus import NEXUS
from goals.api import add_goal, list_goals
from memory.init_db import create_schema, get_client
from memory.operations import MemoryOperations
from milton_orchestrator.state_paths import resolve_state_dir
from milton_orchestrator.input_normalizer import normalize_incoming_input
from milton_orchestrator.reminders import ReminderStore, parse_time_expression
from storage.briefing_store import BriefingStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("milton.api")

MODEL_URL = os.getenv("LLM_API_URL") or os.getenv(
    "OLLAMA_API_URL", "http://localhost:8000"
)
MODEL_NAME = os.getenv(
    "LLM_MODEL", os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
)
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("VLLM_API_KEY")
    or os.getenv("OLLAMA_API_KEY")
)
STATE_DIR = resolve_state_dir()

# Initialize persistent stores
briefing_store = BriefingStore(STATE_DIR / "briefing.sqlite3")
reminder_store = ReminderStore(STATE_DIR / "reminders.sqlite3")

app = Flask(__name__)
CORS(app)
sock = Sock(app)

_REQUESTS: Dict[str, Dict[str, Any]] = {}
_REQUESTS_LOCK = threading.Lock()
_PROCESSED = set()
_PROCESSED_LOCK = threading.Lock()

_REQUEST_STATUS_MAP = {
    "accepted": "QUEUED",
    "queued": "QUEUED",
    "pending": "QUEUED",
    "in_progress": "RUNNING",
    "running": "RUNNING",
    "complete": "COMPLETE",
    "completed": "COMPLETE",
    "failed": "FAILED",
}
_TERMINAL_STATUSES = {"COMPLETE", "FAILED"}

_VECTOR_COUNT = 0
_VECTOR_COUNT_LOCK = threading.Lock()
_MEMORY_CACHE: Dict[str, Any] = {"timestamp": 0.0, "vector_count": 0}

_STATUS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "llm_up": True, "weaviate_up": True}
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()

nexus = NEXUS(model_url=MODEL_URL, model_name=MODEL_NAME)
cortex = CORTEX(model_url=MODEL_URL, model_name=MODEL_NAME)
frontier = FRONTIER(model_url=MODEL_URL, model_name=MODEL_NAME)

AGENT_MAP = {
    "NEXUS": nexus,
    "CORTEX": cortex,
    "FRONTIER": frontier,
}


def _now_iso() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_request_id() -> str:
    return f"req_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def _normalize_request_status(raw_status: Optional[str]) -> str:
    if not raw_status:
        return "UNKNOWN"
    lowered = str(raw_status).strip().lower()
    return _REQUEST_STATUS_MAP.get(lowered, str(raw_status).strip().upper())


def _send_ws(ws, message_type: str, **fields: Any) -> None:
    payload = {"type": message_type, "timestamp": _now_iso(), **fields}
    ws.send(json.dumps(payload))


def _chunk_text(text: str, words_per_chunk: int = 6) -> Iterable[str]:
    parts = re.findall(r"\S+|\s+", text)
    buffer = ""
    word_count = 0

    for part in parts:
        buffer += part
        if part.strip():
            word_count += 1
        if word_count >= words_per_chunk:
            yield buffer
            buffer = ""
            word_count = 0

    if buffer:
        yield buffer


def _persist_attachments(
    request_id: str, attachments: list[Any], state_dir: Path
) -> list[Path]:
    if not attachments:
        return []

    base_dir = state_dir / "attachments" / request_id
    base_dir.mkdir(parents=True, exist_ok=True)
    stored_paths: list[Path] = []

    for idx, attachment in enumerate(attachments, start=1):
        name = getattr(attachment, "name", None) or f"attachment_{idx:02d}"
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(name)).strip("._")
        if not safe_name:
            safe_name = f"attachment_{idx:02d}"
        path = base_dir / f"{idx:02d}_{safe_name}.json"
        payload = {
            "name": getattr(attachment, "name", None),
            "content_type": getattr(attachment, "content_type", None),
            "size": getattr(attachment, "size", None),
            "url": getattr(attachment, "url", None),
            "parse_error": getattr(attachment, "parse_error", None),
            "raw": getattr(attachment, "raw", None),
            "text": getattr(attachment, "text", None),
        }
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stored_paths.append(path)
        except OSError as exc:
            logger.warning("Failed to persist attachment %s: %s", name, exc)

    return stored_paths


_GOAL_INTENT_PATTERNS = [
    re.compile(r"^\s*(?:i\s+want\s+to|i\s+need\s+to|i\s+plan\s+to)\s+(?P<goal>.+)$", re.I),
    re.compile(r"^\s*(?:i\s+should)\s+(?P<goal>.+)$", re.I),
    re.compile(r"^\s*(?:please\s+)?remember\s+to\s+(?P<goal>.+)$", re.I),
    re.compile(r"^\s*(?:remind\s+me\s+to)\s+(?P<goal>.+)$", re.I),
    re.compile(r"^\s*(?:add\s+to\s+goals?|add\s+goal|goal|todo)\s*[:\-]\s*(?P<goal>.+)$", re.I),
]


def _normalize_goal_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.strip(" \"'`")
    cleaned = re.sub(r"[.!?]+$", "", cleaned).strip()
    cleaned = re.sub(r"\bmyself\b", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"^to\s+", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_goal_text(query: str) -> Optional[str]:
    for line in query.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in _GOAL_INTENT_PATTERNS:
            match = pattern.match(stripped)
            if match:
                goal = match.group("goal").strip()
                normalized = _normalize_goal_text(goal)
                return normalized or None
    return None


def _goal_exists(goal_text: str) -> Optional[str]:
    normalized = _normalize_goal_text(goal_text).lower()
    for scope in ("daily", "weekly", "monthly"):
        for goal in list_goals(scope, base_dir=STATE_DIR):
            existing = _normalize_goal_text(str(goal.get("text", ""))).lower()
            if existing == normalized and goal.get("id"):
                return str(goal["id"])
    return None


def _capture_goal(
    query: str, goal_candidates: Optional[list[str]] = None
) -> Optional[Dict[str, str]]:
    candidate_text = None
    if goal_candidates:
        for candidate in goal_candidates:
            candidate_text = _normalize_goal_text(str(candidate))
            if candidate_text:
                break

    goal_text = candidate_text or _extract_goal_text(query)
    if not goal_text:
        return None

    try:
        existing_id = _goal_exists(goal_text)
        if existing_id:
            return {"id": existing_id, "text": goal_text, "status": "existing"}

        goal_id = add_goal(
            "daily",
            goal_text,
            tags=["captured", "intent"],
            base_dir=STATE_DIR,
        )
        return {"id": goal_id, "text": goal_text, "status": "added"}
    except Exception as exc:
        logger.warning("Goal capture failed: %s", exc)
        return None


def _format_goal_capture(capture: Dict[str, str]) -> str:
    text = capture.get("text", "goal")
    goal_id = capture.get("id")
    status = capture.get("status")
    if status == "existing":
        suffix = f" (id {goal_id})" if goal_id else ""
        return f"Goal already tracked: {text}{suffix}"
    if status == "added":
        suffix = f" (id {goal_id})" if goal_id else ""
        return f"Goal captured: {text}{suffix}"
    return f"Goal captured: {text}"


def _check_url(url: str, timeout: float = 1.5) -> bool:
    try:
        headers = {}
        if LLM_API_KEY and url.startswith(MODEL_URL.rstrip("/")):
            headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
        resp = requests.get(url, timeout=timeout, headers=headers)
        return resp.status_code == 200
    except Exception:
        return False


def _get_status_flags() -> Tuple[bool, bool]:
    now = time.time()
    if now - _STATUS_CACHE["timestamp"] < 5:
        return _STATUS_CACHE["llm_up"], _STATUS_CACHE["weaviate_up"]

    llm_up = _check_url(f"{MODEL_URL.rstrip('/')}/v1/models")
    weaviate_up = _check_url("http://localhost:8080/v1/meta")

    _STATUS_CACHE["timestamp"] = now
    _STATUS_CACHE["llm_up"] = llm_up
    _STATUS_CACHE["weaviate_up"] = weaviate_up
    return llm_up, weaviate_up


def _ensure_schema() -> bool:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True
        try:
            client = get_client()
            create_schema(client)
            client.close()
            _SCHEMA_READY = True
            logger.info("Weaviate schema ready")
            return True
        except Exception as exc:
            logger.warning("Weaviate schema init failed: %s", exc)
            _SCHEMA_READY = False
            return False


def _route_query(query: str, agent_override: Optional[str]) -> Dict[str, Any]:
    if agent_override:
        return {
            "target": agent_override,
            "reasoning": "User selected agent",
            "confidence": 0.99,
            "context": {},
        }

    try:
        routing = nexus.route_request(query)
        if isinstance(routing, dict):
            target = str(routing.get("target", "NEXUS")).strip()
            return {
                "target": target,
                "reasoning": routing.get("reasoning", "Auto routing"),
                "confidence": routing.get("confidence", 0.92),
                "context": routing.get("context", {}),
            }

        route = str(getattr(routing, "route", "nexus")).strip().lower()
        tool_name = getattr(routing, "tool_name", None)
        if route == "tool" and tool_name:
            target = str(tool_name)
        elif route == "cortex":
            target = "CORTEX"
        elif route == "frontier":
            target = "FRONTIER"
        else:
            target = "NEXUS"

        return {
            "target": target,
            "reasoning": getattr(routing, "rationale", "Auto routing"),
            "confidence": 0.92,
            "context": {
                "context_ids": getattr(routing, "context_ids", []),
                "tool_name": tool_name,
            },
        }
    except Exception as exc:
        logger.warning("Routing failed: %s", exc)
        return {
            "target": "NEXUS",
            "reasoning": "Routing failed; defaulting to NEXUS",
            "confidence": 0.5,
            "context": {},
        }


def _run_agent(agent_name: str, query: str, use_web: Optional[bool] = None) -> str:
    agent = AGENT_MAP[agent_name]
    if agent_name == "NEXUS" and hasattr(agent, "answer"):
        return agent.answer(query, use_web=use_web)
    return agent._call_llm(query, system_prompt=agent.system_prompt, max_tokens=300)


def _run_integration(target: str, query: str) -> str:
    target_lower = target.lower()
    if target_lower == "weather":
        weather = nexus.weather.current_weather()
        return (
            f"Current weather for {nexus.weather.location}: {weather['temp']}F, "
            f"{weather['condition']} (high {weather['high']}F, low {weather['low']}F, "
            f"humidity {weather['humidity']}%)."
        )
    if target_lower == "news":
        articles = nexus.news.get_top_headlines(category="technology", max_results=5)
        return nexus.news.generate_brief(articles, topic="technology")
    if target_lower == "calendar":
        events = nexus.calendar.get_today_events()
        return nexus.calendar.format_events(events)
    if target_lower == "home_assistant":
        if not nexus.home_assistant.url or not nexus.home_assistant.token:
            return "Home Assistant not configured. Set HOME_ASSISTANT_URL/TOKEN."
        states = nexus.home_assistant.get_all_states()
        return f"Home Assistant connected ({len(states)} entities)."

    return f"Integration '{target}' not implemented. Query: {query}"


def _store_memory(agent: str, query: str, response: str) -> Optional[str]:
    global _VECTOR_COUNT
    global _SCHEMA_READY
    try:
        if not _ensure_schema():
            return None
        with MemoryOperations() as mem:
            vector_id = mem.add_short_term(
                agent=agent,
                content=response,
                context=query,
                metadata={"source": "api_server"},
            )
        with _VECTOR_COUNT_LOCK:
            _VECTOR_COUNT += 1
        return vector_id
    except Exception as exc:
        logger.warning("Memory store failed: %s", exc)
        _SCHEMA_READY = False
        return None


def _get_memory_snapshot() -> Tuple[int, float]:
    global _VECTOR_COUNT
    now = time.time()
    with _VECTOR_COUNT_LOCK:
        fallback_count = _VECTOR_COUNT

    if now - _MEMORY_CACHE["timestamp"] < 5:
        vector_count = _MEMORY_CACHE["vector_count"]
    else:
        vector_count = fallback_count
        if _ensure_schema():
            try:
                with MemoryOperations() as mem:
                    collection = mem.client.collections.get("ShortTermMemory")
                    result = collection.aggregate.over_all(total_count=True)
                    vector_count = int(result.total_count or 0)
            except Exception as exc:
                logger.warning("Memory count lookup failed: %s", exc)

        _MEMORY_CACHE["timestamp"] = now
        _MEMORY_CACHE["vector_count"] = vector_count

        with _VECTOR_COUNT_LOCK:
            if vector_count > _VECTOR_COUNT:
                _VECTOR_COUNT = vector_count

    memory_mb = round(vector_count * 0.0069, 1)
    return vector_count, memory_mb


@app.route("/api/ask", methods=["POST"])
def ask() -> Any:
    data = request.get_json(silent=True) or {}
    query_raw = str(data.get("query", "")).strip()
    normalized = normalize_incoming_input(query_raw, raw_data=data)
    query = normalized.semantic_input.strip()

    if not query:
        return jsonify({"error": "Missing 'query'"}), 400

    goal_capture = _capture_goal(
        query, goal_candidates=normalized.structured_fields.get("goals")
    )

    agent_override = data.get("agent")
    use_web = data.get("use_web")
    if use_web is not None:
        use_web = bool(use_web)
    if agent_override:
        agent_override = str(agent_override).upper()
        if agent_override not in AGENT_MAP:
            return jsonify({"error": "Invalid agent"}), 400

    routing = _route_query(query, agent_override)
    target = str(routing["target"])
    target_upper = target.upper()
    integration_target = None

    logger.info(
        "Routing decision: target=%s confidence=%.2f",
        target,
        routing.get("confidence", 0.0),
    )

    if target_upper in AGENT_MAP:
        agent_assigned = target_upper
    else:
        agent_assigned = "NEXUS"
        integration_target = target

    request_id = _make_request_id()
    created_at = _now_iso()

    attachment_paths = _persist_attachments(
        request_id, normalized.attachments, STATE_DIR
    )
    if attachment_paths:
        logger.info(
            "Stored %d attachment(s) for request_id=%s",
            len(attachment_paths),
            request_id,
        )

    logger.info(
        "Normalized input: type=%s length=%d attachments=%d",
        normalized.input_type,
        normalized.normalized_length,
        len(normalized.attachments),
    )

    with _REQUESTS_LOCK:
        _REQUESTS[request_id] = {
            "id": request_id,
            "query": query,
            "agent_assigned": agent_assigned,
            "integration_target": integration_target,
            "routing_reasoning": routing["reasoning"],
            "confidence": routing["confidence"],
            "status": "queued",
            "created_at": created_at,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "response": None,
            "error": None,
            "use_web": use_web,
            "goal_capture": goal_capture,
        }

    response = {
        "request_id": request_id,
        "status": "accepted",
        "agent_assigned": agent_assigned,
        "confidence": routing["confidence"],
    }
    if goal_capture:
        response["goal_capture"] = goal_capture

    return jsonify(response)


@sock.route("/ws/request/<request_id>")
def stream_request(ws, request_id: str) -> None:
    with _REQUESTS_LOCK:
        req = _REQUESTS.get(request_id)

    if not req:
        _send_ws(ws, "token", content=f"Unknown request ID: {request_id}")
        _send_ws(ws, "complete", total_tokens=0, duration_ms=0)
        return

    with _PROCESSED_LOCK:
        if request_id in _PROCESSED:
            _send_ws(ws, "token", content="Request already completed.")
            _send_ws(ws, "complete", total_tokens=0, duration_ms=0)
            return
        _PROCESSED.add(request_id)

    agent_name = req["agent_assigned"]
    integration_target = req.get("integration_target")

    with _REQUESTS_LOCK:
        req["status"] = "running"
        if not req.get("started_at"):
            req["started_at"] = _now_iso()

    _send_ws(
        ws,
        "routing",
        agent=agent_name,
        confidence=req["confidence"],
        reasoning=req["routing_reasoning"],
    )
    _send_ws(ws, "thinking", content=f"Processing with {agent_name}...")

    start_time = time.time()
    response_text = ""
    error_text = None

    try:
        if integration_target:
            response_text = _run_integration(integration_target, req["query"])
        else:
            response_text = _run_agent(
                agent_name, req["query"], use_web=req.get("use_web")
            )
    except Exception as exc:
        error_text = f"Error: {exc}"
        response_text = error_text

    goal_capture = req.get("goal_capture")
    if goal_capture:
        response_text = f"{response_text}\n\n{_format_goal_capture(goal_capture)}"

    for chunk in _chunk_text(response_text):
        _send_ws(ws, "token", content=chunk)

    vector_id = _store_memory(agent_name, req["query"], response_text)
    if vector_id:
        _send_ws(ws, "memory", vector_id=vector_id, stored=True, embedding_size=1536)
    else:
        _send_ws(ws, "memory", vector_id="unavailable", stored=False)

    duration_ms = int((time.time() - start_time) * 1000)
    total_tokens = len(response_text.split())
    _send_ws(ws, "complete", total_tokens=total_tokens, duration_ms=duration_ms)

    with _REQUESTS_LOCK:
        req["status"] = "failed" if error_text else "complete"
        req["duration_ms"] = duration_ms
        req["response"] = response_text
        req["completed_at"] = _now_iso()
        req["error"] = error_text


@app.route("/api/system-state", methods=["GET"])
def system_state() -> Any:
    llm_up, weaviate_up = _get_status_flags()
    vector_count, memory_mb = _get_memory_snapshot()
    timestamp = _now_iso()

    status = "UP" if llm_up else "DOWN"
    memory_status = "UP" if weaviate_up else "DOWN"

    return jsonify(
        {
            "nexus": {"status": status, "last_check": timestamp},
            "cortex": {
                "status": status,
                "running_jobs": 0,
                "queued_jobs": 0,
                "last_check": timestamp,
            },
            "frontier": {"status": status, "last_check": timestamp},
            "memory": {
                "status": memory_status,
                "vector_count": vector_count,
                "memory_mb": memory_mb,
                "last_check": timestamp,
            },
        }
    )


@app.route("/api/memory-stats", methods=["GET"])
def memory_stats() -> Any:
    vector_count, memory_mb = _get_memory_snapshot()
    with _REQUESTS_LOCK:
        total_queries = len(_REQUESTS)
    return jsonify(
        {
            "total_queries": total_queries,
            "vector_count": vector_count,
            "memory_size_mb": memory_mb,
        }
    )


@app.route("/api/recent-requests", methods=["GET"])
def recent_requests() -> Any:
    with _REQUESTS_LOCK:
        recent = list(_REQUESTS.values())[-20:]

    payload = []
    for r in recent:
        status = _normalize_request_status(r.get("status"))
        is_terminal = status in _TERMINAL_STATUSES
        duration_ms = r.get("duration_ms") if is_terminal else None
        duration_s = (duration_ms / 1000) if duration_ms is not None else None
        payload.append(
            {
                "id": r["id"],
                "query": r["query"],
                "agent": r["agent_assigned"],
                "timestamp": r["created_at"],
                "created_at": r["created_at"],
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "status": status,
                "duration_ms": duration_ms,
                "duration_s": duration_s,
                "error": r.get("error"),
            }
        )
    return jsonify(payload)


# ==============================================================================
# Read-Only System State Endpoints
# ==============================================================================

@app.route("/health", methods=["GET"])
def health() -> Any:
    """
    Health check endpoint (read-only).

    Returns basic service health status.
    """
    llm_up, weaviate_up = _get_status_flags()

    return jsonify({
        "status": "healthy" if llm_up else "degraded",
        "llm": "up" if llm_up else "down",
        "memory": "up" if weaviate_up else "down",
        "timestamp": _now_iso()
    })


@app.route("/config", methods=["GET"])
def effective_config() -> Any:
    """
    Effective configuration endpoint (read-only, no auth required).

    Returns the resolved configuration that this API server is using,
    including state directory, service endpoints, and memory backend.
    This ensures all Milton entrypoints use the same "brain".
    """
    from milton_orchestrator.effective_config import get_effective_config
    config = get_effective_config()
    return jsonify(config.to_dict())


@app.route("/api/queue", methods=["GET"])
def queue_status() -> Any:
    """
    Job queue status endpoint (read-only).

    Returns current job queue state: queued, in_progress, completed, failed.
    """
    try:
        import milton_queue as queue_api

        # Get job counts by status
        tonight_dir = STATE_DIR / "jobs" / "tonight"
        archive_dir = STATE_DIR / "jobs" / "archive"

        queued_jobs = []
        in_progress_jobs = []

        if tonight_dir.exists():
            for job_file in tonight_dir.glob("*.json"):
                try:
                    import json as json_lib
                    with job_file.open() as f:
                        job = json_lib.load(f)

                    status = job.get("status", "queued")
                    job_info = {
                        "id": job.get("id"),
                        "type": job.get("type"),
                        "priority": job.get("priority"),
                        "created_at": job.get("created_at"),
                        "status": status
                    }

                    if status == "in_progress":
                        in_progress_jobs.append(job_info)
                    else:
                        queued_jobs.append(job_info)
                except Exception as e:
                    logger.warning(f"Error reading job file {job_file}: {e}")

        # Count completed/failed from archive (limit to recent)
        completed_count = 0
        failed_count = 0

        if archive_dir.exists():
            import json as json_lib
            for job_file in sorted(archive_dir.glob("*.json"), reverse=True)[:100]:
                try:
                    with job_file.open() as f:
                        job = json_lib.load(f)
                    status = job.get("status", "")
                    if "fail" in status.lower():
                        failed_count += 1
                    else:
                        completed_count += 1
                except Exception:
                    pass

        return jsonify({
            "queued": len(queued_jobs),
            "in_progress": len(in_progress_jobs),
            "completed_recent": completed_count,
            "failed_recent": failed_count,
            "queued_jobs": queued_jobs[:10],  # Show first 10
            "in_progress_jobs": in_progress_jobs,
            "timestamp": _now_iso()
        })

    except Exception as e:
        logger.error(f"Queue status error: {e}", exc_info=True)
        return jsonify({"error": "Failed to read queue status"}), 500


# NOTE: /api/reminders GET endpoint moved to Reminders Endpoints section below
# (Was previously a stub using non-existent milton_reminders.cli module)


@app.route("/api/outputs", methods=["GET"])
def outputs() -> Any:
    """
    Latest outputs endpoint (read-only).

    Returns latest N artifact files from STATE_DIR/outputs.

    Query params:
    - limit: Number of outputs to return (default: 20, max: 100)
    """
    try:
        limit = min(int(request.args.get("limit", "20")), 100)

        outputs_dir = STATE_DIR / "outputs"
        if not outputs_dir.exists():
            return jsonify({"outputs": [], "count": 0, "message": "No outputs directory"})

        # Get all output files sorted by modification time
        output_files = []
        for output_file in outputs_dir.glob("*"):
            if output_file.is_file():
                stat = output_file.stat()
                output_files.append({
                    "name": output_file.name,
                    "path": str(output_file.relative_to(STATE_DIR)),
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 2),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })

        # Sort by modification time (newest first)
        output_files.sort(key=lambda x: x["modified_at"], reverse=True)

        # Note: Tailscale serve URLs would be added here if configured
        # For now, just provide file paths

        limited_outputs = output_files[:limit]
        return jsonify({
            "outputs": limited_outputs,
            "count": len(limited_outputs),
            "total": len(output_files),
            "timestamp": _now_iso()
        })

    except Exception as e:
        logger.error(f"Outputs error: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch outputs"}), 500


@app.route("/api/memory/search", methods=["GET"])
def memory_search() -> Any:
    """
    Memory search endpoint (read-only).

    Search short-term memory using deterministic retrieval.

    Query params:
    - query: Search query (required)
    - top_k: Number of results to return (default: 5, max: 50)
    """
    try:
        query = request.args.get("query", "").strip()
        if not query:
            return jsonify({"error": "Missing 'query' parameter"}), 400

        top_k = min(int(request.args.get("top_k", "5")), 50)

        # Ensure schema is ready
        if not _ensure_schema():
            return jsonify({"error": "Memory system not available"}), 503

        # Use existing memory retrieval
        from memory.retrieve import query_relevant

        results = query_relevant(query, top_k=top_k)

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.get("id"),
                "content": result.get("content"),
                "context": result.get("context"),
                "agent": result.get("agent"),
                "timestamp": result.get("timestamp"),
                "distance": result.get("distance")
            })

        return jsonify({
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "timestamp": _now_iso()
        })

    except Exception as e:
        logger.error(f"Memory search error: {e}", exc_info=True)
        return jsonify({"error": "Memory search failed"}), 500


# ==============================================================================
# Briefing Items Endpoints
# ==============================================================================

@app.route("/api/briefing/items", methods=["POST"])
def create_briefing_item() -> Any:
    """
    Create a custom briefing item.

    Request body (JSON):
    - content: str (required) - The item text
    - priority: int (optional, default 0) - Higher = more important
    - source: str (optional, default "manual") - Origin of the item
    - due_at: str (optional) - ISO8601 UTC due date
    - expires_at: str (optional) - ISO8601 UTC expiration date

    Returns:
    - 201: {"id": int, "status": "active", "created_at": str}
    - 400: {"error": str} on validation failure
    """
    try:
        data = request.get_json(silent=True) or {}

        content = data.get("content", "").strip() if isinstance(data.get("content"), str) else ""
        if not content:
            return jsonify({"error": "Missing required field: content"}), 400

        priority = data.get("priority", 0)
        if not isinstance(priority, int):
            try:
                priority = int(priority)
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid priority: must be integer"}), 400

        source = data.get("source", "manual")
        if not isinstance(source, str):
            return jsonify({"error": "Invalid source: must be string"}), 400

        due_at = data.get("due_at")
        expires_at = data.get("expires_at")

        # Validate ISO8601 format if provided
        for field_name, value in [("due_at", due_at), ("expires_at", expires_at)]:
            if value is not None:
                if not isinstance(value, str):
                    return jsonify({"error": f"Invalid {field_name}: must be ISO8601 string"}), 400

        item_id = briefing_store.add_item(
            content=content,
            priority=priority,
            source=source,
            due_at=due_at,
            expires_at=expires_at,
        )

        item = briefing_store.get_item(item_id)
        return jsonify({
            "id": item_id,
            "status": "active",
            "created_at": item.created_at if item else _now_iso(),
        }), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Create briefing item error: {e}", exc_info=True)
        return jsonify({"error": "Failed to create briefing item"}), 500


@app.route("/api/briefing/items", methods=["GET"])
def list_briefing_items() -> Any:
    """
    List briefing items with optional filtering.

    Query params:
    - status: str (optional) - Filter by status ("active", "done", "dismissed")
    - include_expired: bool (optional, default false) - Include expired items

    Returns:
    - 200: {"items": [...], "count": int, "timestamp": str}
    """
    try:
        status = request.args.get("status")
        if status and status not in ("active", "done", "dismissed"):
            return jsonify({"error": "Invalid status: must be 'active', 'done', or 'dismissed'"}), 400

        include_expired = request.args.get("include_expired", "").lower() in ("true", "1", "yes")

        items = briefing_store.list_items(status=status, include_expired=include_expired)

        return jsonify({
            "items": [item.to_dict() for item in items],
            "count": len(items),
            "timestamp": _now_iso(),
        })

    except Exception as e:
        logger.error(f"List briefing items error: {e}", exc_info=True)
        return jsonify({"error": "Failed to list briefing items"}), 500


@app.route("/api/briefing/items/<int:item_id>/done", methods=["POST"])
def mark_briefing_item_done(item_id: int) -> Any:
    """
    Mark a briefing item as done.

    Returns:
    - 200: {"id": int, "status": "done", "completed_at": str}
    - 404: {"error": str} if item not found or already completed
    """
    try:
        success = briefing_store.mark_done(item_id)
        if not success:
            item = briefing_store.get_item(item_id)
            if item is None:
                return jsonify({"error": f"Item {item_id} not found"}), 404
            return jsonify({"error": f"Item {item_id} is not active (status: {item.status})"}), 400

        item = briefing_store.get_item(item_id)
        return jsonify({
            "id": item_id,
            "status": "done",
            "completed_at": item.completed_at if item else _now_iso(),
        })

    except Exception as e:
        logger.error(f"Mark briefing item done error: {e}", exc_info=True)
        return jsonify({"error": "Failed to mark item done"}), 500


@app.route("/api/briefing/items/<int:item_id>/dismiss", methods=["POST"])
def dismiss_briefing_item(item_id: int) -> Any:
    """
    Dismiss a briefing item (hide without marking done).

    Returns:
    - 200: {"id": int, "status": "dismissed", "dismissed_at": str}
    - 404: {"error": str} if item not found or already dismissed
    """
    try:
        success = briefing_store.mark_dismissed(item_id)
        if not success:
            item = briefing_store.get_item(item_id)
            if item is None:
                return jsonify({"error": f"Item {item_id} not found"}), 404
            return jsonify({"error": f"Item {item_id} is not active (status: {item.status})"}), 400

        item = briefing_store.get_item(item_id)
        return jsonify({
            "id": item_id,
            "status": "dismissed",
            "dismissed_at": item.dismissed_at if item else _now_iso(),
        })

    except Exception as e:
        logger.error(f"Dismiss briefing item error: {e}", exc_info=True)
        return jsonify({"error": "Failed to dismiss item"}), 500


# ==============================================================================
# Reminders Endpoints (wrapping existing ReminderStore)
# ==============================================================================

@app.route("/api/reminders", methods=["POST"])
def create_reminder() -> Any:
    """
    Create a new reminder.

    Request body (JSON):
    - message: str (required) - Reminder text
    - remind_at: str (required) - ISO8601 UTC timestamp OR natural language
    - kind: str (optional, default "REMIND") - Reminder type
    - timezone: str (optional, default "America/New_York")

    Returns:
    - 201: {"id": int, "status": "scheduled", "remind_at": int, "message": str}
    - 400: {"error": str} on validation failure
    """
    try:
        data = request.get_json(silent=True) or {}

        message = data.get("message", "").strip() if isinstance(data.get("message"), str) else ""
        if not message:
            return jsonify({"error": "Missing required field: message"}), 400

        remind_at_raw = data.get("remind_at")
        if not remind_at_raw:
            return jsonify({"error": "Missing required field: remind_at"}), 400

        kind = data.get("kind", "REMIND")
        timezone = data.get("timezone", "America/New_York")

        # Parse remind_at - could be timestamp or natural language
        remind_at_ts: Optional[int] = None

        if isinstance(remind_at_raw, (int, float)):
            remind_at_ts = int(remind_at_raw)
        elif isinstance(remind_at_raw, str):
            # Try ISO8601 first
            try:
                from datetime import datetime, timezone as tz
                # Handle Z suffix
                remind_at_str = remind_at_raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(remind_at_str)
                remind_at_ts = int(dt.timestamp())
            except ValueError:
                # Try natural language parsing
                remind_at_ts = parse_time_expression(remind_at_raw, timezone=timezone)

        if remind_at_ts is None:
            return jsonify({"error": f"Could not parse remind_at: '{remind_at_raw}'"}), 400

        reminder_id = reminder_store.add_reminder(
            kind=kind,
            due_at=remind_at_ts,
            message=message,
            timezone=timezone,
        )

        return jsonify({
            "id": reminder_id,
            "status": "scheduled",
            "remind_at": remind_at_ts,
            "message": message,
        }), 201

    except Exception as e:
        logger.error(f"Create reminder error: {e}", exc_info=True)
        return jsonify({"error": "Failed to create reminder"}), 500


@app.route("/api/reminders", methods=["GET"])
def list_reminders_endpoint() -> Any:
    """
    List reminders with optional filtering.

    Query params:
    - status: str (optional) - "scheduled" (pending), "sent", "canceled", or "all"
    - limit: int (optional, default 50) - Max results

    Returns:
    - 200: {"reminders": [...], "count": int, "timestamp": str}
    """
    try:
        status = request.args.get("status", "scheduled")
        limit = min(int(request.args.get("limit", "50")), 200)

        include_sent = status in ("sent", "all")
        include_canceled = status in ("canceled", "all")

        reminders = reminder_store.list_reminders(
            include_sent=include_sent,
            include_canceled=include_canceled,
        )

        # Additional filtering for specific statuses
        if status == "sent":
            reminders = [r for r in reminders if r.sent_at is not None]
        elif status == "canceled":
            reminders = [r for r in reminders if r.canceled_at is not None]
        elif status == "scheduled":
            reminders = [r for r in reminders if r.sent_at is None and r.canceled_at is None]

        reminders = reminders[:limit]

        return jsonify({
            "reminders": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "message": r.message,
                    "remind_at": r.due_at,
                    "created_at": r.created_at,
                    "sent_at": r.sent_at,
                    "canceled_at": r.canceled_at,
                    "timezone": r.timezone,
                    "status": "sent" if r.sent_at else ("canceled" if r.canceled_at else "scheduled"),
                }
                for r in reminders
            ],
            "count": len(reminders),
            "timestamp": _now_iso(),
        })

    except Exception as e:
        logger.error(f"List reminders error: {e}", exc_info=True)
        return jsonify({"error": "Failed to list reminders"}), 500


@app.route("/api/reminders/<int:reminder_id>/cancel", methods=["POST"])
def cancel_reminder(reminder_id: int) -> Any:
    """
    Cancel a scheduled reminder.

    Returns:
    - 200: {"id": int, "status": "canceled", "canceled_at": int}
    - 404: {"error": str} if reminder not found or already sent/canceled
    """
    try:
        success = reminder_store.cancel_reminder(reminder_id)
        if not success:
            reminder = reminder_store.get_reminder(reminder_id)
            if reminder is None:
                return jsonify({"error": f"Reminder {reminder_id} not found"}), 404
            if reminder.sent_at:
                return jsonify({"error": f"Reminder {reminder_id} already sent"}), 400
            if reminder.canceled_at:
                return jsonify({"error": f"Reminder {reminder_id} already canceled"}), 400
            return jsonify({"error": f"Could not cancel reminder {reminder_id}"}), 400

        reminder = reminder_store.get_reminder(reminder_id)
        return jsonify({
            "id": reminder_id,
            "status": "canceled",
            "canceled_at": reminder.canceled_at if reminder else int(time.time()),
        })

    except Exception as e:
        logger.error(f"Cancel reminder error: {e}", exc_info=True)
        return jsonify({"error": "Failed to cancel reminder"}), 500


if __name__ == "__main__":
    # Allow port to be configured via environment variable
    api_port = int(os.getenv("MILTON_API_PORT", "8001"))
    logger.info(f"Starting Milton API server at http://localhost:{api_port}")
    logger.info("SECURITY WARNING: This server is for local development only")
    logger.info("Do NOT expose to public internet without authentication")
    # Bind to 0.0.0.0 to allow access from other machines (e.g., via Tailscale)
    # SECURITY: Only expose on trusted networks
    app.run(host="0.0.0.0", port=api_port, debug=True, use_reloader=False)
