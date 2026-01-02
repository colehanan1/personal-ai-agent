# Milton Reminders System

Complete guide to Milton's persistent reminder and notification system.

## Overview

Milton's Reminders system provides first-class support for creating, managing, and delivering time-based notifications via ntfy. Unlike simple suggestion systems, Milton **actually stores reminders** and **sends push notifications** at the correct time.

### Key Features

- ✅ **Persistent storage**: SQLite database survives restarts
- ✅ **Real scheduling**: Reminders trigger at the exact time in your timezone (America/New_York by default)
- ✅ **Push notifications**: Sends via ntfy to your iOS/Android device
- ✅ **Natural language**: "remind me to call Bob tomorrow at 9am", "in 2 hours", etc.
- ✅ **Retry logic**: Automatic retries with exponential backoff for failed deliveries
- ✅ **Safe behavior**: Never claims a reminder is set unless it's persisted and scheduled
- ✅ **Multiple interfaces**: CLI, NEXUS agent tool, and orchestrator integration

## Prerequisites

1. **Python dependencies**:
   ```bash
   pip install dateparser pytz
   ```

2. **ntfy topic** (for notifications):
   - Create a topic at https://ntfy.sh (or use self-hosted server)
   - Install ntfy app on your phone
   - Subscribe to your topic in the app

3. **Environment setup**:
   ```bash
   export NTFY_TOPIC=your-unique-topic-name
   export NTFY_BASE_URL=https://ntfy.sh  # Optional, defaults to ntfy.sh
   export TZ=America/New_York  # Optional, your timezone
   ```

## Quick Start

### 1. Install Dependencies

```bash
cd /home/cole-hanan/milton
conda activate milton
pip install -r requirements.txt
```

### 2. Set Up ntfy

**On iOS:**
1. Install ntfy app from App Store
2. Tap + to add subscription
3. Enter your topic name (e.g., `milton-reminders-cole`)
4. Enable notifications

**Configure Milton:**
```bash
export NTFY_TOPIC=milton-reminders-cole
```

### 3. Start the Reminder Scheduler

In one terminal:
```bash
milton-reminders run --verbose
```

This runs the scheduler daemon that monitors for due reminders and sends notifications.

### 4. Create Reminders

**Using CLI:**
```bash
# In another terminal
milton-reminders add "Buy toothbrush" --when "tomorrow at 9am"
milton-reminders add "Team meeting" --when "in 2 hours"
milton-reminders add "Call dentist" --when "2026-01-15 14:30"
```

**Using NEXUS (conversational):**
```bash
# Talk to NEXUS
"remind me to take a break in 30 minutes"
"remind me to call Bob tomorrow at 2pm"
"list my reminders"
"cancel reminder 3"
```

**Via ntfy (from your phone):**
```bash
# Send to your ASK_TOPIC (if orchestrator is running)
REMIND: in 1h | Check the oven
```

## Command Reference

### `milton-reminders` CLI

#### Add a Reminder

```bash
milton-reminders add MESSAGE --when TIME_EXPRESSION [OPTIONS]

# Examples:
milton-reminders add "Standup meeting" --when "tomorrow at 9am"
milton-reminders add "Check build" --when "in 30 minutes"
milton-reminders add "Quarterly review" --when "2026-04-01 10:00" --kind ALARM

# Options:
--when, -w        Time expression (REQUIRED)
--kind, -k        Reminder kind (default: REMIND)
--target, -t      Delivery target (optional)
--timezone, -z    Timezone (default: from TZ env)
--json            Output JSON
```

#### List Reminders

```bash
milton-reminders list [OPTIONS]

# Examples:
milton-reminders list
milton-reminders list --all      # Include sent/canceled
milton-reminders list --verbose  # Show error details
milton-reminders list --json     # JSON output

# Options:
--all, -a         Include sent and canceled reminders
--verbose, -v     Show error details
--json            Output JSON
```

#### Cancel a Reminder

```bash
milton-reminders cancel ID [--json]

# Examples:
milton-reminders cancel 42
milton-reminders cancel 7 --json
```

#### Run the Scheduler

