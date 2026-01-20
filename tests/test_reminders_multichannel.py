"""Tests for multi-channel reminder enhancements."""

from datetime import datetime
from unittest.mock import Mock, patch
import pytest
import json

from milton_orchestrator.reminders import (
    Reminder,
    ReminderStore,
    ReminderScheduler,
    _parse_channels,
    _serialize_channels,
    DEFAULT_ACTIONS,
)
from milton_orchestrator.notifications import DeliveryResult, NotificationRouter


def test_parse_channels_json_list():
    """Test parsing JSON list channels."""
    assert _parse_channels('["ntfy","voice"]') == ["ntfy", "voice"]
    assert _parse_channels('["ntfy"]') == ["ntfy"]


def test_parse_channels_legacy_single_string():
    """Test parsing legacy single string channel."""
    assert _parse_channels("ntfy") == ["ntfy"]
    assert _parse_channels("voice") == ["voice"]


def test_parse_channels_legacy_both():
    """Test parsing legacy 'both' channel."""
    assert _parse_channels("both") == ["ntfy", "voice"]
    assert _parse_channels('["both"]') == ["ntfy", "voice"]


def test_parse_channels_empty():
    """Test parsing empty/None channels defaults to ntfy."""
    assert _parse_channels(None) == ["ntfy"]
    assert _parse_channels("") == ["ntfy"]
    assert _parse_channels("[]") == ["ntfy"]


def test_parse_channels_deduplication():
    """Test channel list deduplication."""
    assert _parse_channels('["ntfy","ntfy","voice"]') == ["ntfy", "voice"]
    assert _parse_channels('["both","ntfy"]') == ["ntfy", "voice"]


def test_serialize_channels():
    """Test channel list serialization."""
    assert _serialize_channels(["ntfy", "voice"]) == '["ntfy", "voice"]'
    assert _serialize_channels(["ntfy"]) == '["ntfy"]'
    assert _serialize_channels([]) == '["ntfy"]'  # Default


def test_serialize_channels_with_both():
    """Test that 'both' is expanded during serialization."""
    result = _serialize_channels(["both"])
    parsed = json.loads(result)
    assert "ntfy" in parsed
    assert "voice" in parsed
    assert "both" not in parsed


def test_reminder_channels_property():
    """Test Reminder.channels property."""
    # JSON list
    r1 = Reminder(
        id=1,
        kind="REMIND",
        message="Test",
        due_at=1704067200,
        created_at=1704060000,
        sent_at=None,
        canceled_at=None,
        channel='["ntfy","voice"]',
    )
    assert r1.channels == ["ntfy", "voice"]
    
    # Legacy single string (after migration would be JSON)
    r2 = Reminder(
        id=2,
        kind="REMIND",
        message="Test",
        due_at=1704067200,
        created_at=1704060000,
        sent_at=None,
        canceled_at=None,
        channel="ntfy",  # Will be parsed
    )
    assert r2.channels == ["ntfy"]


def test_store_add_reminder_with_channels_list(tmp_path):
    """Test adding reminder with new channels parameter (list)."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Multi-channel test",
        channels=["ntfy", "voice"],  # New list parameter
    )
    
    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.channels == ["ntfy", "voice"]
    
    store.close()


def test_store_add_reminder_with_legacy_channel(tmp_path):
    """Test adding reminder with legacy channel parameter (string)."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Legacy channel test",
        channel="ntfy",  # Legacy string parameter
    )
    
    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.channels == ["ntfy"]
    
    store.close()


def test_store_add_reminder_with_both(tmp_path):
    """Test adding reminder with legacy 'both' channel."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Both channels test",
        channel="both",
    )
    
    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    channels = reminder.channels
    assert "ntfy" in channels
    assert "voice" in channels
    
    store.close()


def test_store_channel_migration(tmp_path):
    """Test that old single-string channels are migrated to JSON lists."""
    import sqlite3
    
    db_path = tmp_path / "reminders.db"
    
    # Create DB with old schema
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY,
            kind TEXT,
            message TEXT,
            due_at INTEGER,
            created_at INTEGER,
            sent_at INTEGER,
            canceled_at INTEGER,
            timezone TEXT DEFAULT 'America/New_York',
            delivery_target TEXT,
            last_error TEXT,
            channel TEXT DEFAULT 'ntfy',
            priority TEXT DEFAULT 'med',
            status TEXT DEFAULT 'scheduled',
            actions TEXT DEFAULT '[]',
            source TEXT DEFAULT 'other',
            updated_at INTEGER,
            audit_log TEXT DEFAULT '[]',
            context_ref TEXT
        )
    """)
    
    # Insert old-format reminder
    conn.execute("""
        INSERT INTO reminders (kind, message, due_at, created_at, channel, updated_at)
        VALUES ('REMIND', 'Old reminder', 1704067200, 1704060000, 'ntfy', 1704060000)
    """)
    conn.commit()
    conn.close()
    
    # Now open with ReminderStore (triggers migration)
    store = ReminderStore(db_path)
    
    # Verify migration converted channel to JSON list
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT channel FROM reminders WHERE id = 1").fetchone()
    channel_val = row["channel"]
    conn.close()
    
    # Should be JSON now
    parsed = json.loads(channel_val)
    assert isinstance(parsed, list)
    assert "ntfy" in parsed
    
    store.close()


