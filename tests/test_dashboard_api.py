"""
Unit tests for Milton Dashboard API (read-only endpoints).

Tests:
- GET /health
- GET /api/queue
- GET /api/reminders
- GET /api/outputs
- GET /api/memory/search
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

pytestmark = pytest.mark.integration(reason="API server setup is slow; opt-in only.")


@pytest.fixture
def app():
    """Create Flask app for testing."""
    # Import after path is set
    from scripts.start_api_server import app as flask_app

    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def temp_state_dir():
    """Create temporary state directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        (state_dir / "jobs" / "tonight").mkdir(parents=True)
        (state_dir / "jobs" / "archive").mkdir(parents=True)
        (state_dir / "outputs").mkdir(parents=True)
        yield state_dir


def test_health_endpoint_healthy(client):
    """Test /health endpoint when systems are up."""
    with patch("scripts.start_api_server._get_status_flags", return_value=(True, True)):
        response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "healthy"
        assert data["llm"] == "up"
        assert data["memory"] == "up"
        assert "timestamp" in data


def test_health_endpoint_degraded(client):
    """Test /health endpoint when LLM is down."""
    with patch("scripts.start_api_server._get_status_flags", return_value=(False, True)):
        response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "degraded"
        assert data["llm"] == "down"
        assert data["memory"] == "up"


def test_queue_endpoint_empty(client, temp_state_dir):
    """Test /api/queue endpoint with no jobs."""
    with patch("scripts.start_api_server.STATE_DIR", temp_state_dir):
        response = client.get("/api/queue")

        assert response.status_code == 200
        data = response.get_json()

        assert data["queued"] == 0
        assert data["in_progress"] == 0
        assert data["queued_jobs"] == []
        assert data["in_progress_jobs"] == []
        assert "timestamp" in data


def test_queue_endpoint_with_jobs(client, temp_state_dir):
    """Test /api/queue endpoint with jobs."""
    # Create mock queued job
    tonight_dir = temp_state_dir / "jobs" / "tonight"
    job1 = {
        "id": "job-001",
        "type": "phone_request",
        "priority": "high",
        "status": "queued",
        "created_at": "2026-01-02T14:00:00Z"
    }
    with (tonight_dir / "job-001.json").open("w") as f:
        json.dump(job1, f)

    # Create mock in-progress job
    job2 = {
        "id": "job-002",
        "type": "cortex_analysis",
        "priority": "medium",
        "status": "in_progress",
        "created_at": "2026-01-02T14:05:00Z"
    }
    with (tonight_dir / "job-002.json").open("w") as f:
        json.dump(job2, f)

    with patch("scripts.start_api_server.STATE_DIR", temp_state_dir):
        response = client.get("/api/queue")

        assert response.status_code == 200
        data = response.get_json()

        assert data["queued"] == 1
        assert data["in_progress"] == 1
        assert len(data["queued_jobs"]) == 1
        assert data["queued_jobs"][0]["id"] == "job-001"
        assert len(data["in_progress_jobs"]) == 1
        assert data["in_progress_jobs"][0]["id"] == "job-002"


def test_reminders_endpoint_not_available(client):
    """Test /api/reminders endpoint when reminders module not available."""
    # The endpoint uses milton_orchestrator.reminders.ReminderStore
    # We need to patch it to simulate unavailability
    with patch('scripts.start_api_server.reminder_store') as mock_store:
        mock_store.list_reminders.side_effect = Exception("Reminders not available")
        
        response = client.get("/api/reminders")

        # Should return 500 error when backend fails
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data


def test_reminders_endpoint_with_limit(client, temp_state_dir):
    """Test /api/reminders endpoint with limit parameter."""
    import time
    import scripts.start_api_server as server_module
    from milton_orchestrator.reminders import ReminderStore

    # Create test reminder store
    test_store = ReminderStore(temp_state_dir / "reminders.sqlite3")
    original_store = server_module.reminder_store

    try:
        server_module.reminder_store = test_store

        # Create 3 reminders
        future_ts = int(time.time()) + 3600
        test_store.add_reminder("REMIND", future_ts, "Reminder 1")
        test_store.add_reminder("REMIND", future_ts + 100, "Reminder 2")
        test_store.add_reminder("REMIND", future_ts + 200, "Reminder 3")

        response = client.get("/api/reminders?limit=2")

        assert response.status_code == 200
        data = response.get_json()

        assert data["count"] == 2
        assert len(data["reminders"]) == 2
    finally:
        server_module.reminder_store = original_store
        test_store.close()


def test_outputs_endpoint_empty(client, temp_state_dir):
    """Test /api/outputs endpoint with no outputs."""
    with patch("scripts.start_api_server.STATE_DIR", temp_state_dir):
        response = client.get("/api/outputs")

        assert response.status_code == 200
        data = response.get_json()

        assert data["outputs"] == []
        assert data["count"] == 0
        assert data["total"] == 0


