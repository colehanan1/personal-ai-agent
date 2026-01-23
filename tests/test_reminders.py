"""Tests for reminder parsing and scheduling."""

from datetime import datetime, timedelta
from unittest.mock import patch, Mock

import pytest

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

from milton_orchestrator.reminders import (
    Reminder,
    ReminderScheduler,
    ReminderStore,
    parse_reminder_command,
    parse_time_expression,
    format_timestamp_local,
    deliver_ntfy,
    DATEPARSER_AVAILABLE,
    REMINDER_CHANNELS,
    REMINDER_PRIORITIES,
    REMINDER_STATUSES,
    REMINDER_ACTIONS,
    REMINDER_SOURCES,
    DEFAULT_ACTIONS,
    _LEGACY_SOURCE_MAP,
)


def test_parse_in_minutes():
    now = datetime(2025, 1, 1, 10, 0)
    due_ts = parse_time_expression("in 10m", now=now)
    expected = int((now + timedelta(minutes=10)).timestamp())
    assert due_ts == expected


def test_parse_at_time_rollover():
    now = datetime(2025, 1, 1, 23, 50)
    due_ts = parse_time_expression("at 23:40", now=now)
    due_dt = datetime.fromtimestamp(due_ts)
    assert due_dt.date() == (now + timedelta(days=1)).date()


def test_parse_absolute_datetime():
    due_ts = parse_time_expression("2025-01-02 07:30", now=datetime(2025, 1, 1, 10, 0))
    due_dt = datetime.fromtimestamp(due_ts)
    assert due_dt.strftime("%Y-%m-%d %H:%M") == "2025-01-02 07:30"


def test_parse_reminder_command_schedule():
    now = datetime(2025, 1, 1, 9, 0)
    command = parse_reminder_command("in 30m | Stretch", kind="REMIND", now=now)
    assert command.action == "schedule"
    assert command.message == "Stretch"


def test_parse_reminder_command_list_and_cancel():
    command = parse_reminder_command("list", kind="REMIND")
    assert command.action == "list"

    command = parse_reminder_command("cancel 42", kind="REMIND")
    assert command.action == "cancel"
    assert command.reminder_id == 42


def test_store_list_cancel(tmp_path):
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    reminder_id = store.add_reminder("REMIND", int(datetime.now().timestamp()) + 60, "Test")
    reminders = store.list_reminders()
    assert len(reminders) == 1
    assert reminders[0].id == reminder_id

    canceled = store.cancel_reminder(reminder_id)
    assert canceled is True
    reminders = store.list_reminders()
    assert reminders == []
    store.close()


def test_scheduler_sends_due_reminders(tmp_path):
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    reminder_id = store.add_reminder("REMIND", now_ts - 1, "Ping")
    sent_messages = []

    def publish_fn(message: str, title: str, reminder_id: int) -> bool:
        sent_messages.append((message, title, reminder_id))
        return True

    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)
    scheduler.run_once()

    assert sent_messages
    reminders = store.list_reminders(include_sent=True)
    assert reminders[0].id == reminder_id
    assert reminders[0].sent_at is not None
    store.close()


def test_parse_time_expression_with_hours():
    now = datetime(2025, 1, 1, 10, 0)
    due_ts = parse_time_expression("in 2 hours", now=now)
    expected = int((now + timedelta(hours=2)).timestamp())
    assert due_ts == expected


def test_parse_time_expression_with_minutes_variants():
    now = datetime(2025, 1, 1, 10, 0)

    # Test different minute formats
    for expr in ["in 30m", "in 30 min", "in 30 mins", "in 30 minutes"]:
        due_ts = parse_time_expression(expr, now=now)
        expected = int((now + timedelta(minutes=30)).timestamp())
        assert due_ts == expected, f"Failed for: {expr}"


def test_parse_time_expression_with_hours_variants():
    now = datetime(2025, 1, 1, 10, 0)

    # Test different hour formats
    for expr in ["in 2h", "in 2 hr", "in 2 hrs", "in 2 hours"]:
        due_ts = parse_time_expression(expr, now=now)
        expected = int((now + timedelta(hours=2)).timestamp())
        assert due_ts == expected, f"Failed for: {expr}"


