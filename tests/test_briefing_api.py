"""Tests for briefing items and reminders API endpoints.

Tests cover:
1. BriefingStore CRUD operations
2. Flask API endpoints for briefing items
3. Flask API endpoints for reminders
4. Persistence verification across store re-instantiation
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path for imports
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from storage.briefing_store import BriefingStore, BriefingItem
from milton_orchestrator.reminders import ReminderStore


# ==============================================================================
# BriefingStore Unit Tests
# ==============================================================================

class TestBriefingStore:
    """Tests for BriefingStore SQLite persistence."""

    def test_create_item_and_verify_fields(self, tmp_path):
        """Test that created items have correct fields."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        item_id = store.add_item(
            content="Review AI resources",
            priority=1,
            source="test",
            due_at="2026-01-13T09:00:00Z",
        )

        item = store.get_item(item_id)
        assert item is not None
        assert item.id == item_id
        assert item.content == "Review AI resources"
        assert item.priority == 1
        assert item.source == "test"
        assert item.status == "active"
        assert item.due_at == "2026-01-13T09:00:00Z"
        assert item.created_at is not None
        assert item.completed_at is None
        assert item.dismissed_at is None

        store.close()

    def test_list_items_filters_by_status(self, tmp_path):
        """Test that list_items correctly filters by status."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        id1 = store.add_item(content="Item 1", priority=0)
        id2 = store.add_item(content="Item 2", priority=0)
        id3 = store.add_item(content="Item 3", priority=0)

        # Mark one done, one dismissed
        store.mark_done(id2)
        store.mark_dismissed(id3)

        # Test active filter
        active_items = store.list_items(status="active")
        assert len(active_items) == 1
        assert active_items[0].id == id1

        # Test done filter
        done_items = store.list_items(status="done")
        assert len(done_items) == 1
        assert done_items[0].id == id2

        # Test dismissed filter
        dismissed_items = store.list_items(status="dismissed")
        assert len(dismissed_items) == 1
        assert dismissed_items[0].id == id3

        # Test no filter (all items)
        all_items = store.list_items()
        assert len(all_items) == 3

        store.close()

    def test_list_items_excludes_expired_by_default(self, tmp_path):
        """Test that expired items are excluded by default."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        # Create item that expires in the past
        past_time = "2020-01-01T00:00:00Z"
        future_time = "2030-01-01T00:00:00Z"

        id_expired = store.add_item(content="Expired", expires_at=past_time)
        id_valid = store.add_item(content="Valid", expires_at=future_time)
        id_no_expiry = store.add_item(content="No expiry")

        # Default should exclude expired
        items = store.list_items(status="active")
        item_ids = [item.id for item in items]
        assert id_expired not in item_ids
        assert id_valid in item_ids
        assert id_no_expiry in item_ids

        # With include_expired=True
        items = store.list_items(status="active", include_expired=True)
        item_ids = [item.id for item in items]
        assert id_expired in item_ids

        store.close()

    def test_mark_done_transitions_status(self, tmp_path):
        """Test mark_done correctly updates status."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        item_id = store.add_item(content="Test item")

        # Verify initially active
        item = store.get_item(item_id)
        assert item.status == "active"

        # Mark done
        success = store.mark_done(item_id)
        assert success is True

        # Verify status changed
        item = store.get_item(item_id)
        assert item.status == "done"
        assert item.completed_at is not None

        # Trying to mark done again should fail
        success = store.mark_done(item_id)
        assert success is False

        store.close()

    def test_mark_dismissed_transitions_status(self, tmp_path):
        """Test mark_dismissed correctly updates status."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        item_id = store.add_item(content="Test item")

        # Mark dismissed
        success = store.mark_dismissed(item_id)
        assert success is True

        # Verify status changed
        item = store.get_item(item_id)
        assert item.status == "dismissed"
        assert item.dismissed_at is not None

        # Trying to dismiss again should fail
        success = store.mark_dismissed(item_id)
        assert success is False

        store.close()

    def test_persistence_across_reopen(self, tmp_path):
        """Test data persists when store is reopened."""
        db_path = tmp_path / "briefing.sqlite3"

        # Create and close store
        store1 = BriefingStore(db_path)
        item_id = store1.add_item(content="Persistent item", priority=5)
        store1.close()

        # Reopen and verify data
        store2 = BriefingStore(db_path)
        item = store2.get_item(item_id)
        assert item is not None
        assert item.content == "Persistent item"
        assert item.priority == 5
        store2.close()

    def test_content_cannot_be_empty(self, tmp_path):
        """Test that empty content raises ValueError."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        with pytest.raises(ValueError, match="Content cannot be empty"):
            store.add_item(content="")

        with pytest.raises(ValueError, match="Content cannot be empty"):
            store.add_item(content="   ")

        store.close()

    def test_items_ordered_by_priority_desc(self, tmp_path):
        """Test that items are returned ordered by priority (highest first)."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")

        store.add_item(content="Low", priority=0)
        store.add_item(content="High", priority=10)
        store.add_item(content="Medium", priority=5)

        items = store.list_items()
        assert len(items) == 3
        assert items[0].content == "High"
        assert items[1].content == "Medium"
        assert items[2].content == "Low"

        store.close()


