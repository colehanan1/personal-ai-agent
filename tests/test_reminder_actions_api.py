"""Tests for reminder action callback API."""

from datetime import datetime
import pytest
from unittest.mock import patch, Mock
import json

from milton_orchestrator.reminders import ReminderStore


@pytest.fixture
def reminder_store(tmp_path):
    """Create a temporary reminder store for testing."""
    return ReminderStore(tmp_path / "test_reminders.db")


@pytest.fixture
def app_client(reminder_store, tmp_path, monkeypatch):
    """Create Flask test client with mocked reminder store."""
    import sys
    from pathlib import Path
    
    # Add scripts dir to path
    root_dir = Path(__file__).parent.parent
    scripts_dir = root_dir / "scripts"
    sys.path.insert(0, str(scripts_dir))
    
    # Mock the reminder store before import
    monkeypatch.setenv("MILTON_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("NTFY_BASE_URL", "https://ntfy.sh")
    monkeypatch.setenv("ANSWER_TOPIC", "test-topic")
    
    # Import after env setup
    from start_api_server import app as flask_app, reminder_store as api_store
    
    # Replace the store in the module
    import start_api_server
    start_api_server.reminder_store = reminder_store
    
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_reminder_action_done(app_client, reminder_store):
    """Test DONE action on reminder."""
    now_ts = int(datetime.now().timestamp())
    
    # Create a reminder
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Test reminder",
    )
    
    # Send DONE action
    with patch("start_api_server.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200)
        
        response = app_client.post(
            f"/api/reminders/{reminder_id}/action",
            json={"action": "DONE"},
        )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["id"] == reminder_id
    assert data["action"] == "DONE"
    assert data["status"] == "acknowledged"
    assert data["due_at"] is None  # DONE doesn't reschedule
    
    # Verify reminder status
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder.status == "acknowledged"
    
    # Verify audit log
    action_entries = [e for e in reminder.audit_log if e.get("action") == "action_callback"]
    assert len(action_entries) > 0


def test_reminder_action_snooze_30(app_client, reminder_store):
    """Test SNOOZE_30 action on reminder."""
    now_ts = int(datetime.now().timestamp())
    original_due = now_ts + 3600
    
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=original_due,
        message="Test reminder",
    )
    
    with patch("start_api_server.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200)
        
        response = app_client.post(
            f"/api/reminders/{reminder_id}/action",
            json={"action": "SNOOZE_30"},
        )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["action"] == "SNOOZE_30"
    assert data["status"] == "snoozed"
    assert data["due_at"] is not None
    
    # Verify reminder was snoozed
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder.status == "snoozed"
    assert reminder.sent_at is None  # Reset for re-firing
    # Due time should be approximately 30 minutes from now
    assert abs(reminder.due_at - (now_ts + 30 * 60)) < 60  # Within 1 minute tolerance


def test_reminder_action_delay_2h(app_client, reminder_store):
    """Test DELAY_2H action on reminder."""
    now_ts = int(datetime.now().timestamp())
    original_due = now_ts + 3600
    
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=original_due,
        message="Test reminder",
    )
    
    with patch("start_api_server.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200)
        
        response = app_client.post(
            f"/api/reminders/{reminder_id}/action",
            json={"action": "DELAY_2H"},
        )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["action"] == "DELAY_2H"
    assert data["status"] == "snoozed"
    
    # Verify delay
    reminder = reminder_store.get_reminder(reminder_id)
    assert abs(reminder.due_at - (now_ts + 120 * 60)) < 60


def test_reminder_action_invalid_action(app_client, reminder_store):
    """Test invalid action is rejected."""
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=int(datetime.now().timestamp()) + 3600,
        message="Test",
    )
    
    response = app_client.post(
        f"/api/reminders/{reminder_id}/action",
        json={"action": "INVALID_ACTION"},
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "Invalid action" in data["error"]


def test_reminder_action_not_found(app_client, reminder_store):
    """Test action on non-existent reminder."""
    response = app_client.post(
        "/api/reminders/99999/action",
        json={"action": "DONE"},
    )
    
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert "not found" in data["error"].lower()


def test_reminder_action_missing_action(app_client, reminder_store):
    """Test request with missing action field."""
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=int(datetime.now().timestamp()) + 3600,
        message="Test",
    )
    
    response = app_client.post(
        f"/api/reminders/{reminder_id}/action",
        json={},
    )
    
    assert response.status_code == 400


def test_reminder_action_with_token_auth(app_client, reminder_store, monkeypatch):
    """Test action endpoint with token authentication."""
    monkeypatch.setenv("MILTON_ACTION_TOKEN", "secret123")
    
    # Need to reload module to pick up env var
    import sys
    import importlib
    import start_api_server
    importlib.reload(start_api_server)
    start_api_server.reminder_store = reminder_store
    start_api_server.MILTON_ACTION_TOKEN = "secret123"
    
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=int(datetime.now().timestamp()) + 3600,
        message="Test",
    )
    
    # Valid token should work
    with patch("start_api_server.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200)
        
        response = app_client.post(
            f"/api/reminders/{reminder_id}/action",
            json={"action": "DONE", "token": "secret123"},
        )
    
    assert response.status_code == 200
    
    # Invalid token should fail
    response = app_client.post(
        f"/api/reminders/{reminder_id}/action",
        json={"action": "DONE", "token": "wrong_token"},
    )
    
    assert response.status_code == 401
    
    # Missing token should fail
    response = app_client.post(
        f"/api/reminders/{reminder_id}/action",
        json={"action": "DONE"},
    )
    
    assert response.status_code == 401


def test_reminder_health_endpoint(app_client, reminder_store):
    """Test reminder health check endpoint."""
    response = app_client.get("/api/reminders/health")
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert "status" in data
    assert "scheduler" in data
    assert "reminders" in data
    assert "delivery" in data
    assert "timestamp" in data
    
    assert "last_heartbeat" in data["scheduler"]
    assert "is_alive" in data["scheduler"]
    assert "scheduled_count" in data["reminders"]


def test_reminder_health_degraded_status(app_client, reminder_store):
    """Test health endpoint shows degraded when scheduler not running."""
    # Don't start scheduler, so heartbeat will be None
    response = app_client.get("/api/reminders/health")
    
    assert response.status_code == 200
    data = response.get_json()
    
    # Should be degraded without recent heartbeat
    assert data["status"] == "degraded"
    assert data["scheduler"]["is_alive"] is False
