"""
Request lifecycle tests for /api/ask and /api/recent-requests.
"""

from pathlib import Path
from unittest.mock import patch
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def app():
    from scripts.start_api_server import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def clear_requests():
    import scripts.start_api_server as server

    with server._REQUESTS_LOCK:
        server._REQUESTS.clear()
    with server._PROCESSED_LOCK:
        server._PROCESSED.clear()
    yield
    with server._REQUESTS_LOCK:
        server._REQUESTS.clear()
    with server._PROCESSED_LOCK:
        server._PROCESSED.clear()


def _seed_request(server, request_id, status, duration_ms=None, error=None):
    created_at = "2026-01-02T12:00:00Z"
    started_at = "2026-01-02T12:00:01Z" if status in {"complete", "failed"} else None
    completed_at = "2026-01-02T12:00:02Z" if status in {"complete", "failed"} else None
    with server._REQUESTS_LOCK:
        server._REQUESTS[request_id] = {
            "id": request_id,
            "query": "Test query",
            "agent_assigned": "NEXUS",
            "routing_reasoning": "Test",
            "confidence": 0.99,
            "status": status,
            "created_at": created_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "response": "OK",
            "error": error,
            "use_web": None,
            "goal_capture": None,
        }


def test_recent_requests_queued_not_failed(client, clear_requests, tmp_path):
    with patch(
        "scripts.start_api_server._route_query",
        return_value={
            "target": "NEXUS",
            "reasoning": "test",
            "confidence": 0.99,
            "context": {},
        },
    ), patch("scripts.start_api_server.STATE_DIR", tmp_path):
        response = client.post("/api/ask", json={"query": "Hello"})

    assert response.status_code == 200
    request_id = response.get_json()["request_id"]

    recent = client.get("/api/recent-requests").get_json()
    req = next((r for r in recent if r["id"] == request_id), None)

    assert req is not None
    assert req["status"] == "QUEUED"
    assert req["duration_ms"] is None
    assert req["duration_s"] is None
    assert req["started_at"] is None
    assert req["completed_at"] is None


def test_recent_requests_complete_duration(client, clear_requests):
    import scripts.start_api_server as server

    _seed_request(server, "req_complete", "complete", duration_ms=1250)
    recent = client.get("/api/recent-requests").get_json()
    req = next((r for r in recent if r["id"] == "req_complete"), None)

    assert req is not None
    assert req["status"] == "COMPLETE"
    assert req["duration_ms"] == 1250
    assert req["duration_s"] == pytest.approx(1.25)
    assert req["error"] is None


def test_recent_requests_failed_error(client, clear_requests):
    import scripts.start_api_server as server

    _seed_request(
        server, "req_failed", "failed", duration_ms=500, error="Error: boom"
    )
    recent = client.get("/api/recent-requests").get_json()
    req = next((r for r in recent if r["id"] == "req_failed"), None)

    assert req is not None
    assert req["status"] == "FAILED"
    assert req["duration_ms"] == 500
    assert req["duration_s"] == pytest.approx(0.5)
    assert req["error"] == "Error: boom"
