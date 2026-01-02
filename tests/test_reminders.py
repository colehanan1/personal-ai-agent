"""Tests for reminder parsing and scheduling."""

from datetime import datetime, timedelta

import pytest

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

from milton_orchestrator.reminders import (
    ReminderScheduler,
    ReminderStore,
    parse_reminder_command,
    parse_time_expression,
    format_timestamp_local,
    DATEPARSER_AVAILABLE,
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
    store = ReminderStore(tmp_path / "reminders.sqlite3")
    now_ts = int(datetime.now().timestamp())
    reminder_id = store.add_reminder("REMIND", now_ts - 1, "Retry test")

    attempts = []

    def publish_fn(message: str, title: str, rid: int) -> bool:
        attempts.append(rid)
        # Fail first 2 attempts, succeed on 3rd
        return len(attempts) >= 3

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

    assert len(attempts) == 3
    reminders = store.list_reminders(include_sent=True)
    assert reminders[0].sent_at is not None
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