# ==============================================================================
# Flask API Tests
# ==============================================================================

@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a test client with isolated database."""
    # Set STATE_DIR to temp directory before importing app
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("MILTON_STATE_DIR", str(tmp_path))

    # Import app after setting env vars
    import scripts.start_api_server as server_module

    # Create new stores in temp directory
    test_briefing_store = BriefingStore(tmp_path / "briefing.sqlite3")
    test_reminder_store = ReminderStore(tmp_path / "reminders.sqlite3")

    # Save original stores
    original_briefing_store = server_module.briefing_store
    original_reminder_store = server_module.reminder_store

    # Replace with test stores
    server_module.briefing_store = test_briefing_store
    server_module.reminder_store = test_reminder_store

    app = server_module.app
    app.config["TESTING"] = True

    try:
        with app.test_client() as client:
            yield client, test_briefing_store, test_reminder_store
    finally:
        # Restore original stores
        server_module.briefing_store = original_briefing_store
        server_module.reminder_store = original_reminder_store
        test_briefing_store.close()
        test_reminder_store.close()


class TestBriefingItemsAPI:
    """Tests for /api/briefing/items endpoints."""

    def test_create_item_success(self, app_client):
        """Test POST /api/briefing/items creates item."""
        client, store, _ = app_client

        response = client.post(
            "/api/briefing/items",
            data=json.dumps({"content": "Test item", "priority": 1, "source": "test"}),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "id" in data
        assert data["status"] == "active"
        assert "created_at" in data

        # Verify in store
        item = store.get_item(data["id"])
        assert item.content == "Test item"
        assert item.priority == 1

    def test_create_item_missing_content(self, app_client):
        """Test POST /api/briefing/items fails without content."""
        client, _, _ = app_client

        response = client.post(
            "/api/briefing/items",
            data=json.dumps({"priority": 1}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "content" in data["error"].lower()

    def test_create_item_with_dates(self, app_client):
        """Test POST /api/briefing/items with due_at and expires_at."""
        client, store, _ = app_client

        response = client.post(
            "/api/briefing/items",
            data=json.dumps({
                "content": "Dated item",
                "due_at": "2026-01-15T09:00:00Z",
                "expires_at": "2026-01-16T00:00:00Z",
            }),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()

        item = store.get_item(data["id"])
        assert item.due_at == "2026-01-15T09:00:00Z"
        assert item.expires_at == "2026-01-16T00:00:00Z"

    def test_list_items(self, app_client):
        """Test GET /api/briefing/items returns items."""
        client, store, _ = app_client

        # Create some items
        store.add_item(content="Item 1")
        store.add_item(content="Item 2")

        response = client.get("/api/briefing/items")

        assert response.status_code == 200
        data = response.get_json()
        assert "items" in data
        assert "count" in data
        assert data["count"] == 2

    def test_list_items_filter_by_status(self, app_client):
        """Test GET /api/briefing/items?status= filters correctly."""
        client, store, _ = app_client

        id1 = store.add_item(content="Active")
        id2 = store.add_item(content="Done")
        store.mark_done(id2)

        # Filter active
        response = client.get("/api/briefing/items?status=active")
        data = response.get_json()
        assert data["count"] == 1
        assert data["items"][0]["content"] == "Active"

        # Filter done
        response = client.get("/api/briefing/items?status=done")
        data = response.get_json()
        assert data["count"] == 1
        assert data["items"][0]["content"] == "Done"

    def test_list_items_invalid_status(self, app_client):
        """Test GET /api/briefing/items with invalid status returns 400."""
        client, _, _ = app_client

        response = client.get("/api/briefing/items?status=invalid")

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_mark_item_done(self, app_client):
        """Test POST /api/briefing/items/{id}/done marks item done."""
        client, store, _ = app_client

        item_id = store.add_item(content="To complete")

        response = client.post(f"/api/briefing/items/{item_id}/done")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == item_id
        assert data["status"] == "done"
        assert "completed_at" in data

        # Verify in store
        item = store.get_item(item_id)
        assert item.status == "done"

    def test_mark_item_done_not_found(self, app_client):
        """Test POST /api/briefing/items/{id}/done returns 404 for missing item."""
        client, _, _ = app_client

        response = client.post("/api/briefing/items/99999/done")

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    def test_dismiss_item(self, app_client):
        """Test POST /api/briefing/items/{id}/dismiss dismisses item."""
        client, store, _ = app_client

        item_id = store.add_item(content="To dismiss")

        response = client.post(f"/api/briefing/items/{item_id}/dismiss")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == item_id
        assert data["status"] == "dismissed"
        assert "dismissed_at" in data


class TestRemindersAPI:
    """Tests for /api/reminders endpoints."""

    def test_create_reminder_success(self, app_client):
        """Test POST /api/reminders creates reminder."""
        client, _, reminder_store = app_client

        future_ts = int(time.time()) + 3600  # 1 hour from now

        response = client.post(
            "/api/reminders",
            data=json.dumps({
                "message": "Test reminder",
                "remind_at": future_ts,
            }),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "id" in data
        assert data["status"] == "scheduled"
        assert data["message"] == "Test reminder"
        assert data["remind_at"] == future_ts

    def test_create_reminder_with_iso8601(self, app_client):
        """Test POST /api/reminders with ISO8601 timestamp."""
        client, _, _ = app_client

        response = client.post(
            "/api/reminders",
            data=json.dumps({
                "message": "ISO reminder",
                "remind_at": "2026-01-15T10:00:00Z",
            }),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "scheduled"

    def test_create_reminder_missing_message(self, app_client):
        """Test POST /api/reminders fails without message."""
        client, _, _ = app_client

        response = client.post(
            "/api/reminders",
            data=json.dumps({"remind_at": int(time.time()) + 3600}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "message" in data["error"].lower()

    def test_create_reminder_missing_remind_at(self, app_client):
        """Test POST /api/reminders fails without remind_at."""
        client, _, _ = app_client

        response = client.post(
            "/api/reminders",
            data=json.dumps({"message": "No time"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "remind_at" in data["error"].lower()

    def test_list_reminders(self, app_client):
        """Test GET /api/reminders returns reminders."""
        client, _, _ = app_client

        future_ts = int(time.time()) + 3600

        # Create reminders via API
        resp1 = client.post(
            "/api/reminders",
            data=json.dumps({"message": "Reminder 1", "remind_at": future_ts}),
            content_type="application/json",
        )
        resp2 = client.post(
            "/api/reminders",
            data=json.dumps({"message": "Reminder 2", "remind_at": future_ts}),
            content_type="application/json",
        )

        # Verify creation succeeded
        assert resp1.status_code == 201, f"Create 1 failed: {resp1.get_json()}"
        assert resp2.status_code == 201, f"Create 2 failed: {resp2.get_json()}"

        response = client.get("/api/reminders")

        assert response.status_code == 200
        data = response.get_json()
        assert "reminders" in data
        # Debug: print what we got
        assert data["count"] == 2, f"Expected 2 reminders, got {data['count']}: {data}"

    def test_list_reminders_filter_status(self, app_client):
        """Test GET /api/reminders?status= filters correctly."""
        client, _, _ = app_client

        future_ts = int(time.time()) + 3600

        # Create reminders via API
        resp1 = client.post(
            "/api/reminders",
            data=json.dumps({"message": "Scheduled", "remind_at": future_ts}),
            content_type="application/json",
        )
        resp2 = client.post(
            "/api/reminders",
            data=json.dumps({"message": "Canceled", "remind_at": future_ts}),
            content_type="application/json",
        )

        id2 = resp2.get_json()["id"]

        # Cancel the second one via API
        client.post(f"/api/reminders/{id2}/cancel")

        # Filter scheduled
        response = client.get("/api/reminders?status=scheduled")
        data = response.get_json()
        assert data["count"] == 1
        assert data["reminders"][0]["message"] == "Scheduled"

        # Filter canceled
        response = client.get("/api/reminders?status=canceled")
        data = response.get_json()
        assert data["count"] == 1
        assert data["reminders"][0]["message"] == "Canceled"

    def test_cancel_reminder(self, app_client):
        """Test POST /api/reminders/{id}/cancel cancels reminder."""
        client, _, reminder_store = app_client

        future_ts = int(time.time()) + 3600
        reminder_id = reminder_store.add_reminder("REMIND", future_ts, "To cancel")

        response = client.post(f"/api/reminders/{reminder_id}/cancel")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == reminder_id
        assert data["status"] == "canceled"
        assert "canceled_at" in data

    def test_cancel_reminder_not_found(self, app_client):
        """Test POST /api/reminders/{id}/cancel returns 404 for missing reminder."""
        client, _, _ = app_client

        response = client.post("/api/reminders/99999/cancel")

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data


# ==============================================================================
# Integration / Persistence Tests
# ==============================================================================

class TestPersistence:
    """Tests verifying data persists across operations."""

    def test_briefing_item_survives_store_reopen(self, tmp_path):
        """Test briefing item data survives closing and reopening store."""
        db_path = tmp_path / "test_briefing.sqlite3"

        # Create item
        store1 = BriefingStore(db_path)
        item_id = store1.add_item(
            content="Persistent content",
            priority=7,
            source="persistence_test",
            due_at="2026-02-01T00:00:00Z",
        )
        store1.mark_done(item_id)
        store1.close()

        # Reopen and verify
        store2 = BriefingStore(db_path)
        item = store2.get_item(item_id)

        assert item is not None
        assert item.content == "Persistent content"
        assert item.priority == 7
        assert item.source == "persistence_test"
        assert item.status == "done"
        assert item.completed_at is not None

        store2.close()

    def test_reminder_survives_store_reopen(self, tmp_path):
        """Test reminder data survives closing and reopening store."""
        db_path = tmp_path / "test_reminders.sqlite3"

        # Create reminder
        store1 = ReminderStore(db_path)
        future_ts = int(time.time()) + 3600
        reminder_id = store1.add_reminder("REMIND", future_ts, "Persistent reminder")
        store1.close()

        # Reopen and verify
        store2 = ReminderStore(db_path)
        reminder = store2.get_reminder(reminder_id)

        assert reminder is not None
        assert reminder.message == "Persistent reminder"
        assert reminder.due_at == future_ts

        store2.close()
