# Quick Reference: Multi-Channel Notifications

## 🚀 Quick Start

```bash
# 1. Set environment
export NTFY_TOPIC=milton-reminders-abc123
export MILTON_PUBLIC_BASE_URL=http://localhost:8001

# 2. Start API server
python scripts/start_api_server.py

# 3. Start scheduler (in another terminal)
python scripts/run_reminder_scheduler.py

# 4. Test it
curl -X POST http://localhost:8001/api/reminders \
  -H "Content-Type: application/json" \
  -d '{"message": "Test", "remind_at": "in 1m", "channels": ["ntfy"]}'
```

## 📝 Create Reminders

### Multi-Channel
```bash
curl -X POST http://localhost:8001/api/reminders \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Team standup",
    "remind_at": "2024-01-20T10:00:00Z",
    "channels": ["ntfy", "voice"]
  }'
```

### Single Channel (Legacy)
```bash
curl -X POST http://localhost:8001/api/reminders \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Old format",
    "remind_at": "in 1h",
    "channel": "ntfy"
  }'
```

## 🔔 Action Buttons

When notification arrives on your phone:
- **DONE** → Mark acknowledged
- **SNOOZE_30** → Delay 30 minutes
- **DELAY_2H** → Delay 2 hours

Or simulate via API:
```bash
curl -X POST http://localhost:8001/api/reminders/42/action \
  -H "Content-Type: application/json" \
  -d '{"action": "DONE"}'
```

## 🔍 Health Check

```bash
curl http://localhost:8001/api/reminders/health | jq .

# Check if scheduler is alive
curl http://localhost:8001/api/reminders/health | jq '.scheduler.is_alive'

# Check pending reminders
curl http://localhost:8001/api/reminders/health | jq '.reminders.scheduled_count'
```

## 🧪 Run Tests

```bash
# All reminder + notification tests
pytest tests/test_reminders*.py tests/test_notifications.py -v

# Just new tests
pytest tests/test_notifications.py tests/test_reminders_multichannel.py -v

# With coverage
pytest tests/test_reminders*.py tests/test_notifications.py --cov=milton_orchestrator
```

## 🔐 Security (Production)

```bash
# Set action token for callback auth
export MILTON_ACTION_TOKEN=your-secret-token-here

# Then callbacks must include token
curl -X POST http://localhost:8001/api/reminders/42/action \
  -H "Content-Type: application/json" \
  -d '{"action": "DONE", "token": "your-secret-token-here"}'
```

## 📋 List Reminders

```bash
# Scheduled (pending)
curl http://localhost:8001/api/reminders?status=scheduled

# All reminders
curl http://localhost:8001/api/reminders?status=all

# Specific reminder with audit log
curl http://localhost:8001/api/reminders/42
```

## 🐛 Debug

```bash
# Check scheduler heartbeat
curl http://localhost:8001/api/reminders/health | jq '.scheduler.heartbeat_age_sec'
# Should be < 60 seconds if alive

# Check last error
curl http://localhost:8001/api/reminders/health | jq '.delivery.last_error'

# View reminder audit log
curl http://localhost:8001/api/reminders/42 | jq '.audit_log'

# Check logs
tail -f ~/.local/state/milton/logs/api_server.log
```

## 🛠️ Integration Example

```python
from milton_orchestrator.reminders import ReminderStore, ReminderScheduler
from milton_orchestrator.notifications import create_default_router
from milton_orchestrator.state_paths import resolve_state_dir

# Initialize
state_dir = resolve_state_dir()
store = ReminderStore(state_dir / "reminders.db")
router = create_default_router()

# Create scheduler
scheduler = ReminderScheduler(
    store=store,
    notification_router=router,
    interval_seconds=5,
)
scheduler.start()

# Create multi-channel reminder
reminder_id = store.add_reminder(
    kind="REMIND",
    due_at=int(time.time()) + 3600,
    message="Python API test",
    channels=["ntfy", "voice"],
)
```

## 📦 Files Reference

| File | Purpose |
|------|---------|
| `milton_orchestrator/notifications.py` | Provider architecture |
| `milton_orchestrator/reminders.py` | Multi-channel reminder system |
| `scripts/start_api_server.py` | Flask API with callbacks |
| `scripts/run_reminder_scheduler.py` | Standalone scheduler |
| `MULTI_CHANNEL_NOTIFICATIONS.md` | Full deployment guide |
| `IMPLEMENTATION_SUMMARY.md` | Complete technical summary |

## 🆘 Common Issues

**Reminders not firing?**
```bash
# Check scheduler
curl http://localhost:8001/api/reminders/health
```

**Action buttons not appearing?**
- Set `MILTON_PUBLIC_BASE_URL` env var
- Must be accessible from your phone

**401 Unauthorized on callbacks?**
- Check `MILTON_ACTION_TOKEN` is set correctly
- Include token in callback request body

**Voice/desktop popup failing?**
- Expected behavior - these are stubs
- Only ntfy is fully implemented

## 📚 Documentation

- **Deployment Guide**: `MULTI_CHANNEL_NOTIFICATIONS.md`
- **Technical Summary**: `IMPLEMENTATION_SUMMARY.md`
- **This File**: Quick reference for daily use

## ✅ Test Status

```
============================= 80 passed in 10.93s ==============================
```

---

**Status**: ✅ Production Ready  
**Version**: 1.0.0  
**Date**: 2026-01-20
