# Google Calendar Integration

**Status**: ✅ Works
**Last Updated**: 2026-01-03

---

## Overview

Milton integrates with Google Calendar using OAuth2 for read-only access to your calendar events. This integration is used in:

- **Morning briefings** (`generate_morning_briefing` in NEXUS)
- **NEXUS tools** (calendar event queries)
- **Custom scripts** (via `integrations/calendar.py`)

**Features**:
- ✅ Read-only access (no modifications to your calendar)
- ✅ OAuth2 authentication with automatic token refresh
- ✅ Local token storage in `STATE_DIR/credentials/`
- ✅ Mock mode when credentials unavailable (for testing)
- ✅ Normalized event schema across all integrations

---

## Quick Start

### 1. Install Dependencies

```bash
conda activate milton
pip install google-auth google-auth-oauthlib google-api-python-client
```

### 2. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing one)
3. Enable the **Google Calendar API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

### 3. Create OAuth2 Credentials

1. Navigate to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - User Type: **External** (for personal use)
   - App name: **Milton Calendar Integration**
   - User support email: Your email
   - Developer contact: Your email
   - Scopes: Add `https://www.googleapis.com/auth/calendar.readonly`
   - Test users: Add your Google account email
4. For application type, select **Desktop app**
5. Name it "Milton Calendar Client"
6. Click "Create"
7. Download the JSON file (it will be named something like `client_secret_XXXXX.json`)

### 4. Install Credentials

```bash
# Create credentials directory
mkdir -p ~/.local/state/milton/credentials

# Copy the downloaded JSON file
cp ~/Downloads/client_secret_*.json ~/.local/state/milton/credentials/calendar_client_secret.json

# Verify
ls -l ~/.local/state/milton/credentials/calendar_client_secret.json
```

### 5. First-Run Authentication

Run the calendar test script to complete OAuth2 flow:

```bash
cd /home/cole-hanan/milton
conda activate milton
python integrations/calendar.py
```

This will:
1. Open your browser to Google's authorization page
2. Ask you to sign in with your Google account
3. Request permission to read your calendar (read-only)
4. Save the authorization token to `~/.local/state/milton/credentials/calendar_token.json`

**You only need to do this once.** The token will be automatically refreshed when it expires.

### 6. Verify Integration

```bash
python integrations/calendar.py
```

Expected output:
```
Testing Google Calendar API...
✅ Authenticated with Google Calendar

Fetching today's events...

Found 2 events:
• Fri Jan 03, 10:00 AM: Team Standup @ Zoom
• Fri Jan 03, 02:00 PM: 1:1 with Manager
```

---

## File Locations

All calendar credentials and tokens are stored in `STATE_DIR` (default: `~/.local/state/milton`):

| File | Location | Purpose | Committed? |
|------|----------|---------|------------|
| Client Secret | `STATE_DIR/credentials/calendar_client_secret.json` | OAuth2 client credentials from Google Cloud Console | ❌ No (add to .gitignore) |
| Token | `STATE_DIR/credentials/calendar_token.json` | OAuth2 access/refresh tokens | ❌ No (auto-generated) |

**Security Note**: These files contain sensitive credentials. They are automatically excluded from version control via `.gitignore` patterns for `STATE_DIR`.

---

## OAuth2 Scopes

Milton uses the following read-only scope:

```
https://www.googleapis.com/auth/calendar.readonly
```

This scope allows:
- ✅ Read calendar events
- ✅ Read event details (title, location, attendees, etc.)
- ✅ Read calendar metadata

This scope does NOT allow:
- ❌ Creating events
- ❌ Modifying events
- ❌ Deleting events
- ❌ Changing calendar settings

---

## Usage

### Python API

```python
from integrations.calendar import CalendarAPI

# Initialize (will use OAuth2 or fall back to mock mode)
calendar = CalendarAPI()

# Get today's events
events = calendar.get_today_events()

# Get this week's events
events = calendar.get_this_week_events()

# Get custom time range
events = calendar.get_events(days_ahead=14, max_results=100)

# Format for display
formatted = calendar.format_events(events)
print(formatted)

# Check authentication status
if calendar.is_authenticated():
    print("Using real Google Calendar API")
else:
    print("Using mock mode (no credentials)")
```

### Event Schema

All events are normalized to Milton's internal schema:

```python
{
    "id": "abc123",                           # Google Calendar event ID
    "title": "Team Meeting",                  # Event summary
    "start": "2026-01-03T10:00:00-05:00",    # ISO 8601 start time
    "end": "2026-01-03T11:00:00-05:00",      # ISO 8601 end time
    "location": "Conference Room A",          # Location (optional)
    "description": "Quarterly planning",      # Description (optional)
    "attendees": ["person@example.com"],      # List of attendee emails
    "is_all_day": False,                      # True for all-day events
    "organizer": "manager@example.com",       # Organizer email
    "status": "confirmed",                    # Event status
    "html_link": "https://..."                # Link to event in Google Calendar
}
```

### Mock Mode

If credentials are not configured, the calendar API automatically falls back to **mock mode**, returning fake events for testing:

```python
from integrations.calendar import CalendarAPI

# Force mock mode
calendar = CalendarAPI(mock_mode=True)

events = calendar.get_today_events()
# Returns mock events without requiring Google credentials
```

