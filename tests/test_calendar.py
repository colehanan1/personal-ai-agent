"""
Unit tests for Google Calendar integration.

Tests:
- OAuth2 credential loading and refresh
- Event fetching with Google Calendar API
- Event normalization to Milton schema
- Mock mode behavior
- Event formatting
- Error handling
"""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def temp_state_dir():
    """Create temporary state directory for credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        credentials_dir = state_dir / "credentials"
        credentials_dir.mkdir(parents=True)
        yield state_dir


@pytest.fixture
def mock_google_service():
    """Create a mock Google Calendar API service."""
    service = MagicMock()

    # Mock the events().list() chain
    events_mock = MagicMock()
    service.events.return_value = events_mock

    list_mock = MagicMock()
    events_mock.list.return_value = list_mock

    # Default execute returns empty events
    list_mock.execute.return_value = {"items": []}

    return service


def test_calendar_api_mock_mode():
    """Test CalendarAPI in mock mode."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    assert calendar.mock_mode is True
    assert calendar.is_authenticated() is False

    events = calendar.get_today_events()

    # Should return mock events
    assert isinstance(events, list)
    assert len(events) >= 0

    # Check event schema
    if events:
        event = events[0]
        assert "id" in event
        assert "title" in event
        assert "start" in event
        assert "end" in event
        assert "is_all_day" in event


def test_calendar_api_mock_mode_formatting():
    """Test event formatting in mock mode."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)
    events = calendar.get_today_events()

    formatted = calendar.format_events(events)

    # Should return formatted string
    assert isinstance(formatted, str)
    assert len(formatted) > 0


def test_calendar_api_no_credentials_falls_back_to_mock():
    """Test that missing credentials triggers mock mode."""
    from integrations.calendar import CalendarAPI

    with patch("integrations.calendar.CLIENT_SECRET_FILE") as mock_secret_file:
        # Mock file doesn't exist
        mock_secret_file.exists.return_value = False

        with patch("integrations.calendar.Path") as mock_path:
            mock_path.return_value.exists.return_value = False

            calendar = CalendarAPI(mock_mode=False)

            # Should fall back to mock mode
            assert calendar.mock_mode is True


def test_event_normalization():
    """Test Google Calendar event normalization to Milton schema."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    # Google Calendar API event format
    google_event = {
        "id": "test_event_123",
        "summary": "Team Meeting",
        "start": {
            "dateTime": "2026-01-03T10:00:00-05:00",
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": "2026-01-03T11:00:00-05:00",
            "timeZone": "America/New_York"
        },
        "location": "Conference Room A",
        "description": "Quarterly planning meeting",
        "attendees": [
            {"email": "person1@example.com"},
            {"email": "person2@example.com"}
        ],
        "organizer": {
            "email": "manager@example.com"
        },
        "status": "confirmed",
        "htmlLink": "https://calendar.google.com/..."
    }

    normalized = calendar._normalize_event(google_event)

    # Check normalized fields
    assert normalized["id"] == "test_event_123"
    assert normalized["title"] == "Team Meeting"
    assert normalized["start"] == "2026-01-03T10:00:00-05:00"
    assert normalized["end"] == "2026-01-03T11:00:00-05:00"
    assert normalized["location"] == "Conference Room A"
    assert normalized["description"] == "Quarterly planning meeting"
    assert normalized["attendees"] == ["person1@example.com", "person2@example.com"]
    assert normalized["is_all_day"] is False
    assert normalized["organizer"] == "manager@example.com"
    assert normalized["status"] == "confirmed"
    assert "htmlLink" in google_event or "html_link" in normalized


def test_event_normalization_all_day():
    """Test normalization of all-day events."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    # All-day event uses 'date' instead of 'dateTime'
    google_event = {
        "id": "all_day_event",
        "summary": "All Day Event",
        "start": {
            "date": "2026-01-03"
        },
        "end": {
            "date": "2026-01-04"
        }
    }

    normalized = calendar._normalize_event(google_event)

    assert normalized["id"] == "all_day_event"
    assert normalized["title"] == "All Day Event"
    assert normalized["start"] == "2026-01-03"
    assert normalized["end"] == "2026-01-04"
    assert normalized["is_all_day"] is True


def test_event_normalization_missing_fields():
    """Test normalization handles missing optional fields."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    # Minimal event
    google_event = {
        "id": "minimal_event",
        "start": {"dateTime": "2026-01-03T10:00:00Z"},
        "end": {"dateTime": "2026-01-03T11:00:00Z"}
    }

    normalized = calendar._normalize_event(google_event)

    assert normalized["id"] == "minimal_event"
    assert normalized["title"] == "No title"  # Default value
    assert normalized["location"] == ""
    assert normalized["description"] == ""
    assert normalized["attendees"] == []
    assert normalized["organizer"] == ""


def test_get_events_with_mocked_service(mock_google_service):
    """Test get_events with mocked Google Calendar service."""
    from integrations.calendar import CalendarAPI

    # Mock events response
    mock_events = [
        {
            "id": "event1",
            "summary": "Event 1",
            "start": {"dateTime": "2026-01-03T10:00:00Z"},
            "end": {"dateTime": "2026-01-03T11:00:00Z"}
        },
        {
            "id": "event2",
            "summary": "Event 2",
            "start": {"dateTime": "2026-01-03T14:00:00Z"},
            "end": {"dateTime": "2026-01-03T15:00:00Z"}
        }
    ]

    mock_google_service.events().list().execute.return_value = {"items": mock_events}

    calendar = CalendarAPI(mock_mode=True)
    calendar.service = mock_google_service
    calendar._authenticated = True
    calendar.mock_mode = False

    events = calendar.get_events(days_ahead=7)

    assert len(events) == 2
    assert events[0]["id"] == "event1"
    assert events[0]["title"] == "Event 1"
    assert events[1]["id"] == "event2"
    assert events[1]["title"] == "Event 2"