def test_outputs_endpoint_with_files(client, temp_state_dir):
    """Test /api/outputs endpoint with output files."""
    outputs_dir = temp_state_dir / "outputs"

    # Create mock output files
    (outputs_dir / "brief_20260102.txt").write_text("Morning briefing content")
    (outputs_dir / "analysis_report.md").write_text("# Analysis Report\n\nContent here")
    (outputs_dir / "data_export.json").write_text('{"key": "value"}')

    with patch("scripts.start_api_server.STATE_DIR", temp_state_dir):
        response = client.get("/api/outputs")

        assert response.status_code == 200
        data = response.get_json()

        assert data["count"] == 3
        assert data["total"] == 3
        assert len(data["outputs"]) == 3

        # Check output structure
        output = data["outputs"][0]
        assert "name" in output
        assert "path" in output
        assert "size_bytes" in output
        assert "size_kb" in output
        assert "modified_at" in output
        assert "created_at" in output


def test_outputs_endpoint_with_limit(client, temp_state_dir):
    """Test /api/outputs endpoint respects limit parameter."""
    outputs_dir = temp_state_dir / "outputs"

    # Create 5 files
    for i in range(5):
        (outputs_dir / f"output_{i}.txt").write_text(f"Content {i}")

    with patch("scripts.start_api_server.STATE_DIR", temp_state_dir):
        response = client.get("/api/outputs?limit=3")

        assert response.status_code == 200
        data = response.get_json()

        # count is number of files returned (limited)
        # total is total number of files
        assert data["count"] == 3  # Limited to 3
        assert data["total"] == 5  # Total files created
        assert len(data["outputs"]) == 3


def test_memory_search_missing_query(client):
    """Test /api/memory/search endpoint without query parameter."""
    response = client.get("/api/memory/search")

    assert response.status_code == 400
    data = response.get_json()

    assert "error" in data
    assert "query" in data["error"].lower()


def test_memory_search_with_results(client):
    """Test /api/memory/search endpoint with mock results."""
    mock_results = [
        {
            "id": "vec-001",
            "content": "Test memory content 1",
            "context": "Test context 1",
            "agent": "nexus",
            "timestamp": "2026-01-02T14:00:00Z",
            "distance": 0.12
        },
        {
            "id": "vec-002",
            "content": "Test memory content 2",
            "context": "Test context 2",
            "agent": "cortex",
            "timestamp": "2026-01-02T14:05:00Z",
            "distance": 0.18
        }
    ]

    with patch("scripts.start_api_server._ensure_schema", return_value=True):
        with patch("memory.retrieve.query_relevant", return_value=mock_results):
            response = client.get("/api/memory/search?query=test&top_k=2")

            assert response.status_code == 200
            data = response.get_json()

            assert data["query"] == "test"
            assert data["count"] == 2
            assert len(data["results"]) == 2
            assert data["results"][0]["id"] == "vec-001"
            assert data["results"][0]["content"] == "Test memory content 1"


def test_memory_search_schema_not_ready(client):
    """Test /api/memory/search endpoint when schema not ready."""
    with patch("scripts.start_api_server._ensure_schema", return_value=False):
        response = client.get("/api/memory/search?query=test")

        assert response.status_code == 503
        data = response.get_json()

        assert "error" in data
        assert "not available" in data["error"].lower()


def test_memory_search_respects_top_k(client):
    """Test /api/memory/search endpoint respects top_k parameter."""
    mock_results = [{"id": f"vec-{i:03d}", "content": f"Content {i}"} for i in range(10)]

    with patch("scripts.start_api_server._ensure_schema", return_value=True):
        with patch("memory.retrieve.query_relevant", return_value=mock_results) as mock_query:
            response = client.get("/api/memory/search?query=test&top_k=5")

            assert response.status_code == 200
            data = response.get_json()

            # Verify top_k was passed to query_relevant
            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[0][0] == "test"  # query
            assert call_args[1]["top_k"] == 5  # top_k


def test_memory_search_max_top_k(client):
    """Test /api/memory/search endpoint enforces max top_k."""
    mock_results = []

    with patch("scripts.start_api_server._ensure_schema", return_value=True):
        with patch("memory.retrieve.query_relevant", return_value=mock_results) as mock_query:
            # Request 100 but max is 50
            response = client.get("/api/memory/search?query=test&top_k=100")

            assert response.status_code == 200

            # Verify top_k was capped at 50
            call_args = mock_query.call_args
            assert call_args[1]["top_k"] == 50


def test_existing_endpoints_still_work(client):
    """Test that existing endpoints still work after changes."""
    # Test /api/system-state
    with patch("scripts.start_api_server._get_status_flags", return_value=(True, True)):
        with patch("scripts.start_api_server._get_memory_snapshot", return_value=(1200, 8.3)):
            response = client.get("/api/system-state")

            assert response.status_code == 200
            data = response.get_json()

            assert "nexus" in data
            assert "cortex" in data
            assert "frontier" in data
            assert "memory" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
