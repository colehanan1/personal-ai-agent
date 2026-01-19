"""
Hermetic tests for morning briefing goals integration.

Tests that the morning briefing reliably reads and renders goals from STATE_DIR.
All tests use temp directories and avoid network calls.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from goals.api import add_goal
from scripts.enhanced_morning_briefing import generate_morning_briefing


def test_briefing_with_daily_goals(tmp_path):
    """Test briefing includes daily goals when present."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Add test goals
    add_goal("daily", "Complete morning standup", base_dir=tmp_path, now=now)
    add_goal("daily", "Review pull requests", base_dir=tmp_path, now=now)
    add_goal("daily", "Update documentation", base_dir=tmp_path, now=now)

    # Generate briefing with mocked external providers
    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    # Verify output file exists
    assert output_path.exists()
    content = output_path.read_text()

    # Verify Goals section exists
    assert "Goals" in content or "goals" in content.lower()

    # Verify all goals appear in output
    assert "Complete morning standup" in content
    assert "Review pull requests" in content
    assert "Update documentation" in content

    # Verify section is not empty/disabled
    assert "No goals set" not in content


def test_briefing_with_weekly_goals_fallback(tmp_path):
    """Test briefing falls back to weekly goals when daily is empty."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Only add weekly goals
    add_goal("weekly", "Complete project milestone", base_dir=tmp_path, now=now)
    add_goal("weekly", "Prepare presentation", base_dir=tmp_path, now=now)

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    content = output_path.read_text()

    # Verify weekly goals appear
    assert "Complete project milestone" in content
    assert "Prepare presentation" in content


def test_briefing_with_no_goals(tmp_path):
    """Test briefing handles missing/empty goals gracefully."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Don't add any goals - file may not exist or be empty

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    content = output_path.read_text()

    # Verify Goals section still exists (doesn't silently fail)
    assert "Goals" in content or "goals" in content.lower()

    # Verify it indicates no goals
    assert "No goals set" in content


def test_briefing_goals_in_phd_mode(tmp_path):
    """Test goals section in PhD-aware mode."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Add goals
    add_goal("daily", "Analyze imaging data", base_dir=tmp_path, now=now)
    add_goal("daily", "Write results section", base_dir=tmp_path, now=now)

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=True,
    )

    content = output_path.read_text()

    # In PhD mode, should show "Goals for Today"
    assert "Goals for Today" in content

    # Goals should be present
    assert "Analyze imaging data" in content
    assert "Write results section" in content


def test_briefing_goals_section_deterministic(tmp_path):
    """Test Goals section appears in consistent location and format."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    add_goal("daily", "Test deterministic output", base_dir=tmp_path, now=now)

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    content = output_path.read_text()
    lines = content.splitlines()

    # Find Goals section header
    goals_header_idx = None
    for idx, line in enumerate(lines):
        if "## " in line and "Goals" in line:
            goals_header_idx = idx
            break

    assert goals_header_idx is not None, "Goals section header not found"

    # Verify it's a markdown section header
    assert lines[goals_header_idx].startswith("## ")

    # Verify goal appears as a list item after header
    goal_found = False
    for i in range(goals_header_idx + 1, min(goals_header_idx + 10, len(lines))):
        if "Test deterministic output" in lines[i]:
            assert lines[i].startswith("- "), "Goal should be a list item"
            goal_found = True
            break

    assert goal_found, "Goal not found after section header"


def test_briefing_goals_with_special_characters(tmp_path):
    """Test goals with special characters are properly escaped/rendered."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Goals with various special characters
    add_goal("daily", "Fix bug in `calculate_metrics()` function", base_dir=tmp_path, now=now)
    add_goal("daily", "Update README.md & CHANGELOG.md", base_dir=tmp_path, now=now)

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    content = output_path.read_text()

    # Goals should appear with special chars intact
    assert "calculate_metrics()" in content
    assert "README.md & CHANGELOG.md" in content


def test_briefing_goals_limit(tmp_path):
    """Test that briefing respects goal limit (default 5)."""
    now = datetime(2026, 1, 18, 8, 0, tzinfo=timezone.utc)

    # Add more than 5 goals
    for i in range(10):
        add_goal("daily", f"Goal number {i+1}", base_dir=tmp_path, now=now)

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=lambda: {
            "location": "Test City",
            "temp": 70,
            "condition": "Clear",
            "low": 60,
            "high": 75,
            "humidity": 50,
        },
        papers_provider=lambda q, m: [],
        max_papers=0,
        overnight_hours=12,
        phd_aware=False,
    )

    content = output_path.read_text()

    # First 5 should be present
    for i in range(5):
        assert f"Goal number {i+1}" in content

    # Goals beyond 5 should not appear (default limit in _summarize_goals)
    for i in range(5, 10):
        assert f"Goal number {i+1}" not in content
