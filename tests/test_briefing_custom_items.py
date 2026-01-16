"""Tests for custom briefing items integration in morning briefing generator.

Tests cover:
1. Custom items section appears in briefing output
2. Active items are rendered with correct ordering
3. Expired items are excluded
4. Priority and due_at formatting
5. Graceful degradation when store missing or errors
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path for imports
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from storage.briefing_store import BriefingStore
from scripts.enhanced_morning_briefing import (
    generate_morning_briefing,
    _load_custom_items,
    _build_markdown,
)


class TestCustomItemsLoader:
    """Tests for _load_custom_items function."""

    def test_load_custom_items_with_active_items(self, tmp_path):
        """Test loading active items from store."""
        # Create store with test items
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        id1 = store.add_item(content="High priority task", priority=10)
        id2 = store.add_item(content="Normal task", priority=0, due_at="2026-01-15T09:00:00Z")
        id3 = store.add_item(content="Medium task", priority=5)
        store.close()

        # Load items
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now, max_items=10)

        # Verify
        assert error is None
        assert len(items) == 3
        # Should be ordered by priority DESC
        assert items[0]["content"] == "High priority task"
        assert items[0]["priority"] == 10
        assert items[1]["content"] == "Medium task"
        assert items[1]["priority"] == 5
        assert items[2]["content"] == "Normal task"
        assert items[2]["priority"] == 0

    def test_load_custom_items_excludes_expired(self, tmp_path):
        """Test that expired items are excluded."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        id_valid = store.add_item(content="Valid", expires_at="2030-01-01T00:00:00Z")
        id_expired = store.add_item(content="Expired", expires_at="2020-01-01T00:00:00Z")
        id_no_expiry = store.add_item(content="No expiry")
        store.close()

        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now)

        assert error is None
        assert len(items) == 2
        item_contents = [item["content"] for item in items]
        assert "Valid" in item_contents
        assert "No expiry" in item_contents
        assert "Expired" not in item_contents

    def test_load_custom_items_excludes_done_and_dismissed(self, tmp_path):
        """Test that done and dismissed items are excluded."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        id_active = store.add_item(content="Active")
        id_done = store.add_item(content="Done")
        id_dismissed = store.add_item(content="Dismissed")
        
        store.mark_done(id_done)
        store.mark_dismissed(id_dismissed)
        store.close()

        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now)

        assert error is None
        assert len(items) == 1
        assert items[0]["content"] == "Active"
        assert items[0]["status"] == "active"

    def test_load_custom_items_respects_max_items(self, tmp_path):
        """Test that max_items limit is respected."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        for i in range(15):
            store.add_item(content=f"Item {i}", priority=i)
        store.close()

        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now, max_items=5)

        assert error is None
        assert len(items) == 5
        # Should get highest priority items
        assert items[0]["priority"] == 14

    def test_load_custom_items_ordering_priority_due_created(self, tmp_path):
        """Test items are ordered by priority DESC, due_at ASC, created_at ASC."""
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        
        # Same priority, different due dates
        id1 = store.add_item(content="P5 Due Later", priority=5, due_at="2026-01-20T00:00:00Z")
        id2 = store.add_item(content="P5 Due Earlier", priority=5, due_at="2026-01-15T00:00:00Z")
        id3 = store.add_item(content="P5 No Due", priority=5)
        
        # Higher priority
        id4 = store.add_item(content="P10", priority=10)
        
        store.close()

        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now)

        assert error is None
        assert len(items) == 4
        # Order should be: P10, P5 Due Earlier, P5 Due Later, P5 No Due
        assert items[0]["content"] == "P10"
        assert items[1]["content"] == "P5 Due Earlier"
        assert items[2]["content"] == "P5 Due Later"
        assert items[3]["content"] == "P5 No Due"

    def test_load_custom_items_missing_db_returns_empty(self, tmp_path):
        """Test that missing database returns empty list without error."""
        # Don't create any store
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now)

        assert error is None
        assert items == []

    def test_load_custom_items_handles_db_error_gracefully(self, tmp_path):
        """Test that database errors are caught and reported."""
        # Create a corrupted database file
        db_path = tmp_path / "briefing.sqlite3"
        db_path.write_text("not a valid sqlite database")
        
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        items, error = _load_custom_items(tmp_path, now)

        assert items == []
        assert error is not None
        assert "store error" in error