```bash
milton-reminders run [OPTIONS]

# Examples:
milton-reminders run
milton-reminders run --verbose
milton-reminders run --interval 10 --max-retries 5

# Options:
--interval, -i       Check interval in seconds (default: 5)
--max-retries        Max retry attempts (default: 3)
--retry-backoff      Retry backoff in seconds (default: 60)
--verbose, -v        Verbose logging
```

## Time Expression Formats

Milton supports multiple time formats:

### Relative Times
- `in 10m`, `in 10 minutes`
- `in 2h`, `in 2 hours`
- `in 3d`, `in 3 days`

### Today/Tomorrow
- `at 14:30`, `at 9:00`
- `tomorrow at 9am` (requires dateparser)
- `next monday at 3pm` (requires dateparser)

### Absolute
- `2026-01-15 14:30`

### Natural Language (if dateparser installed)
- `tomorrow morning`
- `next friday at 2pm`
- `in 2 weeks`

## Architecture

### Storage

**Database**: SQLite at `$STATE_DIR/reminders.sqlite3` (default: `~/.local/state/milton/reminders.sqlite3`)

**Schema**:
```sql
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY,
    kind TEXT,               -- REMIND, ALARM, etc.
    message TEXT,
    due_at INTEGER,          -- Unix timestamp (UTC)
    created_at INTEGER,
    sent_at INTEGER,
    canceled_at INTEGER,
    timezone TEXT,           -- e.g., America/New_York
    delivery_target TEXT,    -- Optional target info
    last_error TEXT          -- Last delivery error
)
```

### Scheduler

The `ReminderScheduler` runs as a background thread that:
1. Polls the database every N seconds (default: 5)
2. Finds reminders where `due_at <= now` and `sent_at IS NULL`
3. Attempts to send via ntfy
4. Retries failed deliveries with exponential backoff
5. Marks as sent or failed after max retries

### Timezone Handling

- **Storage**: All timestamps stored as UTC (Unix epoch)
- **Parsing**: Time expressions parsed in the specified timezone (default: America/New_York)
- **Display**: Timestamps formatted with timezone info

### Retry Logic

```
Attempt 1: Send immediately
Attempt 2: Wait 60s (retry_backoff)
Attempt 3: Wait 120s (retry_backoff * 2)
After max_retries: Mark as failed, log error
```

## Integration Modes

### 1. Standalone CLI

Run the scheduler and use CLI commands directly:
```bash
# Terminal 1: Scheduler
milton-reminders run

# Terminal 2: Add reminders
milton-reminders add "Test" --when "in 5m"
```

### 2. NEXUS Agent Tool

NEXUS automatically recognizes reminder requests:
```python
from agents.nexus import NEXUS

nexus = NEXUS()
response = nexus.process_message("remind me to check email in 30 minutes")
print(response.text)
# ✓ Reminder set (ID: 1)
#   Message: check email
#   Due: 2026-01-02 14:30 EST
```

### 3. Milton Orchestrator

The orchestrator runs a scheduler automatically when `ENABLE_REMINDERS=true`:
```bash
# In .env
ENABLE_REMINDERS=true
NTFY_TOPIC=milton-reminders

# Run orchestrator
milton-orchestrator
```

Reminders sent via `REMIND:` prefix are automatically handled.

## Running as a Service

### systemd Example

Create `/etc/systemd/user/milton-reminders.service`:

```ini
[Unit]
Description=Milton Reminders Scheduler
After=network.target

[Service]
Type=simple
Environment="NTFY_TOPIC=your-topic"
Environment="NTFY_BASE_URL=https://ntfy.sh"
Environment="TZ=America/New_York"
ExecStart=/home/cole-hanan/miniconda3/envs/milton/bin/milton-reminders run
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

**Enable and start:**
```bash
systemctl --user daemon-reload
systemctl --user enable milton-reminders
systemctl --user start milton-reminders

# Check status
systemctl --user status milton-reminders

# View logs
journalctl --user -u milton-reminders -f
```

## Error Handling

### Failed Deliveries

When a notification fails:
1. Error logged to `last_error` column
2. Retry scheduled with exponential backoff
3. After `max_retries`, marked as sent with error logged

**Check for errors:**
```bash
milton-reminders list --verbose --all
```

Example output:
```
ID     Due                  Kind     Message           Status
================================================================================
42     2026-01-02 14:30 EST REMIND   Check build       ERROR
       Error: Failed after 3 attempts
