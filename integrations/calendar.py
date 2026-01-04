"""
Google Calendar Integration with OAuth2

Production-ready Google Calendar API integration using OAuth2 authentication.
Supports read-only access to calendar events with local token storage.

Requirements:
    pip install google-auth google-auth-oauthlib google-api-python-client

Setup:
    See docs/CALENDAR.md for detailed setup instructions.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import json
import logging

logger = logging.getLogger(__name__)

# OAuth2 scope for read-only calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# State directory for credentials
STATE_DIR = Path(os.getenv("STATE_DIR", Path.home() / ".local" / "state" / "milton"))
CREDENTIALS_DIR = STATE_DIR / "credentials"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "calendar_client_secret.json"
TOKEN_FILE = CREDENTIALS_DIR / "calendar_token.json"


class CalendarAPI:
    """
    Google Calendar API client with OAuth2 authentication.

    Features:
    - Read-only access to calendar events
    - OAuth2 authentication with local token storage
    - Automatic token refresh
    - Mock mode when credentials unavailable
    - Normalized event schema

    Example:
        calendar = CalendarAPI()
        events = calendar.get_events(days_ahead=7)
        print(calendar.format_events(events))
    """

    def __init__(self, mock_mode: bool = False):
        """
        Initialize Calendar API client.

        Args:
            mock_mode: If True, use mock data instead of real API calls
        """
        self.service = None
        self.mock_mode = mock_mode
        self._authenticated = False

        if not mock_mode:
            self._initialize_service()
        else:
            logger.info("Calendar API initialized in MOCK mode")

    def _initialize_service(self):
        """Initialize Google Calendar service with OAuth2 credentials."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None

            # Load existing token if available
            if TOKEN_FILE.exists():
                try:
                    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
                    logger.debug(f"Loaded credentials from {TOKEN_FILE}")
                except Exception as e:
                    logger.warning(f"Failed to load credentials from {TOKEN_FILE}: {e}")

            # Refresh or obtain new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    # Refresh expired token
                    try:
                        creds.refresh(Request())
                        logger.info("Refreshed expired calendar credentials")
                    except Exception as e:
                        logger.error(f"Failed to refresh credentials: {e}")
                        creds = None

                if not creds:
                    # Run OAuth2 flow to get new credentials
                    if not CLIENT_SECRET_FILE.exists():
                        logger.warning(
                            f"Calendar client secret not found at {CLIENT_SECRET_FILE}. "
                            "Running in mock mode. See docs/CALENDAR.md for setup instructions."
                        )
                        self.mock_mode = True
                        return

                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            str(CLIENT_SECRET_FILE), SCOPES
                        )
                        creds = flow.run_local_server(port=0)
                        logger.info("Obtained new calendar credentials via OAuth2 flow")
                    except Exception as e:
                        logger.error(f"OAuth2 flow failed: {e}")
                        self.mock_mode = True
                        return

                # Save credentials for future use
                if creds:
                    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
                    with TOKEN_FILE.open('w') as token_file:
                        token_file.write(creds.to_json())
                    logger.info(f"Saved credentials to {TOKEN_FILE}")

            # Build the service
            self.service = build('calendar', 'v3', credentials=creds)
            self._authenticated = True
            logger.info("Google Calendar API service initialized successfully")

        except ImportError as e:
            logger.warning(
                f"Google Calendar dependencies not installed: {e}. "
                "Install with: pip install google-auth google-auth-oauthlib google-api-python-client"
            )
            self.mock_mode = True
        except Exception as e:
            logger.error(f"Failed to initialize Calendar API: {e}", exc_info=True)
            self.mock_mode = True

    def get_events(
        self,
        days_ahead: int = 7,
        calendar_id: str = "primary",
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming calendar events.

        Args:
            days_ahead: Number of days ahead to fetch (default: 7)
            calendar_id: Calendar ID (default: "primary")
            max_results: Maximum number of events to return (default: 50)

        Returns:
            List of calendar events in normalized format:
            [
                {
                    "id": "event_id",
                    "title": "Event Title",
                    "start": "2026-01-03T10:00:00-05:00",
                    "end": "2026-01-03T11:00:00-05:00",
                    "location": "Conference Room A",
                    "description": "Event description",
                    "attendees": ["person@example.com"],
                    "is_all_day": False
                },
                ...
            ]
        """
        if self.mock_mode or not self._authenticated:
            return self._get_mock_events(days_ahead)

        try:
            # Calculate time range
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            # Call Google Calendar API
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Normalize events to Milton schema
            normalized_events = []
            for event in events:
                normalized_event = self._normalize_event(event)
                normalized_events.append(normalized_event)

            logger.info(f"Retrieved {len(normalized_events)} events from Google Calendar")
            return normalized_events

        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e}", exc_info=True)
            return []

    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Google Calendar event to Milton's internal schema.

        Args:
            event: Raw Google Calendar event

        Returns:
            Normalized event dictionary
        """
        # Extract start/end times
        start = event.get('start', {})
        end = event.get('end', {})

        # Handle all-day events vs. time-specific events
        is_all_day = 'date' in start
        start_time = start.get('date') or start.get('dateTime', '')
        end_time = end.get('date') or end.get('dateTime', '')

        # Extract attendees
        attendees = []
        for attendee in event.get('attendees', []):
            if 'email' in attendee:
                attendees.append(attendee['email'])

        return {
            "id": event.get('id', ''),
            "title": event.get('summary', 'No title'),
            "start": start_time,
            "end": end_time,
            "location": event.get('location', ''),
            "description": event.get('description', ''),
            "attendees": attendees,
            "is_all_day": is_all_day,
            "organizer": event.get('organizer', {}).get('email', ''),
            "status": event.get('status', 'confirmed'),
            "html_link": event.get('htmlLink', '')
        }

    def _get_mock_events(self, days_ahead: int) -> List[Dict[str, Any]]:
        """
        Get mock calendar events for testing without credentials.

        Args:
            days_ahead: Number of days ahead

        Returns:
            List of mock events
        """
        logger.debug(f"Returning mock calendar events (days_ahead={days_ahead})")

        now = datetime.now(timezone.utc)

        # Generate some mock events
        mock_events = [
            {
                "id": "mock_event_1",
                "title": "Team Standup",
                "start": (now + timedelta(hours=2)).isoformat(),
                "end": (now + timedelta(hours=2, minutes=30)).isoformat(),
                "location": "Zoom",
                "description": "Daily team standup meeting",
                "attendees": ["team@example.com"],
                "is_all_day": False,
                "organizer": "manager@example.com",
                "status": "confirmed",
                "html_link": ""
            },
            {
                "id": "mock_event_2",
                "title": "Lunch",
                "start": (now + timedelta(hours=5)).isoformat(),
                "end": (now + timedelta(hours=6)).isoformat(),
                "location": "",
                "description": "",
                "attendees": [],
                "is_all_day": False,
                "organizer": "",
                "status": "confirmed",
                "html_link": ""
            }
        ]

        # Filter to events within days_ahead
        cutoff = now + timedelta(days=days_ahead)
        filtered_events = [
            e for e in mock_events
            if datetime.fromisoformat(e['start'].replace('Z', '+00:00')) < cutoff
        ]

        return filtered_events

    def get_today_events(self, calendar_id: str = "primary") -> List[Dict[str, Any]]:
        """
        Get today's calendar events.

        Args:
            calendar_id: Calendar ID (default: "primary")

        Returns:
            List of today's events
        """
        return self.get_events(days_ahead=1, calendar_id=calendar_id)

    def get_this_week_events(self, calendar_id: str = "primary") -> List[Dict[str, Any]]:
        """
        Get this week's calendar events.

        Args:
            calendar_id: Calendar ID (default: "primary")

        Returns:
            List of this week's events
        """
        return self.get_events(days_ahead=7, calendar_id=calendar_id)

    def format_events(self, events: List[Dict[str, Any]]) -> str:
        """
        Format events as readable text for briefings.

        Args:
            events: List of normalized events

        Returns:
            Formatted string
        """
        if not events:
            return "No upcoming events"

        lines = []

        for event in events:
            # Parse start time
            start_str = event.get("start", "")
            try:
                if event.get("is_all_day"):
                    # All-day event: just show date
                    start_dt = datetime.fromisoformat(start_str)
                    time_str = start_dt.strftime("%a %b %d (all day)")
                else:
                    # Time-specific event: show date and time
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    time_str = start_dt.strftime("%a %b %d, %I:%M %p")
            except Exception:
                time_str = start_str

            title = event.get("title", "No title")
            location = event.get("location", "")

            # Format line
            if location:
                lines.append(f"• {time_str}: {title} @ {location}")
            else:
                lines.append(f"• {time_str}: {title}")

        return "\n".join(lines)

    def is_authenticated(self) -> bool:
        """
        Check if calendar API is authenticated and ready.

        Returns:
            True if authenticated, False otherwise
        """
        return self._authenticated and not self.mock_mode


if __name__ == "__main__":
    # Test the calendar API
    print("Testing Google Calendar API...")

    calendar = CalendarAPI()

    if calendar.is_authenticated():
        print("✅ Authenticated with Google Calendar")
    else:
        print("⚠️  Running in MOCK mode (no credentials)")

    print("\nFetching today's events...")
    events = calendar.get_today_events()

    print(f"\nFound {len(events)} events:")
    print(calendar.format_events(events))
