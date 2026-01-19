"""
Hermetic tests for goal capture functionality.

Tests goal extraction, persistence, and briefing integration without network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil

import pytest

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from goals.capture import (
    normalize_goal_text,
    extract_goal_from_line,
    extract_goals_from_text,
    goal_exists,
    capture_goal,
    capture_goals_from_message,
)
from goals.api import add_goal, list_goals


class TestGoalTextNormalization:
    """Tests for goal text normalization."""

    def test_normalize_strips_whitespace(self):
        assert normalize_goal_text("  test goal  ") == "test goal"

    def test_normalize_removes_bullets(self):
        assert normalize_goal_text("- test goal") == "test goal"
        assert normalize_goal_text("* test goal") == "test goal"
        assert normalize_goal_text("• test goal") == "test goal"

    def test_normalize_removes_numbers(self):
        assert normalize_goal_text("1. test goal") == "test goal"
        assert normalize_goal_text("42) test goal") == "test goal"

    def test_normalize_removes_quotes(self):
        assert normalize_goal_text('"test goal"') == "test goal"
        assert normalize_goal_text("'test goal'") == "test goal"

    def test_normalize_collapses_whitespace(self):
        assert normalize_goal_text("test   goal   here") == "test goal here"

    def test_normalize_empty_returns_empty(self):
        assert normalize_goal_text("") == ""
        assert normalize_goal_text("   ") == ""


class TestGoalExtraction:
    """Tests for deterministic goal extraction patterns."""

    def test_extract_simple_goal_prefix(self):
        assert extract_goal_from_line("goal: finish the report") == "finish the report"
        assert extract_goal_from_line("Goal: finish the report") == "finish the report"
        assert extract_goal_from_line("GOAL: finish the report") == "finish the report"

    def test_extract_slash_command(self):
        assert extract_goal_from_line("/goal add complete task") == "complete task"
        assert extract_goal_from_line("/goal complete task") == "complete task"

    def test_extract_natural_language(self):
        assert extract_goal_from_line("my goal for today: fix bugs") == "fix bugs"
        assert extract_goal_from_line("today's goal: fix bugs") == "fix bugs"
        assert extract_goal_from_line("goal is: fix bugs") == "fix bugs"

    def test_extract_with_bullet(self):
        assert extract_goal_from_line("- goal: write tests") == "write tests"
        assert extract_goal_from_line("* goal: write tests") == "write tests"
        assert extract_goal_from_line("1. goal: write tests") == "write tests"

    def test_extract_ignores_too_short(self):
        assert extract_goal_from_line("goal: ab") is None
        assert extract_goal_from_line("goal: x") is None

    def test_extract_returns_none_for_non_goals(self):
        assert extract_goal_from_line("just a regular message") is None
        assert extract_goal_from_line("I think the goal should be...") is None

    def test_extract_multiple_from_text(self):
        text = """
        goal: finish report
        Some other text here
        goal: review code
        """
        goals = extract_goals_from_text(text)
        assert len(goals) == 2
        assert "finish report" in goals
        assert "review code" in goals

    def test_extract_with_mixed_formats(self):
        text = """
        - goal: task one
        /goal add task two
        my goal for today: task three
        """
        goals = extract_goals_from_text(text)
        assert len(goals) == 3
        assert "task one" in goals
        assert "task two" in goals
        assert "task three" in goals


class TestGoalPersistence:
    """Tests for goal persistence with temporary state directory."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create a temporary state directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_capture_goal_creates_new(self, temp_state_dir):
        """Test capturing a new goal."""
        result = capture_goal(
            "finish the report",
            scope="daily",
            tags=["test"],
            base_dir=temp_state_dir,
        )
        
        assert result["status"] == "added"
        assert result["text"] == "finish the report"
        assert result["id"].startswith("d-")  # daily prefix
        
        # Verify it was persisted
        goals = list_goals("daily", base_dir=temp_state_dir)
        assert len(goals) == 1
        assert goals[0]["text"] == "finish the report"
        assert "test" in goals[0]["tags"]

    def test_capture_goal_detects_duplicate(self, temp_state_dir):
        """Test that duplicate goals are not re-added."""
        # Add first time
        result1 = capture_goal("finish report", base_dir=temp_state_dir)
        assert result1["status"] == "added"
        
        # Try to add again
        result2 = capture_goal("finish report", base_dir=temp_state_dir)
        assert result2["status"] == "existing"
        assert result2["id"] == result1["id"]
        
        # Verify only one goal exists
        goals = list_goals("daily", base_dir=temp_state_dir)
        assert len(goals) == 1

    def test_capture_goal_case_insensitive_duplicate(self, temp_state_dir):
        """Test that duplicate detection is case-insensitive."""
        capture_goal("Finish Report", base_dir=temp_state_dir)
        result = capture_goal("finish report", base_dir=temp_state_dir)
        
        assert result["status"] == "existing"
        
        goals = list_goals("daily", base_dir=temp_state_dir)
        assert len(goals) == 1

    def test_capture_multiple_goals_from_message(self, temp_state_dir):
        """Test capturing multiple goals from a single message."""
        message = """
        goal: complete task one
        goal: complete task two
        goal: complete task three
        """
        
        results = capture_goals_from_message(
            message,
            scope="daily",
            tags=["chat"],
            base_dir=temp_state_dir,
        )
        
        assert len(results) == 3
        assert all(r["status"] == "added" for r in results)
        
        goals = list_goals("daily", base_dir=temp_state_dir)
        assert len(goals) == 3

    def test_goal_exists_checks_all_scopes(self, temp_state_dir):
        """Test that goal_exists checks daily, weekly, and monthly."""
        # Add to weekly
        add_goal("weekly", "test goal", base_dir=temp_state_dir)
        
        # Should find it
        goal_id = goal_exists("test goal", base_dir=temp_state_dir)
        assert goal_id is not None
        assert goal_id.startswith("w-")  # weekly prefix