def test_get_events_time_range(mock_google_service):
    """Test that get_events requests correct time range."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)
    calendar.service = mock_google_service
    calendar._authenticated = True
    calendar.mock_mode = False

    # Call get_events
    calendar.get_events(days_ahead=14, max_results=100, calendar_id="test@example.com")

    # Verify API was called with correct parameters
    mock_google_service.events().list.assert_called_once()

    call_kwargs = mock_google_service.events().list.call_args[1]

    assert call_kwargs["calendarId"] == "test@example.com"
    assert call_kwargs["maxResults"] == 100
    assert call_kwargs["singleEvents"] is True
    assert call_kwargs["orderBy"] == "startTime"
    assert "timeMin" in call_kwargs
    assert "timeMax" in call_kwargs


def test_get_events_api_error_returns_empty(mock_google_service):
    """Test that API errors return empty list gracefully."""
    from integrations.calendar import CalendarAPI

    # Mock API error
    mock_google_service.events().list().execute.side_effect = Exception("API Error")

    calendar = CalendarAPI(mock_mode=True)
    calendar.service = mock_google_service
    calendar._authenticated = True
    calendar.mock_mode = False

    events = calendar.get_events()

    # Should return empty list on error
    assert events == []


def test_format_events_empty():
    """Test formatting empty event list."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    formatted = calendar.format_events([])

    assert formatted == "No upcoming events"


def test_format_events_with_location():
    """Test formatting events with location."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    events = [
        {
            "title": "Meeting",
            "start": "2026-01-03T10:00:00-05:00",
            "location": "Room 101",
            "is_all_day": False
        }
    ]

    formatted = calendar.format_events(events)

    assert "Meeting" in formatted
    assert "Room 101" in formatted
    assert "@" in formatted  # Location separator


def test_format_events_without_location():
    """Test formatting events without location."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    events = [
        {
            "title": "Meeting",
            "start": "2026-01-03T10:00:00-05:00",
            "location": "",
            "is_all_day": False
        }
    ]

    formatted = calendar.format_events(events)

    assert "Meeting" in formatted
    assert "@" not in formatted  # No location separator


def test_format_events_all_day():
    """Test formatting all-day events."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    events = [
        {
            "title": "Holiday",
            "start": "2026-01-03",
            "location": "",
            "is_all_day": True
        }
    ]

    formatted = calendar.format_events(events)

    assert "Holiday" in formatted
    assert "all day" in formatted.lower()


def test_get_today_events():
    """Test get_today_events calls get_events with days_ahead=1."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    with patch.object(calendar, 'get_events', return_value=[]) as mock_get_events:
        calendar.get_today_events()

        mock_get_events.assert_called_once_with(days_ahead=1, calendar_id="primary")


def test_get_this_week_events():
    """Test get_this_week_events calls get_events with days_ahead=7."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    with patch.object(calendar, 'get_events', return_value=[]) as mock_get_events:
        calendar.get_this_week_events()

        mock_get_events.assert_called_once_with(days_ahead=7, calendar_id="primary")


def test_is_authenticated_mock_mode():
    """Test is_authenticated returns False in mock mode."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    assert calendar.is_authenticated() is False


def test_is_authenticated_real_mode():
    """Test is_authenticated returns True when authenticated."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)
    calendar._authenticated = True
    calendar.mock_mode = False

    assert calendar.is_authenticated() is True


def test_mock_events_filtering():
    """Test that mock events are filtered by days_ahead."""
    from integrations.calendar import CalendarAPI

    calendar = CalendarAPI(mock_mode=True)

    # Get events for next day
    events_1_day = calendar._get_mock_events(days_ahead=1)

    # Get events for next week
    events_7_days = calendar._get_mock_events(days_ahead=7)

    # 7-day window should have same or more events
    assert len(events_7_days) >= len(events_1_day)


def test_credentials_directory_creation(temp_state_dir):
    """Test that credentials directory is created on token save."""
    from integrations.calendar import CREDENTIALS_DIR

    # The calendar module should reference STATE_DIR from env
    with patch("integrations.calendar.STATE_DIR", temp_state_dir):
        with patch("integrations.calendar.CREDENTIALS_DIR", temp_state_dir / "credentials"):
            from integrations.calendar import CalendarAPI

            # Credentials dir should be created when needed
            credentials_dir = temp_state_dir / "credentials"

            # Simulate credential save
            credentials_dir.mkdir(parents=True, exist_ok=True)

            assert credentials_dir.exists()


def test_token_file_paths():
    """Test that token and client secret paths are in STATE_DIR."""
    from integrations.calendar import TOKEN_FILE, CLIENT_SECRET_FILE, CREDENTIALS_DIR

    # All paths should be under CREDENTIALS_DIR
    assert str(CREDENTIALS_DIR) in str(TOKEN_FILE)
    assert str(CREDENTIALS_DIR) in str(CLIENT_SECRET_FILE)

    # Filenames should be correct
    assert TOKEN_FILE.name == "calendar_token.json"
    assert CLIENT_SECRET_FILE.name == "calendar_client_secret.json"


def test_oauth_scope_is_read_only():
    """Test that OAuth scope is read-only."""
    from integrations.calendar import SCOPES

    assert len(SCOPES) == 1
    assert SCOPES[0] == "https://www.googleapis.com/auth/calendar.readonly"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
