"""
Phase 2C Tests: Context Query Command

Tests for /recent and /context commands that query activity snapshots
to answer "what was I doing" questions.
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
def snapshot_store(temp_state_dir):
    """Initialize ActivitySnapshotStore in temp directory."""
    from milton_orchestrator.activity_snapshots import ActivitySnapshotStore
    
    db_path = temp_state_dir / "activity_snapshots.db"
    store = ActivitySnapshotStore(db_path=db_path)
    yield store
    store.close()


@pytest.fixture
def command_processor(temp_state_dir):
    """Initialize CommandProcessor with temp state directory."""
    from milton_gateway.command_processor import CommandProcessor
    
    processor = CommandProcessor(state_dir=temp_state_dir)
    yield processor
    # Note: close() is async but we're not using it in these sync tests


def test_command_processor_has_context_query_handler():
    """Test that CommandProcessor has _handle_context_query method."""
    from milton_gateway.command_processor import CommandProcessor
    
    processor = CommandProcessor()
    assert hasattr(processor, "_handle_context_query"), \
        "CommandProcessor should have _handle_context_query method"


def test_recent_command_recognized(command_processor):
    """Test that /recent command is recognized as a command."""
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True, "/recent should be recognized as a command"


def test_context_command_recognized(command_processor):
    """Test that /context command is recognized as a command."""
    result = command_processor._handle_context_query("/context")
    
    assert result.is_command is True, "/context should be recognized as a command"


def test_recent_command_returns_empty_when_no_snapshots(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent returns empty result when no snapshots exist."""
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.error is None
    assert result.response is not None
    assert "No recent activity" in result.response or "0 snapshots" in result.response


def test_recent_command_returns_snapshots(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent returns recent activity snapshots."""
    # Create some snapshots
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 1800,  # 30 minutes ago
        active_app="VSCode",
        window_title="test.py",
        project_path="/home/user/milton",
        git_branch="feature/phase2c",
    )
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 600,  # 10 minutes ago
        active_app="Chrome",
        window_title="GitHub - Pull Requests",
    )
    
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.error is None
    assert result.response is not None
    
    # Should contain device info
    assert "laptop-1" in result.response or "mac" in result.response
    
    # Should contain app info
    assert "VSCode" in result.response or "Chrome" in result.response



def test_recent_command_with_time_filter(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent supports time filtering (e.g., /recent 30m, /recent 2h)."""
    now = int(time.time())
    
    # Create snapshot 3 hours ago
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 10800,  # 3 hours ago
        active_app="OldApp",
    )
    
    # Create snapshot 1 hour ago
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 3600,  # 1 hour ago
        active_app="RecentApp",
    )
    
    # Query last 2 hours (should only get RecentApp)
    result = command_processor._handle_context_query("/recent 2h")
    
    assert result.is_command is True
    assert result.error is None
    assert "RecentApp" in result.response
    assert "OldApp" not in result.response



def test_recent_command_shows_project_and_branch(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent output includes project path and git branch."""
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="work-laptop",
        device_type="mac",
        captured_at=now - 300,  # 5 minutes ago
        active_app="VSCode",
        project_path="/Users/cole/milton",
        git_branch="feature/phase2c",
    )
    
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.response is not None
    assert "/Users/cole/milton" in result.response or "milton" in result.response
    assert "feature/phase2c" in result.response or "phase2c" in result.response



def test_recent_command_shows_timestamp(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent output includes readable timestamps."""
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 1800,  # 30 minutes ago
        active_app="Chrome",
    )
    
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.response is not None
    # Should contain relative time like "30 minutes ago" or "30m ago" or timestamp
    assert any(
        pattern in result.response.lower()
        for pattern in ["ago", "minutes", "hours", "min", "h"]
    )



def test_recent_command_groups_by_device(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent groups snapshots by device."""
    now = int(time.time())
    
    # Create snapshots from two devices
    snapshot_store.add_snapshot(
        device_id="laptop-mac",
        device_type="mac",
        captured_at=now - 600,
        active_app="VSCode",
    )
    snapshot_store.add_snapshot(
        device_id="desktop-pc",
        device_type="pc",
        captured_at=now - 300,
        active_app="PyCharm",
    )
    
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.response is not None
    
    # Should mention both devices
    assert "laptop-mac" in result.response or "mac" in result.response
    assert "desktop-pc" in result.response or "pc" in result.response
    
    # Should mention both apps
    assert "VSCode" in result.response
    assert "PyCharm" in result.response



def test_recent_command_limits_results(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent limits number of results shown (e.g., last 10)."""
    now = int(time.time())
    
    # Create 15 snapshots
    for i in range(15):
        snapshot_store.add_snapshot(
            device_id="laptop-1",
            device_type="mac",
            captured_at=now - (i * 300),  # Every 5 minutes
            active_app=f"App{i}",
        )
    
    result = command_processor._handle_context_query("/recent")
    
    assert result.is_command is True
    assert result.response is not None
    
    # Should not show all 15 (should be limited, e.g., to 10)
    # Count how many app names appear in response
    app_count = sum(1 for i in range(15) if f"App{i}" in result.response)
    assert app_count <= 10, "Should limit results to reasonable number"



def test_context_command_same_as_recent(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /context command works the same as /recent."""
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 600,
        active_app="TestApp",
    )
    
    recent_result = command_processor._handle_context_query("/recent")
    context_result = command_processor._handle_context_query("/context")
    
    # Both should work
    assert recent_result.is_command is True
    assert context_result.is_command is True
    
    # Both should contain the same info
    assert "TestApp" in recent_result.response
    assert "TestApp" in context_result.response



def test_recent_command_handles_missing_optional_fields(
    command_processor, snapshot_store, temp_state_dir
):
    """Test that /recent handles snapshots with missing optional fields gracefully."""
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="minimal-device",
        device_type="pi",
        captured_at=now - 300,
        # No active_app, window_title, project_path, git_branch
    )
    
    result = command_processor._handle_context_query("/recent")
    
    # Should not error, should show device at minimum
    assert result.is_command is True
    assert result.error is None
    assert result.response is not None
    assert "minimal-device" in result.response or "pi" in result.response