```

### Common Issues

**"NTFY_TOPIC not set"**
```bash
export NTFY_TOPIC=your-topic-name
```

**"Could not parse time expression"**
- Install dateparser: `pip install dateparser`
- Or use simpler format: "in 30m", "at 14:30"

**Reminders not sending**
- Check scheduler is running: `ps aux | grep milton-reminders`
- Check ntfy topic is correct
- Test ntfy manually: `curl -d "Test" ntfy.sh/your-topic`

## Testing

### Unit Tests

```bash
pytest tests/test_reminders.py -v
```

### Manual End-to-End Test

```bash
# Terminal 1: Start scheduler
milton-reminders run --verbose

# Terminal 2: Create test reminder
milton-reminders add "Test notification" --when "in 1m"

# Terminal 2: Watch for reminder
milton-reminders list

# Check your phone for notification in 1 minute
```

### Verification Script

Run the included verification script:
```bash
./scripts/verify_reminders.sh
```

This script:
1. Checks dependencies
2. Creates a test reminder
3. Verifies it appears in the database
4. Optionally sends a test notification

## Best Practices

1. **Run scheduler as a service**: Use systemd for production
2. **Set explicit timezone**: Don't rely on system TZ
3. **Use unique ntfy topics**: Avoid conflicts with other services
4. **Monitor logs**: Watch for delivery failures
5. **Clean up old reminders**: Periodically check `--all` and remove old entries

## FAQ

**Q: Do reminders persist across restarts?**
A: Yes! They're stored in SQLite and automatically reloaded on scheduler start.

**Q: What happens if the scheduler is down when a reminder is due?**
A: It sends immediately when the scheduler restarts (if still within retry window).

**Q: Can I use a self-hosted ntfy server?**
A: Yes! Set `NTFY_BASE_URL=https://your-server.com`

**Q: How do I secure my ntfy topic?**
A: Use ntfy access tokens:
```bash
export NTFY_TOKEN=tk_yourtokenhere
```

**Q: Can I change timezones?**
A: Yes, set `TZ` environment variable or use `--timezone` flag per reminder.

**Q: What's the difference between REMIND and ALARM?**
A: Just a label (kind). Both work identically. Use for organization.

## Advanced Usage

### Custom Delivery Targets

```bash
milton-reminders add "Deploy complete" --when "in 5m" --target "ops-channel"
```

This stores metadata you can use for custom routing in your publish function.

### JSON Integration

```bash
# Add and capture ID
RESULT=$(milton-reminders add "Test" --when "in 1h" --json)
ID=$(echo $RESULT | jq -r '.id')

# Later, cancel it
milton-reminders cancel $ID
```

### Programmatic Access

```python
from pathlib import Path
from milton_orchestrator.reminders import ReminderStore, parse_time_expression

db_path = Path.home() / ".local/state/milton/reminders.sqlite3"
store = ReminderStore(db_path)

# Create reminder
due_ts = parse_time_expression("tomorrow at 9am", timezone="America/New_York")
reminder_id = store.add_reminder("REMIND", due_ts, "Morning standup")

# List pending
reminders = store.list_reminders()
for r in reminders:
    print(f"{r.id}: {r.message} at {r.due_at}")

store.close()
```

## Roadmap

- [ ] Web UI for reminder management
- [ ] Recurring reminders (daily, weekly)
- [ ] Reminder templates
- [ ] Voice input integration
- [ ] Calendar sync
- [ ] Smart scheduling (suggest optimal times)

## Troubleshooting

Enable debug logging:
```bash
milton-reminders run --verbose
```

Check database directly:
```bash
sqlite3 ~/.local/state/milton/reminders.sqlite3 "SELECT * FROM reminders;"
```

Test ntfy connectivity:
```bash
curl -d "Test from CLI" https://ntfy.sh/your-topic
```

## Support

- GitHub Issues: https://github.com/colehanan1/milton/issues
- Logs: Check systemd journal or console output
- Database: `~/.local/state/milton/reminders.sqlite3`

---

**Version**: 1.0.0
**Last Updated**: 2026-01-02
