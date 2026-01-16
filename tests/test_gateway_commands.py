"""Tests for Milton Gateway command processor.

Tests cover:
1. Command parsing and detection
2. API call payloads
3. Error handling
4. Date/time parsing
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock

import httpx
import pytest
import anyio

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from milton_gateway.command_processor import CommandProcessor, CommandResult


@pytest.mark.asyncio
class TestCommandDetection:
    """Test command detection and non-command passthrough."""

    async def test_non_command_passthrough(self):
        """Test that regular messages are not treated as commands."""
        processor = CommandProcessor()
        
        result = await processor.process_message("Hello, how are you?")
        assert result.is_command is False
        assert result.response is None
        assert result.error is None
        
        await processor.close()

    async def test_briefing_command_detected(self):
        """Test that /briefing commands are detected."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 1, "status": "active"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/briefing add Test item")
            assert result.is_command is True
        
        await processor.close()

    async def test_reminder_command_detected(self):
        """Test that /reminder commands are detected."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 1, "status": "scheduled"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/reminder add Test | at:+2h")
            assert result.is_command is True
        
        await processor.close()


@pytest.mark.asyncio
class TestBriefingAddCommand:
    """Test /briefing add command with various options."""

    async def test_briefing_add_simple(self):
        """Test simple briefing add without options."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 1, "status": "active", "created_at": "2026-01-12T18:00:00Z"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/briefing add Review code")
            
            # Verify command was recognized
            assert result.is_command is True
            assert result.error is None
            assert "Review code" in result.response
            assert "✅" in result.response
            
            # Verify API call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://localhost:8001/api/briefing/items"
            payload = call_args[1]["json"]
            assert payload["content"] == "Review code"
            assert payload["priority"] == 0
            assert payload["source"] == "interactive-chat"
            assert "due_at" not in payload
        
        await processor.close()

    async def test_briefing_add_with_priority(self):
        """Test briefing add with priority."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 2, "status": "active"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/briefing add Urgent task | priority:10")
            
            assert result.is_command is True
            assert result.error is None
            assert "[P10]" in result.response
            assert "Urgent task" in result.response
            
            # Verify API payload
            payload = mock_post.call_args[1]["json"]
            assert payload["content"] == "Urgent task"
            assert payload["priority"] == 10
        
        await processor.close()

    async def test_briefing_add_with_due_date(self):
        """Test briefing add with due date."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 3, "status": "active"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/briefing add Call dentist | due:2026-01-15")
            
            assert result.is_command is True
            assert result.error is None
            assert "due: 2026-01-15" in result.response
            
            # Verify API payload
            payload = mock_post.call_args[1]["json"]
            assert payload["content"] == "Call dentist"
            assert payload["due_at"] == "2026-01-15T09:00:00Z"
        
        await processor.close()

    async def test_briefing_add_with_priority_and_due(self):
        """Test briefing add with both priority and due date."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 4, "status": "active"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/briefing add Important meeting | priority:8 | due:tomorrow")
            
            assert result.is_command is True
            assert result.error is None
            assert "[P8]" in result.response
            
            # Verify API payload
            payload = mock_post.call_args[1]["json"]
            assert payload["content"] == "Important meeting"
            assert payload["priority"] == 8
            assert "due_at" in payload
            assert payload["due_at"].endswith("T09:00:00Z")
        
        await processor.close()

    async def test_briefing_add_empty_content(self):
        """Test briefing add with empty content returns error."""
        processor = CommandProcessor()
        
        result = await processor.process_message("/briefing add ")
        
        assert result.is_command is True
        assert result.error is not None
        assert "Usage" in result.error
        
        await processor.close()

    async def test_briefing_add_api_error(self):
        """Test briefing add handles API errors gracefully."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.side_effect = httpx.HTTPStatusError(
                "400 Bad Request",
                request=Mock(),
                response=mock_response
            )
            
            result = await processor.process_message("/briefing add Test")
            
            assert result.is_command is True
            assert result.error is not None
            assert "400" in result.error
        
        await processor.close()