def test_scheduler_with_notification_router(tmp_path):
    """Test scheduler delivers through notification router."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    # Create reminder with multiple channels
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts - 1,  # Due now
        message="Multi-channel scheduler test",
        channels=["ntfy", "voice"],
    )
    
    # Mock router
    mock_router = Mock(spec=NotificationRouter)
    mock_router.send_all.return_value = [
        DeliveryResult(ok=True, provider="ntfy", message_id="msg1"),
        DeliveryResult(ok=False, provider="voice", error="not implemented"),
    ]
    
    # Create scheduler with router
    scheduler = ReminderScheduler(
        store=store,
        notification_router=mock_router,
        now_fn=lambda: now_ts,
    )
    
    # Run once
    scheduler.run_once()
    
    # Verify router was called
    mock_router.send_all.assert_called_once()
    call_args = mock_router.send_all.call_args
    
    # Check reminder argument
    reminder_arg = call_args[0][0]
    assert reminder_arg.id == reminder_id
    
    # Check channels argument
    channels_arg = call_args[0][1]
    assert "ntfy" in channels_arg
    assert "voice" in channels_arg
    
    # Verify reminder was marked as sent
    reminder = store.get_reminder(reminder_id)
    assert reminder.sent_at is not None
    assert reminder.status == "fired"
    
    # Verify audit log contains delivery attempts
    assert len(reminder.audit_log) > 0
    delivery_entries = [e for e in reminder.audit_log if e.get("action") == "delivery_attempt"]
    assert len(delivery_entries) == 2  # One for each channel
    
    store.close()


def test_scheduler_with_legacy_publish_fn(tmp_path):
    """Test scheduler works with legacy publish_fn (backward compatibility)."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts - 1,
        message="Legacy test",
    )
    
    sent_messages = []
    
    def publish_fn(message, title, rid):
        sent_messages.append((message, title, rid))
        return True
    
    scheduler = ReminderScheduler(
        store=store,
        publish_fn=publish_fn,
        now_fn=lambda: now_ts,
    )
    
    scheduler.run_once()
    
    assert len(sent_messages) == 1
    assert sent_messages[0][2] == reminder_id
    
    store.close()


def test_append_audit_log(tmp_path):
    """Test appending audit log entries."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Audit log test",
    )
    
    # Append some entries
    entries = [
        {"ts": now_ts, "action": "test1", "actor": "test", "details": "First"},
        {"ts": now_ts + 1, "action": "test2", "actor": "test", "details": "Second"},
    ]
    
    success = store.append_audit_log(reminder_id, entries)
    assert success is True
    
    # Verify entries were added
    reminder = store.get_reminder(reminder_id)
    assert len(reminder.audit_log) >= 2  # At least our 2 entries (plus creation entry)
    
    # Check our entries are present
    test_entries = [e for e in reminder.audit_log if e.get("action") in ("test1", "test2")]
    assert len(test_entries) == 2
    
    store.close()


def test_append_audit_log_bounds(tmp_path):
    """Test audit log is bounded to prevent unbounded growth."""
    store = ReminderStore(tmp_path / "reminders.db")
    now_ts = int(datetime.now().timestamp())
    
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Bounded audit log test",
    )
    
    # Add 150 entries (should be truncated to 100)
    for i in range(150):
        store.append_audit_log(reminder_id, [{
            "ts": now_ts + i,
            "action": f"entry_{i}",
            "actor": "test",
            "details": f"Entry {i}",
        }])
    
    reminder = store.get_reminder(reminder_id)
    assert len(reminder.audit_log) <= 101  # 100 + creation entry
    
    store.close()