@pytest.mark.skipif(not DATEPARSER_AVAILABLE, reason="dateparser not installed")
def test_parse_natural_language_time():
    now = datetime(2025, 1, 1, 10, 0)

    # Test "tomorrow at X"
    due_ts = parse_time_expression("tomorrow at 9am", now=now)
    assert due_ts is not None

    # Should be roughly 23 hours from now (10am -> 9am next day)
    expected_roughly = now + timedelta(hours=23)
    due_dt = datetime.fromtimestamp(due_ts)
    assert abs((due_dt - expected_roughly).total_seconds()) < 3600


def test_store_with_timezone(tmp_path):
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Test",
        timezone="America/Los_Angeles",
    )

    reminders = store.list_reminders()
    assert len(reminders) == 1
    assert reminders[0].timezone == "America/Los_Angeles"
    store.close()


def test_store_mark_error(tmp_path):
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts + 60, "Test")
    store.mark_error(reminder_id, "Test error")

    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.last_error == "Test error"
    store.close()


def test_scheduler_retry_logic(tmp_path):
    """Test that scheduler does NOT retry failed deliveries (exactly-once semantics).

    Phase 1: Reminders are claimed atomically and marked as fired immediately.
    Failed deliveries are logged but NOT retried to ensure exactly-once semantics.
    """
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    reminder_id = store.add_reminder("REMIND", now_ts - 1, "Retry test")

    attempts = []

    def publish_fn(message: str, title: str, rid: int) -> bool:
        attempts.append(rid)
        # Always fail to test that there's NO retry
        return False

    scheduler = ReminderScheduler(
        store,
        publish_fn=publish_fn,
        now_fn=lambda: now_ts,
        max_retries=3,
        retry_backoff=0,  # No backoff for testing
    )

    # Run 3 times
    for _ in range(3):
        scheduler.run_once()

    # Should only attempt ONCE (no retry with new exactly-once semantics)
    assert len(attempts) == 1

    # Reminder should still be marked as sent (fired) despite delivery failure
    reminders = store.list_reminders(include_sent=True)
    assert reminders[0].sent_at is not None
    assert reminders[0].status == "fired"
    assert reminders[0].last_error is not None  # Error should be logged

    store.close()


@pytest.mark.skipif(not PYTZ_AVAILABLE, reason="pytz not installed")
def test_format_timestamp_with_timezone():
    # Create a known timestamp
    dt = datetime(2025, 1, 1, 14, 30, 0)
    ts = int(dt.timestamp())

    # Format in different timezones
    formatted = format_timestamp_local(ts, "America/New_York")
    assert "2025-01-01" in formatted
    assert "14:30" in formatted or "09:30" in formatted  # Could be EST or EDT


def test_store_get_reminder(tmp_path):
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts + 3600, "Test message")

    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.id == reminder_id
    assert reminder.message == "Test message"

    # Non-existent reminder
    non_existent = store.get_reminder(99999)
    assert non_existent is None

    store.close()


# =============================================================================
# Phase 0 Tests: Dataclass Validation
# =============================================================================


def test_reminder_dataclass_valid_with_all_fields():
    """Valid reminder with all Phase 0 fields."""
    reminder = Reminder(
        id=1,
        kind="REMIND",
        message="Test",
        due_at=1000,
        created_at=900,
        sent_at=None,
        canceled_at=None,
        channel="voice",
        priority="high",
        status="scheduled",
        actions=["DONE", "SNOOZE_30"],
        source="phone",
    )
    assert reminder.channel == "voice"
    assert reminder.priority == "high"
    assert reminder.status == "scheduled"
    assert reminder.source == "phone"
    assert reminder.actions == ["DONE", "SNOOZE_30"]


def test_reminder_dataclass_invalid_channel():
    """Channel validation now happens at parsing level, not construction.
    
    The channel field accepts any string (or JSON list) and parses it.
    Invalid channels are only detected when routing delivery."""
    # This should work now - channel is parsed, not validated at construction
    r = Reminder(
        id=1,
        kind="REMIND",
        message="Test",
        due_at=1000,
        created_at=900,
        sent_at=None,
        canceled_at=None,
        channel="invalid_channel",  # Will be parsed to ["invalid_channel"]
    )
    # Verify it parses to a list
    assert r.channels == ["invalid_channel"]