This allows:
- Development/testing without OAuth2 setup
- CI/CD pipelines to run without credentials
- Graceful degradation when credentials unavailable

---

## Integration Points

### 1. Morning Briefings

The calendar integration is automatically used in NEXUS morning briefings:

**File**: `agents/nexus.py:606-639`

```python
def generate_morning_briefing(self) -> str:
    sections = []

    # ... weather, news ...

    # Calendar
    sections.append("\nTODAY'S SCHEDULE\n")
    try:
        events = self.calendar.get_today_events()
        if events:
            sections.append(self.calendar.format_events(events))
        else:
            sections.append("No scheduled events\n")
    except Exception as e:
        sections.append(f"Calendar unavailable: {e}\n")

    return "\n".join(sections)
```

### 2. NEXUS Tools (Future)

Calendar events can be exposed as NEXUS tools for agent queries:

```python
# Example tool definition (to be implemented)
{
    "name": "check_calendar",
    "description": "Check calendar for upcoming events",
    "parameters": {
        "days_ahead": "Number of days to look ahead (default: 7)"
    }
}
```

---

## Troubleshooting

### Error: "Client secret not found"

**Problem**: `calendar_client_secret.json` not found

**Solution**:
```bash
# Check if file exists
ls -l ~/.local/state/milton/credentials/calendar_client_secret.json

# If missing, download from Google Cloud Console and copy
cp ~/Downloads/client_secret_*.json ~/.local/state/milton/credentials/calendar_client_secret.json
```

### Error: "The OAuth consent screen is not configured"

**Problem**: OAuth consent screen not set up in Google Cloud Console

**Solution**:
1. Go to Google Cloud Console > APIs & Services > OAuth consent screen
2. Fill out required fields (app name, user email, developer email)
3. Add test users (your Google account email)
4. Save

### Error: "Token has expired and refresh failed"

**Problem**: Refresh token is invalid or revoked

**Solution**:
```bash
# Delete the token file
rm ~/.local/state/milton/credentials/calendar_token.json

# Re-run authentication
python integrations/calendar.py
```

This will trigger a new OAuth2 flow.

### Error: "ImportError: No module named 'google'"

**Problem**: Google API libraries not installed

**Solution**:
```bash
conda activate milton
pip install google-auth google-auth-oauthlib google-api-python-client
```

### Warning: "Running in MOCK mode"

**Expected behavior** when:
- Client secret file doesn't exist
- OAuth2 flow hasn't been completed
- Google API libraries not installed

**To enable real calendar access**: Follow the setup steps above.

---

## Security Best Practices

### Credentials Storage

- ✅ **DO**: Store credentials in `STATE_DIR/credentials/` (excluded from git)
- ❌ **DON'T**: Commit credentials to version control
- ❌ **DON'T**: Share credentials in chat logs or screenshots

### Token Refresh

- Tokens are automatically refreshed when expired
- Refresh tokens are long-lived (typically valid for months)
- If refresh fails, user will be prompted to re-authenticate

### Scope Limitations

- Milton uses **read-only** scope only
- Even if credentials are compromised, attacker cannot modify calendar
- Consider using a dedicated Google account for Milton integration

### Revocation

To revoke Milton's access to your calendar:

1. Go to [Google Account Settings](https://myaccount.google.com/permissions)
2. Find "Milton Calendar Integration"
3. Click "Remove Access"
4. Delete local token: `rm ~/.local/state/milton/credentials/calendar_token.json`

---

## Advanced Configuration

### Custom State Directory

If using a custom `STATE_DIR`:

```bash
export STATE_DIR=/custom/path/to/state
mkdir -p $STATE_DIR/credentials
cp client_secret.json $STATE_DIR/credentials/calendar_client_secret.json
```

### Multiple Calendars

To access calendars other than "primary":

```python
calendar = CalendarAPI()

# Get events from specific calendar
events = calendar.get_events(
    days_ahead=7,
    calendar_id="user@example.com"  # Calendar ID
)
```

To find calendar IDs:
1. Go to Google Calendar settings
2. Click on the calendar you want
3. Scroll to "Integrate calendar"
4. Copy the "Calendar ID"

### Programmatic OAuth (Headless Servers)

For headless servers without browser access, use service account credentials instead:

**Not recommended for single-user Milton installations.** Service accounts require domain-wide delegation and are more complex to set up.

---

## Testing

### Unit Tests

Run calendar integration tests:

```bash
pytest tests/test_calendar.py -v
```

Tests use mocked Google API responses (no real credentials needed).

### Manual Testing

```bash
# Test in mock mode
python -c "from integrations.calendar import CalendarAPI; c = CalendarAPI(mock_mode=True); print(c.format_events(c.get_today_events()))"

# Test with real credentials
python integrations/calendar.py
```

---

## Changelog

**2026-01-03**: Initial production implementation
- OAuth2 authentication with read-only scope
- Automatic token refresh
- Mock mode for testing
- Integration with NEXUS morning briefings

---

## References

- [Google Calendar API Documentation](https://developers.google.com/calendar/api/v3/reference)
- [Google OAuth2 Python Guide](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google API Python Client](https://github.com/googleapis/google-api-python-client)

---

**Questions?** See `integrations/calendar.py` source code or check the troubleshooting section above.
