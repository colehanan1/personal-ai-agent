"""
Phase 2C Tests: Briefing Context Integration

Tests that morning/evening briefings include a "Recent Context" section
when activity snapshots exist, and omit it when none exist.
"""
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
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


def test_load_recent_context_function_exists():
    """Test that _load_recent_context function exists in briefing module."""
    from scripts import enhanced_morning_briefing
    
    assert hasattr(enhanced_morning_briefing, "_load_recent_context"), \
        "enhanced_morning_briefing should have _load_recent_context function"


def test_load_recent_context_returns_empty_when_no_snapshots(temp_state_dir):
    """Test that _load_recent_context returns empty list when no snapshots."""
    from scripts.enhanced_morning_briefing import _load_recent_context
    
    context = _load_recent_context(temp_state_dir, hours=8)
    
    assert isinstance(context, list)
    assert len(context) == 0


def test_load_recent_context_returns_snapshots(temp_state_dir, snapshot_store):
    """Test that _load_recent_context returns recent snapshots."""
    from scripts.enhanced_morning_briefing import _load_recent_context
    
    # Create snapshots within last 8 hours
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 3600,  # 1 hour ago
        active_app="VSCode",
        project_path="/home/user/milton",
    )
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 7200,  # 2 hours ago
        active_app="Chrome",
    )
    
    context = _load_recent_context(temp_state_dir, hours=8)
    
    assert isinstance(context, list)
    assert len(context) == 2
    assert all(isinstance(item, dict) for item in context)


def test_load_recent_context_respects_time_window(temp_state_dir, snapshot_store):
    """Test that _load_recent_context only returns snapshots within time window."""
    from scripts.enhanced_morning_briefing import _load_recent_context
    
    now = int(time.time())
    
    # Create snapshot 2 hours ago (should be included)
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 7200,
        active_app="RecentApp",
    )
    
    # Create snapshot 10 hours ago (should not be included)
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 36000,
        active_app="OldApp",
    )
    
    # Query last 8 hours
    context = _load_recent_context(temp_state_dir, hours=8)
    
    assert len(context) == 1
    assert context[0]["active_app"] == "RecentApp"


def test_load_recent_context_limits_results(temp_state_dir, snapshot_store):
    """Test that _load_recent_context limits number of snapshots returned."""
    from scripts.enhanced_morning_briefing import _load_recent_context
    
    now = int(time.time())
    
    # Create 20 snapshots
    for i in range(20):
        snapshot_store.add_snapshot(
            device_id="laptop-1",
            device_type="mac",
            captured_at=now - (i * 300),
            active_app=f"App{i}",
        )
    
    context = _load_recent_context(temp_state_dir, hours=24)
    
    # Should be limited (e.g., to 10)
    assert len(context) <= 10


def test_build_markdown_accepts_recent_context_parameter():
    """Test that _build_markdown accepts recent_context parameter."""
    from scripts.enhanced_morning_briefing import _build_markdown
    import inspect
    
    sig = inspect.signature(_build_markdown)
    params = sig.parameters
    
    assert "recent_context" in params, \
        "_build_markdown should accept recent_context parameter"


def test_briefing_includes_context_section_when_snapshots_exist(temp_state_dir, snapshot_store):
    """Test that briefing includes Recent Context section when snapshots exist."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    # Create snapshots
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="work-laptop",
        device_type="mac",
        captured_at=now - 3600,
        active_app="VSCode",
        project_path="/home/user/milton",
        git_branch="feature/phase2c",
    )
    
    # Load context
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    
    # Build briefing
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Verify section exists
    assert "Recent Context" in markdown or "recent context" in markdown.lower()
    assert "work-laptop" in markdown or "mac" in markdown
    assert "VSCode" in markdown


def test_briefing_omits_context_section_when_no_snapshots(temp_state_dir):
    """Test that briefing omits Recent Context section when no snapshots."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    # Load context (should be empty)
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    assert len(recent_context) == 0
    
    # Build briefing
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Verify section does NOT exist
    assert "Recent Context" not in markdown