def test_reminder_dataclass_invalid_priority():
    """Invalid priority raises ValueError."""
    with pytest.raises(ValueError, match="Invalid priority"):
        Reminder(
            id=1,
            kind="REMIND",
            message="Test",
            due_at=1000,
            created_at=900,
            sent_at=None,
            canceled_at=None,
            priority="urgent",
        )


def test_reminder_dataclass_invalid_status():
    """Invalid status raises ValueError."""
    with pytest.raises(ValueError, match="Invalid status"):
        Reminder(
            id=1,
            kind="REMIND",
            message="Test",
            due_at=1000,
            created_at=900,
            sent_at=None,
            canceled_at=None,
            status="pending",
        )


def test_reminder_dataclass_invalid_source():
    """Invalid source raises ValueError."""
    with pytest.raises(ValueError, match="Invalid source"):
        Reminder(
            id=1,
            kind="REMIND",
            message="Test",
            due_at=1000,
            created_at=900,
            sent_at=None,
            canceled_at=None,
            source="api",
        )


def test_reminder_dataclass_invalid_action():
    """Invalid action raises ValueError."""
    with pytest.raises(ValueError, match="Invalid action"):
        Reminder(
            id=1,
            kind="REMIND",
            message="Test",
            due_at=1000,
            created_at=900,
            sent_at=None,
            canceled_at=None,
            actions=["DONE", "INVALID_ACTION"],
        )


# =============================================================================
# Phase 0 Tests: Schema Migration
# =============================================================================


def test_schema_migration_adds_phase0_columns(tmp_path):
    """Legacy DB gets new columns after opening with ReminderStore."""
    import sqlite3

    db_path = tmp_path / "legacy.sqlite3"

    # Create a legacy database without Phase 0 columns
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            due_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            sent_at INTEGER,
            canceled_at INTEGER,
            timezone TEXT DEFAULT 'America/New_York',
            delivery_target TEXT,
            last_error TEXT
        )
    """)
    # Insert a legacy reminder
    conn.execute(
        "INSERT INTO reminders (kind, message, due_at, created_at) VALUES (?, ?, ?, ?)",
        ("REMIND", "Legacy reminder", 2000, 1000),
    )
    conn.commit()
    conn.close()

    # Open with ReminderStore which should trigger migration
    store = ReminderStore(db_path)
    reminder = store.get_reminder(1)

    assert reminder is not None
    assert reminder.channel == '["ntfy"]'  # Now stored as JSON list
    assert reminder.channels == ["ntfy"]  # But parses correctly via property
    assert reminder.priority == "med"  # Default
    assert reminder.status == "scheduled"  # Backfilled
    assert reminder.source == "other"  # Default
    assert reminder.actions == list(DEFAULT_ACTIONS)
    store.close()


def test_schema_migration_backfills_status(tmp_path):
    """Status backfill works correctly for sent and canceled reminders."""
    import sqlite3

    db_path = tmp_path / "legacy_status.sqlite3"

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            due_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            sent_at INTEGER,
            canceled_at INTEGER,
            timezone TEXT DEFAULT 'America/New_York',
            delivery_target TEXT,
            last_error TEXT
        )
    """)
    # Insert reminders with different states
    conn.execute(
        "INSERT INTO reminders (kind, message, due_at, created_at, sent_at) VALUES (?, ?, ?, ?, ?)",
        ("REMIND", "Sent reminder", 2000, 1000, 2001),
    )
    conn.execute(
        "INSERT INTO reminders (kind, message, due_at, created_at, canceled_at) VALUES (?, ?, ?, ?, ?)",
        ("REMIND", "Canceled reminder", 2000, 1000, 1500),
    )
    conn.execute(
        "INSERT INTO reminders (kind, message, due_at, created_at) VALUES (?, ?, ?, ?)",
        ("REMIND", "Scheduled reminder", 2000, 1000),
    )
    conn.commit()
    conn.close()

    store = ReminderStore(db_path)

    sent = store.get_reminder(1)
    assert sent.status == "fired"

    canceled = store.get_reminder(2)
    assert canceled.status == "canceled"

    scheduled = store.get_reminder(3)
    assert scheduled.status == "scheduled"

    store.close()


# =============================================================================
# Phase 0 Tests: New Methods
# =============================================================================


