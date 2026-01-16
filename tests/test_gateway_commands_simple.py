"""Simplified synchronous tests for command processor."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch
import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from milton_gateway.command_processor import CommandProcessor


def test_parse_due_date_ymd():
    """Test parsing YYYY-MM-DD format."""
    processor = CommandProcessor()
    result = processor._parse_due_date("2026-01-15")
    assert result == "2026-01-15T09:00:00Z"


def test_parse_due_date_tomorrow():
    """Test parsing 'tomorrow'."""
    processor = CommandProcessor()
    result = processor._parse_due_date("tomorrow")
    assert result is not None
    assert result.endswith("T09:00:00Z")


def test_parse_due_date_day_of_week():
    """Test parsing day names like 'monday'."""
    processor = CommandProcessor()
    result = processor._parse_due_date("monday")
    assert result is not None
    assert result.endswith("T09:00:00Z")


def test_parse_due_date_invalid():
    """Test parsing invalid date returns None."""
    processor = CommandProcessor()
    result = processor._parse_due_date("not-a-date")
    assert result is None


def test_parse_hour_am_pm():
    """Test parsing hours like '9am', '2pm'."""
    processor = CommandProcessor()
    assert processor._parse_hour("9am") == 9
    assert processor._parse_hour("2pm") == 14
    assert processor._parse_hour("12pm") == 12
    assert processor._parse_hour("12am") == 0


def test_parse_hour_24h():
    """Test parsing 24-hour format."""
    processor = CommandProcessor()
    assert processor._parse_hour("14:00") == 14
    assert processor._parse_hour("9:30") == 9


def test_parse_reminder_time_relative():
    """Test parsing relative times like '+2h'."""
    from datetime import datetime, timezone
    processor = CommandProcessor()
    result = processor._parse_reminder_time("+2h")
    assert result is not None
    assert isinstance(result, int)
    # Should be approximately 2 hours from now
    now_ts = int(datetime.now(timezone.utc).timestamp())
    assert abs(result - now_ts - 7200) < 60  # Within 1 minute tolerance