@pytest.mark.asyncio
class TestBriefingListCommand:
    """Test /briefing list command."""

    async def test_briefing_list_with_items(self):
        """Test listing briefing items."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "count": 2,
                "items": [
                    {"id": 1, "content": "Item 1", "priority": 10, "due_at": "2026-01-15T09:00:00Z"},
                    {"id": 2, "content": "Item 2", "priority": 0, "due_at": None},
                ]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = await processor.process_message("/briefing list")
            
            assert result.is_command is True
            assert result.error is None
            assert "Item 1" in result.response
            assert "Item 2" in result.response
            assert "[P10]" in result.response
            assert "📋" in result.response
        
        await processor.close()

    async def test_briefing_list_empty(self):
        """Test listing when no items exist."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"count": 0, "items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = await processor.process_message("/briefing list")
            
            assert result.is_command is True
            assert result.error is None
            assert "No active briefing items" in result.response
        
        await processor.close()


class TestDateParsing:
    """Test date/time parsing helpers."""

    def test_parse_due_date_ymd(self):
        """Test parsing YYYY-MM-DD format."""
        processor = CommandProcessor()
        
        result = processor._parse_due_date("2026-01-15")
        assert result == "2026-01-15T09:00:00Z"

    def test_parse_due_date_tomorrow(self):
        """Test parsing 'tomorrow'."""
        processor = CommandProcessor()
        
        result = processor._parse_due_date("tomorrow")
        assert result is not None
        assert result.endswith("T09:00:00Z")
        
        # Verify it's actually tomorrow
        parsed_date = result[:10]
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = tomorrow.replace(day=tomorrow.day + 1)
        assert parsed_date == tomorrow.strftime("%Y-%m-%d")

    def test_parse_due_date_day_of_week(self):
        """Test parsing day names like 'monday'."""
        processor = CommandProcessor()
        
        result = processor._parse_due_date("monday")
        assert result is not None
        assert result.endswith("T09:00:00Z")

    def test_parse_due_date_invalid(self):
        """Test parsing invalid date returns None."""
        processor = CommandProcessor()
        
        result = processor._parse_due_date("not-a-date")
        assert result is None

    def test_parse_hour_am_pm(self):
        """Test parsing hours like '9am', '2pm'."""
        processor = CommandProcessor()
        
        assert processor._parse_hour("9am") == 9
        assert processor._parse_hour("2pm") == 14
        assert processor._parse_hour("12pm") == 12
        assert processor._parse_hour("12am") == 0

    def test_parse_hour_24h(self):
        """Test parsing 24-hour format."""
        processor = CommandProcessor()
        
        assert processor._parse_hour("14:00") == 14
        assert processor._parse_hour("9:30") == 9

    def test_parse_reminder_time_relative(self):
        """Test parsing relative times like '+2h'."""
        processor = CommandProcessor()
        
        result = processor._parse_reminder_time("+2h")
        assert result is not None
        assert isinstance(result, int)
        
        # Should be approximately 2 hours from now
        now_ts = int(datetime.now(timezone.utc).timestamp())
        assert abs(result - now_ts - 7200) < 60  # Within 1 minute tolerance


@pytest.mark.asyncio
class TestReminderCommands:
    """Test reminder commands."""

    
    async def test_reminder_add_simple(self):
        """Test adding a reminder."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 1, "status": "scheduled"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = await processor.process_message("/reminder add Check email | at:+1h")
            
            assert result.is_command is True
            assert result.error is None
            assert "Check email" in result.response
            assert "⏰" in result.response
            
            # Verify API call
            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            assert payload["message"] == "Check email"
            assert isinstance(payload["remind_at"], int)
        
        await processor.close()

    
    async def test_reminder_list(self):
        """Test listing reminders."""
        processor = CommandProcessor()
        
        with patch.object(processor.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "count": 1,
                "reminders": [
                    {"id": 1, "message": "Test reminder", "remind_at": 1736928000}
                ]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = await processor.process_message("/reminder list")
            
            assert result.is_command is True
            assert result.error is None
            assert "Test reminder" in result.response
        
        await processor.close()


@pytest.mark.asyncio
class TestInvalidCommands:
    """Test error handling for invalid commands."""

    
    async def test_briefing_unknown_subcommand(self):
        """Test unknown briefing subcommand."""
        processor = CommandProcessor()
        
        result = await processor.process_message("/briefing delete 123")
        
        assert result.is_command is True
        assert result.error is not None
        assert "Unknown" in result.error
        
        await processor.close()

    
    async def test_reminder_missing_time(self):
        """Test reminder without time."""
        processor = CommandProcessor()
        
        result = await processor.process_message("/reminder add Do something")
        
        assert result.is_command is True
        assert result.error is not None
        assert "time required" in result.error.lower()
        
        await processor.close()