def test_add_reminder_with_phase0_params(tmp_path):
    """add_reminder() with Phase 0 params creates initial audit entry."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Test Phase 0",
        channel="voice",
        priority="high",
        actions=["DONE", "DELAY_2H"],
        source="phone",
    )

    reminder = store.get_reminder(reminder_id)
    assert reminder.channel == '["voice"]'  # Stored as JSON list
    assert reminder.channels == ["voice"]  # Parsed correctly
    assert reminder.priority == "high"
    assert reminder.status == "scheduled"
    assert reminder.actions == ["DONE", "DELAY_2H"]
    assert reminder.source == "phone"
    assert len(reminder.audit_log) == 1
    assert reminder.audit_log[0]["action"] == "created"
    assert "phone" in reminder.audit_log[0]["details"]
    store.close()


def test_add_reminder_invalid_channel(tmp_path):
    """Invalid channels are now accepted (parsed as single-item list).
    
    Validation happens at routing time, not storage time."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # This now works - invalid channels are parsed but won't route successfully
    reminder_id = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Test",
        channel="sms",
    )
    
    reminder = store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.channels == ["sms"]
    
    store.close()


def test_update_status_transitions_and_audits(tmp_path):
    """update_status() transitions status and appends audit."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts + 3600, "Test")
    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "scheduled"
    assert len(reminder.audit_log) == 1

    # Update to fired
    result = store.update_status(reminder_id, "fired", actor="scheduler", details="Delivered via ntfy")
    assert result is True

    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "fired"
    assert reminder.sent_at is not None
    assert len(reminder.audit_log) == 2
    assert "status_change:scheduled->fired" in reminder.audit_log[1]["action"]
    assert reminder.audit_log[1]["actor"] == "scheduler"
    store.close()


def test_update_status_invalid_status(tmp_path):
    """update_status() with invalid status raises ValueError."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts + 3600, "Test")

    with pytest.raises(ValueError, match="Invalid status"):
        store.update_status(reminder_id, "invalid_status")
    store.close()


def test_snooze_delays_due_at_and_records_audit(tmp_path):
    """snooze() delays due_at and records audit."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Use a due_at in the past (already fired)
    reminder_id = store.add_reminder("REMIND", now_ts - 60, "Test snooze")
    # First mark as fired
    store.update_status(reminder_id, "fired")

    # Now snooze - should set new due_at to now + 30 minutes
    result = store.snooze(reminder_id, 30, actor="user", details="User requested snooze")
    assert result is True

    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "scheduled"  # Snoozed reminders return to scheduled status
    assert reminder.sent_at is None  # Reset
    # Snooze sets due_at to current time + minutes, so it should be in the future
    assert reminder.due_at >= now_ts + (30 * 60) - 5  # Allow small time drift
    assert len(reminder.audit_log) == 3  # created, fired, snoozed
    assert "snoozed:30min" in reminder.audit_log[2]["action"]
    store.close()


def test_acknowledge_marks_fired_reminder(tmp_path):
    """acknowledge() marks fired reminder as acknowledged."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts - 60, "Test acknowledge")
    store.update_status(reminder_id, "fired")

    result = store.acknowledge(reminder_id, actor="user", details="User clicked DONE")
    assert result is True

    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "acknowledged"
    assert len(reminder.audit_log) == 3  # created, fired, acknowledged
    store.close()


