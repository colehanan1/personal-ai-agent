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
STATE_DIR = Path(os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR") or ROOT_DIR)

app = Flask(__name__)
CORS(app)
sock = Sock(app)

_REQUESTS: Dict[str, Dict[str, Any]] = {}
_REQUESTS_LOCK = threading.Lock()
_PROCESSED = set()
_PROCESSED_LOCK = threading.Lock()

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
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_request_id() -> str:
    return f"req_{int(time.time())}_{uuid.uuid4().hex[:6]}"


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
    for pattern in _GOAL_INTENT_PATTERNS:
        match = pattern.match(query)
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


def _capture_goal(query: str) -> Optional[Dict[str, str]]:
    goal_text = _extract_goal_text(query)
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
    query = str(data.get("query", "")).strip()

    if not query:
        return jsonify({"error": "Missing 'query'"}), 400

    goal_capture = _capture_goal(query)

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

    if target_upper in AGENT_MAP:
        agent_assigned = target_upper
    else:
        agent_assigned = "NEXUS"
        integration_target = target

    request_id = _make_request_id()
    created_at = _now_iso()

    with _REQUESTS_LOCK:
        _REQUESTS[request_id] = {
            "id": request_id,
            "query": query,
            "agent_assigned": agent_assigned,
            "integration_target": integration_target,
            "routing_reasoning": routing["reasoning"],
            "confidence": routing["confidence"],
            "status": "accepted",
            "created_at": created_at,
            "duration_ms": None,
            "response": None,
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

    payload = [
        {
            "id": r["id"],
            "query": r["query"],
            "agent": r["agent_assigned"],
            "timestamp": r["created_at"],
            "status": "COMPLETE" if r["status"] == "complete" else "FAILED",
            "duration_ms": r["duration_ms"],
        }
        for r in recent
    ]
    return jsonify(payload)


if __name__ == "__main__":
    logger.info("Starting Milton API server at http://localhost:8001")
    app.run(host="localhost", port=8001, debug=True, use_reloader=False)
