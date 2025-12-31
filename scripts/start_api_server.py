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
    "LLM_MODEL", os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-405B-Instruct")
)
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("VLLM_API_KEY")
    or os.getenv("OLLAMA_API_KEY")
)

app = Flask(__name__)
CORS(app)
sock = Sock(app)

_REQUESTS: Dict[str, Dict[str, Any]] = {}
_REQUESTS_LOCK = threading.Lock()
_PROCESSED = set()
_PROCESSED_LOCK = threading.Lock()

_VECTOR_COUNT = 0
_VECTOR_COUNT_LOCK = threading.Lock()

_STATUS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "llm_up": True, "weaviate_up": True}

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


def _check_url(url: str, timeout: float = 1.5) -> bool:
    try:
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
        resp = requests.get(url, timeout=timeout, headers=headers)
        if resp.status_code == 401:
            return False
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
        target = str(routing.get("target", "NEXUS")).strip()
        return {
            "target": target,
            "reasoning": routing.get("reasoning", "Auto routing"),
            "confidence": 0.92,
            "context": routing.get("context", {}),
        }
    except Exception as exc:
        logger.warning("Routing failed: %s", exc)
        return {
            "target": "NEXUS",
            "reasoning": "Routing failed; defaulting to NEXUS",
            "confidence": 0.5,
            "context": {},
        }


def _run_agent(agent_name: str, query: str) -> str:
    agent = AGENT_MAP[agent_name]
    return agent._call_llm(query, system_prompt=agent.system_prompt)


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
    try:
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
        return None


def _get_memory_snapshot() -> Tuple[int, float]:
    with _VECTOR_COUNT_LOCK:
        vector_count = _VECTOR_COUNT
    memory_mb = round(vector_count * 0.0069, 1)
    return vector_count, memory_mb


@app.route("/api/ask", methods=["POST"])
def ask() -> Any:
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()

    if not query:
        return jsonify({"error": "Missing 'query'"}), 400

    agent_override = data.get("agent")
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
        }

    return jsonify(
        {
            "request_id": request_id,
            "status": "accepted",
            "agent_assigned": agent_assigned,
            "confidence": routing["confidence"],
        }
    )


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
            response_text = _run_agent(agent_name, req["query"])
    except Exception as exc:
        error_text = f"Error: {exc}"
        response_text = error_text

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