def test_cancel_reminder_with_audit_logging(tmp_path):
    """cancel_reminder() adds audit log entry."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts + 3600, "Test cancel")

    result = store.cancel_reminder(reminder_id, actor="user", details="User canceled via webui")
    assert result is True

    # Get including canceled
    reminders = store.list_reminders(include_canceled=True)
    reminder = [r for r in reminders if r.id == reminder_id][0]
    assert reminder.status == "canceled"
    assert reminder.canceled_at is not None
    assert len(reminder.audit_log) == 2  # created, canceled
    assert reminder.audit_log[1]["action"] == "canceled"
    assert reminder.audit_log[1]["actor"] == "user"
    store.close()


# =============================================================================
# Phase 0 Tests: Round-trip Persistence
# =============================================================================


def test_roundtrip_create_update_snooze_acknowledge(tmp_path):
    """Create -> get -> update_status -> snooze -> acknowledge round-trip."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create
    rid = store.add_reminder(
        kind="REMIND",
        due_at=now_ts + 3600,
        message="Round-trip test",
        channel="both",
        priority="high",
        source="webui",
    )

    # Get and verify creation
    r = store.get_reminder(rid)
    assert r.status == "scheduled"
    # "both" is now expanded to ["ntfy", "voice"] during storage
    assert r.channels == ["ntfy", "voice"]
    assert len(r.audit_log) == 1

    # Fire
    store.update_status(rid, "fired", actor="scheduler")
    r = store.get_reminder(rid)
    assert r.status == "fired"
    assert len(r.audit_log) == 2

    # Snooze
    store.snooze(rid, 15, actor="user")
    r = store.get_reminder(rid)
    assert r.status == "scheduled"  # Snoozed reminders return to scheduled status
    assert len(r.audit_log) == 3

    # Fire again (after snooze period)
    store.update_status(rid, "fired", actor="scheduler")
    r = store.get_reminder(rid)
    assert r.status == "fired"
    assert len(r.audit_log) == 4

    # Acknowledge
    store.acknowledge(rid, actor="user")
    r = store.get_reminder(rid)
    assert r.status == "acknowledged"
    assert len(r.audit_log) == 5

    # Verify audit log has all entries in order
    actions = [entry["action"] for entry in r.audit_log]
    assert actions[0] == "created"
    assert "scheduled->fired" in actions[1]
    assert "snoozed:15min" in actions[2]
    assert "scheduled->fired" in actions[3]  # After snooze, status is 'scheduled' again
    assert "fired->acknowledged" in actions[4]

    store.close()


def test_constants_exported():
    """Verify Phase 0 constants are properly exported."""
    assert "ntfy" in REMINDER_CHANNELS
    assert "voice" in REMINDER_CHANNELS
    assert "both" in REMINDER_CHANNELS

    assert "low" in REMINDER_PRIORITIES
    assert "med" in REMINDER_PRIORITIES
    assert "high" in REMINDER_PRIORITIES

    assert "scheduled" in REMINDER_STATUSES
    assert "fired" in REMINDER_STATUSES
    assert "acknowledged" in REMINDER_STATUSES
    assert "snoozed" in REMINDER_STATUSES
    assert "canceled" in REMINDER_STATUSES

    assert "DONE" in REMINDER_ACTIONS
    assert "SNOOZE_30" in REMINDER_ACTIONS
    assert "DELAY_2H" in REMINDER_ACTIONS
    assert "EDIT_TIME" in REMINDER_ACTIONS

    assert "webui" in REMINDER_SOURCES
    assert "phone" in REMINDER_SOURCES
    assert "voice" in REMINDER_SOURCES
    assert "other" in REMINDER_SOURCES


def test_legacy_source_mapping():
    """Test that legacy sources like 'manual_cli' are mapped to valid sources.

    Regression test for: ValueError: Invalid source 'manual_cli', must be one of ['other','phone','voice','webui']
    """
    # Verify legacy sources are mapped correctly
    assert _LEGACY_SOURCE_MAP.get("manual_cli") == "other"
    assert _LEGACY_SOURCE_MAP.get("cli") == "other"
    assert _LEGACY_SOURCE_MAP.get("api") == "other"

    # Valid sources should pass through unchanged
    assert _LEGACY_SOURCE_MAP.get("webui", "webui") == "webui"
    assert _LEGACY_SOURCE_MAP.get("phone", "phone") == "phone"