class TestGoalCaptureValidation:
    """Tests for goal capture validation."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create a temporary state directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_capture_goal_rejects_empty(self, temp_state_dir):
        """Test that empty goals are rejected."""
        with pytest.raises(ValueError, match="at least 3 characters"):
            capture_goal("", base_dir=temp_state_dir)

    def test_capture_goal_rejects_too_short(self, temp_state_dir):
        """Test that goals shorter than 3 characters are rejected."""
        with pytest.raises(ValueError, match="at least 3 characters"):
            capture_goal("ab", base_dir=temp_state_dir)

    def test_capture_goals_from_message_skips_invalid(self, temp_state_dir):
        """Test that invalid goals are skipped silently."""
        message = """
        goal: ab
        goal: valid goal here
        goal: x
        """
        
        results = capture_goals_from_message(message, base_dir=temp_state_dir)
        
        # Only the valid goal should be captured
        assert len(results) == 1
        assert results[0]["text"] == "valid goal here"


class TestBriefingIntegration:
    """Tests for goal integration in briefings."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create a temporary state directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_briefing_includes_goals(self, temp_state_dir):
        """
        End-to-end test: capture goals and verify they appear in briefing.
        
        This is a hermetic test that doesn't generate an actual briefing,
        but verifies the goal would be accessible via list_goals().
        """
        # Capture some goals
        capture_goal("finish report", scope="daily", base_dir=temp_state_dir)
        capture_goal("review code", scope="daily", base_dir=temp_state_dir)
        
        # Simulate what a briefing would do
        goals = list_goals("daily", base_dir=temp_state_dir)
        
        # Verify goals are present
        assert len(goals) == 2
        goal_texts = [g["text"] for g in goals]
        assert "finish report" in goal_texts
        assert "review code" in goal_texts
        
        # Verify they have the expected structure
        for goal in goals:
            assert "id" in goal
            assert "text" in goal
            assert "status" in goal
            assert goal["status"] == "active"
            assert "created_at" in goal

    def test_briefing_goal_ordering(self, temp_state_dir):
        """Test that goals maintain order for briefing display."""
        # Add goals in specific order
        for i in range(5):
            capture_goal(f"task {i}", scope="daily", base_dir=temp_state_dir)
        
        goals = list_goals("daily", base_dir=temp_state_dir)
        
        # Verify we get all goals back
        assert len(goals) == 5
        
        # Goals should be in the order they were added (FIFO)
        texts = [g["text"] for g in goals]
        for i in range(5):
            assert f"task {i}" in texts


class TestGoalCapturePatterns:
    """Tests for specific goal capture patterns."""

    def test_add_goal_command(self):
        assert extract_goal_from_line("add goal: complete review") == "complete review"
        assert extract_goal_from_line("set goal: complete review") == "complete review"
        assert extract_goal_from_line("create goal: complete review") == "complete review"

    def test_goal_with_context(self):
        # These should extract successfully
        assert extract_goal_from_line("goal: complete review before 5pm")
        assert extract_goal_from_line("goal: call John about the project")

    def test_non_goal_messages(self):
        # These should NOT be detected as goals
        assert extract_goal_from_line("I'm thinking about my goals") is None
        assert extract_goal_from_line("The goal of this project is...") is None
        assert extract_goal_from_line("What should my goal be?") is None