class TestBriefingMarkdownWithCustomItems:
    """Tests for _build_markdown with custom items."""

    def test_markdown_includes_custom_items_section(self):
        """Test that custom items section appears in markdown."""
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        custom_items = [
            {"id": 1, "content": "Review PR", "priority": 1, "due_at": None},
            {"id": 2, "content": "Update docs", "priority": 0, "due_at": "2026-01-15T00:00:00Z"},
        ]

        markdown = _build_markdown(
            now=now,
            goals_today=[],
            overnight_jobs=[],
            weather=None,
            weather_error=None,
            papers=[],
            next_actions=[],
            phd_context=None,
            custom_items=custom_items,
            custom_items_error=None,
        )

        # Verify section exists
        assert "## Custom Items / Reminders" in markdown
        
        # Verify items appear
        assert "Review PR" in markdown
        assert "Update docs" in markdown
        assert "[due: 2026-01-15]" in markdown

    def test_markdown_custom_items_with_priority_formatting(self):
        """Test that priority is formatted correctly in markdown."""
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        custom_items = [
            {"id": 1, "content": "High priority", "priority": 10, "due_at": None},
            {"id": 2, "content": "Normal", "priority": 0, "due_at": None},
        ]

        markdown = _build_markdown(
            now=now,
            goals_today=[],
            overnight_jobs=[],
            weather=None,
            weather_error=None,
            papers=[],
            next_actions=[],
            custom_items=custom_items,
        )

        assert "[P10] High priority" in markdown
        assert "[P0]" not in markdown  # Priority 0 should not show tag
        assert "- Normal" in markdown

    def test_markdown_custom_items_empty_shows_placeholder(self):
        """Test that empty custom items shows 'No custom items'."""
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)

        markdown = _build_markdown(
            now=now,
            goals_today=[],
            overnight_jobs=[],
            weather=None,
            weather_error=None,
            papers=[],
            next_actions=[],
            custom_items=[],
            custom_items_error=None,
        )

        assert "## Custom Items / Reminders" in markdown
        assert "- No custom items" in markdown

    def test_markdown_custom_items_error_shows_message(self):
        """Test that custom items error is displayed."""
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)

        markdown = _build_markdown(
            now=now,
            goals_today=[],
            overnight_jobs=[],
            weather=None,
            weather_error=None,
            papers=[],
            next_actions=[],
            custom_items=[],
            custom_items_error="store error: DB locked",
        )

        assert "## Custom Items / Reminders" in markdown
        assert "Custom items unavailable (store error: DB locked)" in markdown

    def test_markdown_phd_mode_includes_custom_items_emoji(self):
        """Test that PhD mode includes emoji in custom items section."""
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        phd_context = {"overall_goal": "Complete PhD", "current_year_projects": [], "immediate_steps": []}

        markdown = _build_markdown(
            now=now,
            goals_today=[],
            overnight_jobs=[],
            weather=None,
            weather_error=None,
            papers=[],
            next_actions=[],
            phd_context=phd_context,
            custom_items=[],
        )

        assert "## 📌 Custom Items / Reminders" in markdown


class TestBriefingGeneratorIntegration:
    """Integration tests for full briefing generation with custom items."""

    def test_generate_briefing_with_custom_items(self, tmp_path):
        """Test full briefing generation includes custom items."""
        # Create store with items
        store = BriefingStore(tmp_path / "briefing.sqlite3")
        store.add_item(content="Integration test item", priority=5)
        store.close()

        # Mock weather and papers to avoid external calls
        def mock_weather():
            return {
                "location": "Test City",
                "temp": 70,
                "condition": "Clear",
                "low": 60,
                "high": 80,
                "humidity": 50,
            }

        def mock_papers(query, max_results):
            return []

        # Generate briefing
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        output_path = generate_morning_briefing(
            now=now,
            state_dir=tmp_path,
            weather_provider=mock_weather,
            papers_provider=mock_papers,
            phd_aware=False,
        )

        # Verify output file
        assert output_path.exists()
        content = output_path.read_text()

        # Verify custom items section exists
        assert "## Custom Items / Reminders" in content
        assert "Integration test item" in content
        assert "[P5]" in content

    def test_generate_briefing_no_db_degrades_gracefully(self, tmp_path):
        """Test briefing generation succeeds when no briefing.sqlite3 exists."""
        def mock_weather():
            return {
                "location": "Test City",
                "temp": 70,
                "condition": "Clear",
                "low": 60,
                "high": 80,
                "humidity": 50,
            }

        def mock_papers(query, max_results):
            return []

        # Generate briefing without creating store
        now = datetime(2026, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
        output_path = generate_morning_briefing(
            now=now,
            state_dir=tmp_path,
            weather_provider=mock_weather,
            papers_provider=mock_papers,
            phd_aware=False,
        )

        # Verify output
        assert output_path.exists()
        content = output_path.read_text()

        # Should have custom items section with "No custom items"
        assert "## Custom Items / Reminders" in content
        assert "- No custom items" in content
        # Should not crash
        assert "Morning Briefing" in content