def test_row_to_reminder_legacy_source(tmp_path):
    """Test that _row_to_reminder normalizes legacy source values.

    Regression test: reminders with legacy 'manual_cli' source in DB should
    not crash when loaded.
    """
    db_path = tmp_path / "test_reminders.db"
    store = ReminderStore(db_path)

    # Insert a reminder with legacy source directly via SQL
    with store._conn:
        store._conn.execute(
            """
            INSERT INTO reminders
            (kind, message, due_at, created_at, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("REMIND", "Test legacy source", 9999999999, 1737312600, "manual_cli"),
        )

    # list_reminders should not crash - it should normalize the legacy source
    reminders = store.list_reminders()
    assert len(reminders) == 1
    assert reminders[0].source == "other"  # manual_cli -> other


# =============================================================================
# ntfy Delivery Tests
# =============================================================================


def test_deliver_ntfy_payload():
    """deliver_ntfy() sends correct payload with action buttons."""
    reminder = Reminder(
        id=42,
        kind="REMIND",
        message="Take medication",
        due_at=1737312600,  # Fixed timestamp
        created_at=1737309000,
        sent_at=None,
        canceled_at=None,
        timezone="America/Chicago",
        priority="high",
        actions=["DONE", "SNOOZE_30", "DELAY_2H"],
    )

    with patch("milton_orchestrator.reminders.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200, text="ok")
        result = deliver_ntfy(
            reminder,
            ntfy_base_url="https://ntfy.sh",
            topic="milton-reminders",
            public_base_url="https://milton.ts.net",
        )

    # Assert result
    assert result["ok"] is True
    assert result["status_code"] == 200

    # Assert request
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://ntfy.sh/milton-reminders"

    # Assert message body
    body = call_args[1]["data"].decode("utf-8")
    assert "Take medication" in body
    assert "42" in body

    # Assert Actions header
    headers = call_args[1]["headers"]
    assert "Actions" in headers
    assert "DONE" in headers["Actions"]
    assert "https://milton.ts.net/api/reminders/42/action" in headers["Actions"]


def test_deliver_ntfy_without_public_url():
    """deliver_ntfy() without public_base_url omits Actions header."""
    reminder = Reminder(
        id=99,
        kind="ALARM",
        message="Wake up",
        due_at=1737312600,
        created_at=1737309000,
        sent_at=None,
        canceled_at=None,
        timezone="America/New_York",
        priority="low",
        actions=["DONE"],
    )

    with patch("milton_orchestrator.reminders.requests.post") as mock_post:
        mock_post.return_value = Mock(status_code=200, text="ok")
        result = deliver_ntfy(
            reminder,
            ntfy_base_url="https://ntfy.sh",
            topic="milton-alarms",
            public_base_url=None,
        )

    # Assert result
    assert result["ok"] is True
    assert result["status_code"] == 200

    # Assert no Actions header
    headers = mock_post.call_args[1]["headers"]
    assert "Actions" not in headers

    # Assert message body still correct
    body = mock_post.call_args[1]["data"].decode("utf-8")
    assert "Wake up" in body
    assert "99" in body


# ==============================================================================
# Atomic Claim Tests (Phase 1: Exactly-Once Semantics)
# ==============================================================================


def test_claim_due_reminders_atomic(tmp_path):
    """Test that claim_due_reminders atomically marks reminders as fired."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create 3 due reminders
    id1 = store.add_reminder("REMIND", now_ts - 10, "Reminder 1")
    id2 = store.add_reminder("REMIND", now_ts - 5, "Reminder 2")
    id3 = store.add_reminder("ALARM", now_ts - 1, "Alarm 1")

    # Verify they're scheduled
    all_reminders = store.list_reminders()
    assert len(all_reminders) == 3
    assert all([r.status == "scheduled" for r in all_reminders])

    # Claim them
    claimed = store.claim_due_reminders(now_ts)

    # Should get all 3
    assert len(claimed) == 3
    claimed_ids = {r.id for r in claimed}
    assert claimed_ids == {id1, id2, id3}

    # All should be marked as fired
    assert all([r.status == "fired" for r in claimed])
    assert all([r.sent_at == now_ts for r in claimed])

    # Trying to claim again should return empty (already claimed)
    claimed_again = store.claim_due_reminders(now_ts)
    assert len(claimed_again) == 0

    store.close()


def test_claim_due_reminders_respects_limit(tmp_path):
    """Test that claim_due_reminders respects the limit parameter."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create 5 due reminders
    for i in range(5):
        store.add_reminder("REMIND", now_ts - i, f"Reminder {i}")

    # Claim only 2
    claimed = store.claim_due_reminders(now_ts, limit=2)
    assert len(claimed) == 2

    # The remaining 3 should still be claimable
    claimed_again = store.claim_due_reminders(now_ts, limit=10)
    assert len(claimed_again) == 3

    store.close()


def test_claim_only_scheduled_reminders(tmp_path):
    """Test that claim_due_reminders only claims scheduled reminders."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create reminders in different states
    id_scheduled = store.add_reminder("REMIND", now_ts - 10, "Scheduled")
    id_snoozed = store.add_reminder("REMIND", now_ts - 5, "Snoozed")
    id_canceled = store.add_reminder("REMIND", now_ts - 3, "Canceled")

    # Change states
    store.snooze(id_snoozed, minutes=30, actor="test", details="Test snooze")
    store.cancel_reminder(id_canceled)

    # Claim due reminders
    claimed = store.claim_due_reminders(now_ts)

    # Should only get the scheduled one
    # Note: snoozed reminder's due_at was updated, so it's not due anymore
    # Only scheduled and not canceled should be claimed
    assert len(claimed) == 1
    assert claimed[0].id == id_scheduled

    store.close()


def test_scheduler_uses_atomic_claim(tmp_path):
    """Test that scheduler uses claim_due_reminders for exactly-once semantics."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create a due reminder
    reminder_id = store.add_reminder("REMIND", now_ts - 1, "Test message")

    sent_messages = []

    def publish_fn(message: str, title: str, rid: int) -> bool:
        sent_messages.append((message, title, rid))
        return True

    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)

    # Run once
    scheduler.run_once()

    # Should have sent the reminder
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "Test message"
    assert sent_messages[0][2] == reminder_id

    # Reminder should be marked as fired
    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "fired"
    assert reminder.sent_at == now_ts

    # Running again should NOT send it again (exactly-once)
    scheduler.run_once()
    assert len(sent_messages) == 1  # Still just 1 message

    store.close()


def test_scheduler_concurrent_claim(tmp_path):
    """Test that two schedulers racing don't double-fire reminders."""
    import threading

    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    # Create 10 due reminders
    for i in range(10):
        store.add_reminder("REMIND", now_ts - i, f"Message {i}")

    sent_messages_1 = []
    sent_messages_2 = []

    def publish_fn_1(message: str, title: str, rid: int) -> bool:
        sent_messages_1.append(rid)
        return True

    def publish_fn_2(message: str, title: str, rid: int) -> bool:
        sent_messages_2.append(rid)
        return True

    # Create two schedulers with the same store
    scheduler_1 = ReminderScheduler(store, publish_fn=publish_fn_1, now_fn=lambda: now_ts)
    scheduler_2 = ReminderScheduler(store, publish_fn=publish_fn_2, now_fn=lambda: now_ts)

    # Run both concurrently
    thread_1 = threading.Thread(target=scheduler_1.run_once)
    thread_2 = threading.Thread(target=scheduler_2.run_once)

    thread_1.start()
    thread_2.start()
    thread_1.join()
    thread_2.join()

    # Each scheduler should get some reminders, but NO overlap
    total_sent = len(sent_messages_1) + len(sent_messages_2)
    assert total_sent == 10  # All 10 should be sent

    # Check for no duplicates
    all_sent_ids = set(sent_messages_1) | set(sent_messages_2)
    assert len(all_sent_ids) == 10  # All unique

    # Intersection should be empty (no double-fire)
    overlap = set(sent_messages_1) & set(sent_messages_2)
    assert len(overlap) == 0

    store.close()


def test_scheduler_delivery_failure_no_revert(tmp_path):
    """Test that delivery failures don't revert claimed reminders to scheduled."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())

    reminder_id = store.add_reminder("REMIND", now_ts - 1, "Test")

    def publish_fn(message: str, title: str, rid: int) -> bool:
        # Simulate delivery failure
        return False

    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)
    scheduler.run_once()

    # Reminder should still be fired (claimed), not reverted to scheduled
    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "fired"
    assert reminder.sent_at == now_ts
    assert reminder.last_error is not None  # Error should be recorded

    # Running again should NOT retry (exactly-once semantics)
    scheduler.run_once()
    reminder = store.get_reminder(reminder_id)
    assert reminder.status == "fired"  # Still fired, not scheduled

    store.close()


# =============================================================================
# Health Check Tests
# =============================================================================


def test_health_stats_empty_database(tmp_path):
    """get_health_stats() returns correct values for empty database."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    
    stats = store.get_health_stats()
    
    assert stats["scheduled_count"] == 0
    assert stats["next_due_at"] is None
    assert stats["last_scheduler_heartbeat"] is None
    assert stats["heartbeat_age_sec"] is None
    assert stats["last_ntfy_ok"] is None
    assert stats["last_error"] is None
    
    store.close()


def test_health_stats_with_pending_reminders(tmp_path):
    """get_health_stats() counts scheduled reminders and finds next due."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Add reminders at different times
    store.add_reminder("REMIND", now_ts + 3600, "In 1 hour")
    store.add_reminder("REMIND", now_ts + 7200, "In 2 hours")
    store.add_reminder("REMIND", now_ts + 1800, "In 30 min")  # This is next
    
    stats = store.get_health_stats()
    
    assert stats["scheduled_count"] == 3
    assert stats["next_due_at"] == now_ts + 1800
    
    store.close()


def test_health_stats_excludes_fired_and_canceled(tmp_path):
    """get_health_stats() only counts scheduled reminders."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Add various reminders
    rid1 = store.add_reminder("REMIND", now_ts + 3600, "Scheduled")
    rid2 = store.add_reminder("REMIND", now_ts + 7200, "To be fired")
    rid3 = store.add_reminder("REMIND", now_ts + 1800, "To be canceled")
    
    # Mark some as fired/canceled
    store.update_status(rid2, "fired")
    store.cancel_reminder(rid3)
    
    stats = store.get_health_stats()
    
    # Only rid1 should be counted
    assert stats["scheduled_count"] == 1
    assert stats["next_due_at"] == now_ts + 3600
    
    store.close()


def test_health_stats_tracks_heartbeat(tmp_path):
    """get_health_stats() returns heartbeat metadata."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Set heartbeat metadata
    store.set_metadata("last_heartbeat", str(now_ts - 30))
    
    stats = store.get_health_stats()
    
    assert stats["last_scheduler_heartbeat"] == now_ts - 30
    assert stats["heartbeat_age_sec"] == 30
    
    store.close()


def test_health_stats_tracks_ntfy_success(tmp_path):
    """get_health_stats() returns last successful ntfy delivery timestamp."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Set ntfy success metadata
    store.set_metadata("last_ntfy_ok", str(now_ts - 60))
    
    stats = store.get_health_stats()
    
    assert stats["last_ntfy_ok"] == now_ts - 60
    
    store.close()


def test_health_stats_shows_last_error(tmp_path):
    """get_health_stats() returns most recent error from any reminder."""
    import time
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Create reminders with errors
    rid1 = store.add_reminder("REMIND", now_ts - 100, "Old error")
    rid2 = store.add_reminder("REMIND", now_ts - 50, "Recent error")
    
    store.mark_error(rid1, "Old failure")
    time.sleep(1.1)  # Ensure different integer timestamps (>1 second)
    store.mark_error(rid2, "Recent failure")
    
    stats = store.get_health_stats()
    
    # Should show the most recent error (based on updated_at)
    assert stats["last_error"] == "Recent failure"
    
    store.close()


def test_scheduler_updates_heartbeat(tmp_path):
    """Scheduler run_once() updates heartbeat metadata."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    def publish_fn(message: str, title: str, rid: int) -> bool:
        return True
    
    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)
    scheduler.run_once()
    
    # Check that heartbeat was recorded
    heartbeat_meta = store.get_metadata("last_heartbeat")
    assert heartbeat_meta is not None
    assert int(heartbeat_meta[0]) == now_ts
    
    store.close()


def test_scheduler_updates_ntfy_on_success(tmp_path):
    """Scheduler records last successful ntfy delivery."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Create due reminder
    store.add_reminder("REMIND", now_ts - 1, "Test")
    
    def publish_fn(message: str, title: str, rid: int) -> bool:
        return True  # Success
    
    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)
    scheduler.run_once()
    
    # Check that ntfy success was recorded
    ntfy_meta = store.get_metadata("last_ntfy_ok")
    assert ntfy_meta is not None
    assert int(ntfy_meta[0]) == now_ts
    
    store.close()


def test_metadata_roundtrip(tmp_path):
    """Metadata set/get operations work correctly."""
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    
    # Set metadata
    store.set_metadata("test_key", "test_value")
    
    # Get metadata
    result = store.get_metadata("test_key")
    assert result is not None
    assert result[0] == "test_value"
    assert result[1] <= now_ts + 1  # Timestamp should be around now
    
    # Update metadata
    store.set_metadata("test_key", "updated_value")
    result = store.get_metadata("test_key")
    assert result[0] == "updated_value"
    
    # Get non-existent key
    result = store.get_metadata("nonexistent")
    assert result is None
    
    store.close()
