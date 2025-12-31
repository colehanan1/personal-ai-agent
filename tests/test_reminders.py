"""Tests for reminder parsing and scheduling."""

from datetime import datetime, timedelta

import pytest

from milton_orchestrator.reminders import (
    ReminderScheduler,
    ReminderStore,
    parse_reminder_command,
    parse_time_expression,
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

    def publish_fn(message: str) -> bool:
        sent_messages.append(message)
        return True

    scheduler = ReminderScheduler(store, publish_fn=publish_fn, now_fn=lambda: now_ts)
    scheduler.run_once()

    assert sent_messages
    reminders = store.list_reminders(include_sent=True)
    assert reminders[0].id == reminder_id
    assert reminders[0].sent_at is not None
    store.close()
