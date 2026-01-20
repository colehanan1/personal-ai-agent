"""
Phase 2C Tests: Reminder Enrichment with Context

Tests that reminder creation is enriched with context_ref linking to
recent activity snapshots, while remaining non-blocking.
"""
import os
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def temp_state_dir():
    """Create temporary state directory for isolated tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_env = os.environ.get("MILTON_STATE_DIR")
        os.environ["MILTON_STATE_DIR"] = tmpdir
        yield Path(tmpdir)
        if old_env:
            os.environ["MILTON_STATE_DIR"] = old_env
        else:
            os.environ.pop("MILTON_STATE_DIR", None)


@pytest.fixture
def reminder_store(temp_state_dir):
    """Initialize ReminderStore in temp directory."""
    from milton_orchestrator.reminders import ReminderStore
    
    db_path = temp_state_dir / "reminders.db"
    store = ReminderStore(db_path=db_path)
    yield store
    store.close()


@pytest.fixture
def snapshot_store(temp_state_dir):
    """Initialize ActivitySnapshotStore in temp directory."""
    from milton_orchestrator.activity_snapshots import ActivitySnapshotStore
    
    db_path = temp_state_dir / "activity_snapshots.db"
    store = ActivitySnapshotStore(db_path=db_path)
    yield store
    store.close()


def test_reminder_schema_has_context_ref_column(reminder_store):
    """Test that reminders table includes context_ref column."""
    import sqlite3
    
    cursor = reminder_store._conn.execute("PRAGMA table_info(reminders)")
    columns = {row[1] for row in cursor.fetchall()}
    
    assert "context_ref" in columns, "reminders table should have context_ref column"


def test_reminder_dataclass_has_context_ref_field():
    """Test that Reminder dataclass includes context_ref field."""
    from milton_orchestrator.reminders import Reminder
    
    # Check if Reminder has context_ref annotation
    annotations = Reminder.__annotations__
    assert "context_ref" in annotations, "Reminder dataclass should have context_ref field"


def test_add_reminder_accepts_context_ref_parameter(reminder_store):
    """Test that add_reminder() accepts context_ref parameter."""
    import inspect
    
    sig = inspect.signature(reminder_store.add_reminder)
    params = sig.parameters
    
    assert "context_ref" in params, "add_reminder() should accept context_ref parameter"


def test_reminder_creation_attaches_context_ref_when_snapshots_exist(
    reminder_store, snapshot_store
):
    """Test that reminder creation links to recent activity snapshot."""
    # Create a recent activity snapshot
    snapshot_id = snapshot_store.add_snapshot(
        device_id="test-laptop",
        device_type="mac",
        captured_at=int(time.time()),
        active_app="VSCode",
        window_title="test.py",
        project_path="/home/user/project",
        git_branch="feature/test",
    )
    
    # Create reminder with context_ref
    current_time = int(time.time())
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="Test reminder",
        timezone="America/Chicago",
        context_ref=snapshot_id,
    )
    
    # Retrieve reminder and verify context_ref is set
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.context_ref == snapshot_id


def test_reminder_creation_works_without_context_ref(reminder_store):
    """Test that reminder creation still works when context_ref is None."""
    current_time = int(time.time())
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="Test reminder without context",
        timezone="America/Chicago",
        context_ref=None,
    )
    
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.context_ref is None
    assert reminder.message == "Test reminder without context"


def test_reminder_creation_defaults_context_ref_to_none(reminder_store):
    """Test that context_ref defaults to None if not provided."""
    current_time = int(time.time())
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="Test reminder",
        timezone="America/Chicago",
        # context_ref not provided
    )
    
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.context_ref is None


def test_get_reminder_by_id_returns_context_ref(reminder_store, snapshot_store):
    """Test that get_reminder() returns context_ref field."""
    # Create snapshot
    snapshot_id = snapshot_store.add_snapshot(
        device_id="test-device",
        device_type="pc",
        captured_at=int(time.time()),
        active_app="Chrome",
    )
    
    # Create reminder with context
    current_time = int(time.time())
    reminder_id = reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="Test",
        context_ref=snapshot_id,
    )
    
    # Retrieve and verify
    reminder = reminder_store.get_reminder(reminder_id)
    assert reminder.context_ref == snapshot_id


def test_list_reminders_includes_context_ref(reminder_store, snapshot_store):
    """Test that list_reminders() returns context_ref for each reminder."""
    # Create snapshot
    snapshot_id = snapshot_store.add_snapshot(
        device_id="test-device",
        device_type="mac",
        captured_at=int(time.time()),
    )
    
    # Create reminders (one with context, one without)
    current_time = int(time.time())
    reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="With context",
        context_ref=snapshot_id,
    )
    reminder_store.add_reminder(
        kind="REMIND",
        due_at=current_time + 7200,
        message="Without context",
        context_ref=None,
    )
    
    reminders = reminder_store.list_reminders()
    assert len(reminders) >= 2
    
    # Find our test reminders
    with_context = next((r for r in reminders if r.message == "With context"), None)
    without_context = next((r for r in reminders if r.message == "Without context"), None)
    
    assert with_context is not None
    assert with_context.context_ref == snapshot_id
    
    assert without_context is not None
    assert without_context.context_ref is None


def test_context_ref_persists_across_store_reload(temp_state_dir, snapshot_store):
    """Test that context_ref persists when store is reopened."""
    from milton_orchestrator.reminders import ReminderStore
    
    # Create snapshot
    snapshot_id = snapshot_store.add_snapshot(
        device_id="test-device",
        device_type="mac",
        captured_at=int(time.time()),
    )
    
    # Create reminder in first store instance
    db_path = temp_state_dir / "reminders.db"
    store1 = ReminderStore(db_path=db_path)
    current_time = int(time.time())
    reminder_id = store1.add_reminder(
        kind="REMIND",
        due_at=current_time + 3600,
        message="Test persistence",
        context_ref=snapshot_id,
    )
    store1.close()
    
    # Reopen store and verify context_ref persists
    store2 = ReminderStore(db_path=db_path)
    reminder = store2.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.context_ref == snapshot_id
    store2.close()


def test_migration_idempotency_with_context_ref(temp_state_dir):
    """Test that context_ref migration is idempotent (safe to run multiple times)."""
    from milton_orchestrator.reminders import ReminderStore
    
    db_path = temp_state_dir / "reminders.db"
    
    # Create store (runs migration)
    store1 = ReminderStore(db_path=db_path)
    store1.close()
    
    # Reopen store (should not fail on duplicate migration)
    store2 = ReminderStore(db_path=db_path)
    
    # Verify column exists
    cursor = store2._conn.execute("PRAGMA table_info(reminders)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "context_ref" in columns
    
    store2.close()