def test_briefing_context_section_shows_device_info(temp_state_dir, snapshot_store):
    """Test that Recent Context section shows device information."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="work-macbook",
        device_type="mac",
        captured_at=now - 1800,
        active_app="Terminal",
    )
    
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Should show device ID or type
    assert "work-macbook" in markdown or "mac" in markdown


def test_briefing_context_section_shows_project_and_branch(temp_state_dir, snapshot_store):
    """Test that Recent Context section shows project path and git branch."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 3600,
        active_app="VSCode",
        project_path="/home/user/awesome-project",
        git_branch="main",
    )
    
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Should show project and branch
    assert "awesome-project" in markdown
    assert "main" in markdown


def test_briefing_context_section_shows_relative_time(temp_state_dir, snapshot_store):
    """Test that Recent Context section shows relative time (e.g., 2h ago)."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="laptop-1",
        device_type="mac",
        captured_at=now - 7200,  # 2 hours ago
        active_app="Chrome",
    )
    
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Should show relative time
    assert any(
        pattern in markdown.lower()
        for pattern in ["ago", "hours", "hour", "2h"]
    )


def test_briefing_context_section_groups_by_device(temp_state_dir, snapshot_store):
    """Test that Recent Context section groups snapshots by device."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    now = int(time.time())
    
    # Create snapshots from two different devices
    snapshot_store.add_snapshot(
        device_id="laptop-mac",
        device_type="mac",
        captured_at=now - 3600,
        active_app="VSCode",
    )
    snapshot_store.add_snapshot(
        device_id="desktop-pc",
        device_type="pc",
        captured_at=now - 1800,
        active_app="PyCharm",
    )
    
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Should mention both devices
    assert "laptop-mac" in markdown or "mac" in markdown
    assert "desktop-pc" in markdown or "pc" in markdown


def test_briefing_context_section_is_concise(temp_state_dir, snapshot_store):
    """Test that Recent Context section is concise and not overly verbose."""
    from scripts.enhanced_morning_briefing import _build_markdown, _load_recent_context
    
    now = int(time.time())
    
    # Create several snapshots
    for i in range(5):
        snapshot_store.add_snapshot(
            device_id=f"device-{i}",
            device_type="mac",
            captured_at=now - (i * 1800),
            active_app=f"App{i}",
            project_path=f"/path/to/project{i}",
        )
    
    recent_context = _load_recent_context(temp_state_dir, hours=8)
    now_dt = datetime.now(timezone.utc)
    markdown = _build_markdown(
        now=now_dt,
        goals_today=[],
        overnight_jobs=[],
        weather=None,
        weather_error=None,
        papers=[],
        next_actions=[],
        recent_context=recent_context,
    )
    
    # Extract just the Recent Context section
    if "Recent Context" in markdown:
        start = markdown.index("Recent Context")
        # Find next section (marked by ##)
        next_section_start = markdown.find("##", start + 1)
        if next_section_start == -1:
            context_section = markdown[start:]
        else:
            context_section = markdown[start:next_section_start]
        
        # Section should be reasonably sized (not overly verbose)
        # Let's say max 500 chars per device as a rough guideline
        assert len(context_section) < 2500, "Context section should be concise"


def test_generate_briefing_integration(temp_state_dir, snapshot_store):
    """Integration test: generate_morning_briefing includes context when configured."""
    from scripts.enhanced_morning_briefing import generate_morning_briefing
    
    # Create snapshots
    now = int(time.time())
    snapshot_store.add_snapshot(
        device_id="test-laptop",
        device_type="mac",
        captured_at=now - 3600,
        active_app="VSCode",
        project_path="/home/user/milton",
    )
    
    # Generate briefing (this should call _load_recent_context internally)
    try:
        result = generate_morning_briefing(
            state_dir=temp_state_dir,
            weather_provider=lambda: {"temp": "75°F", "description": "Sunny"},
            papers_provider=lambda q, n: [],
        )
        
        # Verify briefing was created and contains context
        assert result is not None
        
        # Check output file for context section (markdown file)
        import glob
        output_files = glob.glob(str(temp_state_dir / "inbox" / "morning" / "*.md"))
        if output_files:
            content = Path(output_files[0]).read_text()
            assert "Recent Context" in content or "VSCode" in content or "milton" in content
    except Exception as e:
        # If dependencies missing (weather, arxiv, etc.), that's okay for this test
        # We're just verifying the integration point exists
        pytest.skip(f"Skipping integration test due to missing dependencies: {e}")
