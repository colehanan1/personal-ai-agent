# Milton iPhone Ask/Answer Listener - Production Documentation

**Status**: Works ✅

The Milton Phone Listener is a production-ready systemd service that enables you to ask questions to Milton from your iPhone via ntfy, with robust security controls, audit logging, and routing through NEXUS.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Security Model](#security-model)
4. [Installation & Setup](#installation--setup)
5. [Usage](#usage)
6. [Action Allowlist](#action-allowlist)
7. [Message Prefixes](#message-prefixes)
8. [Audit Logging](#audit-logging)
9. [Systemd Service Management](#systemd-service-management)
10. [Troubleshooting](#troubleshooting)
11. [Threat Model](#threat-model)

---

## Overview

### What It Does

- **Listens**: Monitors ntfy topic for incoming questions from your iPhone
- **Parses**: Extracts message prefixes (claude/cortex/frontier/status/briefing)
- **Routes**: All requests go through NEXUS as single entrypoint (no ad-hoc execution)
- **Enforces**: Action allowlist prevents unauthorized operations
- **Audits**: Full audit trail with who/when/what/task_id/result
- **Responds**: Sends AI-generated answers back to your iPhone

### Key Principles

1. **No Silent Remote Code Execution**: All actions must be on allowlist
2. **Single Entrypoint**: All requests route through NEXUS orchestrator
3. **Audit Everything**: Complete provenance trail for all operations
4. **Read-Only by Default**: Write operations require explicit allowlist entry
5. **Restartable & Observable**: systemd service with journald logs

---

## Architecture

```
iPhone (ntfy app)
    ↓
    | Send message to ntfy.sh/{TOPIC}-ask
    ↓
ntfy.sh (public server)
    ↓
    | Stream to listener
    ↓
Milton Phone Listener (systemd service)
    ├─ Parse message prefix
    ├─ Determine action
    ├─ Check allowlist ←─────┐
    │                         │
    ├─ Execute via NEXUS ─────┤ Single Entrypoint
    │   └─ NEXUS routes to    │
    │      CORTEX/FRONTIER     │
    │                          │
    ├─ Write audit log ────────┘
    │
    ↓
Send response to ntfy.sh/{TOPIC}
    ↓
iPhone notification
```

### Process Flow

1. **Message Reception**: ntfy stream delivers message
2. **Parsing**: Extract prefix (claude:/cortex:/frontier:/status:/briefing:)
3. **Action Determination**: Map prefix + content → action type
4. **Allowlist Check**: Verify action is permitted
5. **NEXUS Routing**: All requests go through NEXUS (single entrypoint)
6. **Audit Logging**: Write complete audit trail (JSONL format)
7. **Response**: Send formatted answer back to iPhone

---

## Security Model

### Threat Model

**Threats Mitigated**:
- ✅ Unauthorized remote code execution
- ✅ Unaudited system modifications
- ✅ Privilege escalation from phone listener
- ✅ Information disclosure without logging
- ✅ Denial of service via resource exhaustion

**Threats NOT Mitigated** (out of scope for single-user system):
- ❌ Multi-user isolation (single-user only)
- ❌ ntfy.sh compromise (public server, use unique topic names)
- ❌ Physical device access (assume trusted device)

### Security Controls

1. **Action Allowlist**
   - Only permitted actions can execute
   - Read-only by default
   - Write operations explicitly marked

2. **NEXUS Single Entrypoint**
   - No ad-hoc code execution
   - All routing through NEXUS orchestrator
   - Consistent authorization model

3. **Audit Logging**
   - JSONL format with full provenance
   - Stored in STATE_DIR/logs/phone_listener/
   - Includes: timestamp, action, message, task_id, result

4. **systemd Security Hardening**
   - `NoNewPrivileges`: Prevent escalation
   - `ProtectSystem`: Read-only /usr, /boot, /efi
   - `PrivateDevices`: No direct hardware access
   - `SystemCallFilter`: Restrict syscalls to safe subset
   - `CapabilityBoundingSet`: Drop all capabilities
   - `MemoryDenyWriteExecute`: Prevent code injection

---

## Installation & Setup

### Prerequisites

- Milton system installed
- ntfy.sh account (free, public service)
- iPhone with ntfy app installed

### 1. Configure ntfy Topic

```bash
# Edit .env
NTFY_TOPIC=milton-briefing-YOUR_UNIQUE_ID

# The listener will use:
# - Listen topic: {NTFY_TOPIC}-ask (e.g., milton-briefing-YOUR_UNIQUE_ID-ask)
# - Response topic: {NTFY_TOPIC} (e.g., milton-briefing-YOUR_UNIQUE_ID)
```

**⚠️  Security Note**: Use a unique, hard-to-guess topic name to prevent unauthorized access.

### 2. Install systemd Service

```bash
# Copy service file
mkdir -p ~/.config/systemd/user
cp systemd/milton-phone-listener.service ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable service (start on boot)
systemctl --user enable milton-phone-listener.service

# Start service
systemctl --user start milton-phone-listener.service
```

### 3. Subscribe on iPhone

1. Open ntfy app
2. Add subscription: `{NTFY_TOPIC}-ask` (for sending)
3. Add subscription: `{NTFY_TOPIC}` (for receiving responses)

---

## Usage

### Asking Questions

#### From iPhone (ntfy app)

1. Open ntfy app
2. Select `{NTFY_TOPIC}-ask` subscription
3. Tap "Send"
4. Type your question
5. Receive response on `{NTFY_TOPIC}` subscription

#### From Command Line (Testing)

```bash
# Ask a question
curl -d "What's the weather today?" ntfy.sh/{NTFY_TOPIC}-ask

# Ask with prefix
curl -d "cortex: Analyze my research papers" ntfy.sh/{NTFY_TOPIC}-ask

# Get system status
curl -d "status: Show current status" ntfy.sh/{NTFY_TOPIC}-ask
```

### Test Mode (Dry-Run)

Test message handling without ntfy:

```bash
# Test a simple question
python scripts/ask_from_phone.py --test "What's the weather?"

# Test with prefix
python scripts/ask_from_phone.py --test "cortex: Analyze my papers tonight"

# Test status check
python scripts/ask_from_phone.py --test "status:"
```

### Show Audit Log

```bash
python scripts/ask_from_phone.py --show-audit
```

### Show Allowlist

```bash
python scripts/ask_from_phone.py --show-allowlist
```

---

## Action Allowlist

All permitted actions that can be executed from iPhone:

| Action | Description | Read-Only | Example |
|--------|-------------|-----------|---------|
| `ask_question` | Ask AI question via NEXUS | ✅ Yes | "What's the weather?" |
| `get_status` | Get Milton system status | ✅ Yes | "status:" |
| `get_briefing` | Generate morning/evening briefing | ✅ Yes | "briefing:" |
| `enqueue_job` | Submit job to overnight queue | ❌ No | "cortex: Analyze my papers tonight" |
| `check_reminders` | Check active reminders | ✅ Yes | "Check my reminders" |
| `weather` | Get weather forecast | ✅ Yes | "What's the weather?" |

### Modifying the Allowlist

To add a new allowed action:

1. Edit `scripts/ask_from_phone.py`
2. Add entry to `ALLOWED_ACTIONS` dict:

```python
ALLOWED_ACTIONS = {
    # Existing actions...
    "new_action": ("Description of action", read_only_bool),
}
```

3. Implement handler in `execute_allowed_action()`:

```python
elif action == "new_action":
    # Implementation here
    return route_to_nexus(query, prefix)
```

4. Restart service:

```bash
systemctl --user restart milton-phone-listener.service
```

---

## Message Prefixes

Control routing by prefixing your message:

### Supported Prefixes

| Prefix | Routes To | Example |
|--------|-----------|---------|
| (none) | NEXUS (auto-route) | "What's the weather?" |
| `claude:` | NEXUS | "claude: Explain quantum computing" |
| `cortex:` | CORTEX via NEXUS | "cortex: Analyze my research papers" |
| `frontier:` | FRONTIER via NEXUS | "frontier: Find papers on fMRI" |
| `status:` | System status check | "status:" |
| `briefing:` | Generate briefing | "briefing:" |

### Examples

```bash
# Default routing (NEXUS decides)
"What's the weather today?"

# Explicit CORTEX routing
"cortex: Create a plan for my PhD thesis"

# FRONTIER research discovery
"frontier: Find recent papers on brain imaging"

# System status
"status:"

# Morning briefing
"briefing:"

# Job submission (overnight processing)
"cortex: Analyze all my research papers tonight"
```

---

## Audit Logging

### Log Format

All actions are logged in JSONL format (one JSON object per line):

```json
{
  "action": "ask_question",
  "allowed": true,
  "error": null,
  "message": "What's the weather?",
  "parsed_prefix": null,
  "parsed_query": "What's the weather?",
  "result_summary": "Success: 245 chars",
  "source": "phone_listener",
  "task_id": "phone_20260102_143025",
  "timestamp": "2026-01-02T14:30:25.123456+00:00"
}
```

### Log Location

```
STATE_DIR/logs/phone_listener/audit_YYYYMMDD.jsonl
```

### Viewing Logs

```bash
# Show recent audit entries
python scripts/ask_from_phone.py --show-audit

# View raw JSONL log
cat ~/.local/state/milton/logs/phone_listener/audit_$(date +%Y%m%d).jsonl | jq

# Search for specific action
grep -r "enqueue_job" ~/.local/state/milton/logs/phone_listener/

# Count actions by type
jq -r .action ~/.local/state/milton/logs/phone_listener/audit_*.jsonl | sort | uniq -c
```

### Audit Log Fields

- `timestamp`: ISO 8601 timestamp (UTC)
- `source`: Always "phone_listener"
- `action`: Action type (ask_question, get_status, etc.)
- `message`: Original message from phone
- `parsed_prefix`: Detected prefix (claude/cortex/frontier/etc.)
- `parsed_query`: Query after prefix removal
- `allowed`: Whether action was permitted (true/false)
- `task_id`: Unique task identifier
- `result_summary`: Brief result description
- `error`: Error message if failed (null otherwise)

---

## Systemd Service Management

### Start/Stop/Restart

```bash
# Start service
systemctl --user start milton-phone-listener.service

# Stop service
systemctl --user stop milton-phone-listener.service

# Restart service (after config changes)
systemctl --user restart milton-phone-listener.service

# Check status
systemctl --user status milton-phone-listener.service
```

### Enable/Disable Auto-Start

```bash
# Enable (start on boot)
systemctl --user enable milton-phone-listener.service

# Disable (don't start on boot)
systemctl --user disable milton-phone-listener.service
```

### View Logs

```bash
# View recent logs
journalctl --user -u milton-phone-listener.service -n 50

# Follow logs (live tail)
journalctl --user -u milton-phone-listener.service -f

# Show logs for today
journalctl --user -u milton-phone-listener.service --since today

# Show logs with full details
journalctl --user -u milton-phone-listener.service -o verbose
```

### Service Configuration

Edit service file:

```bash
# Edit
vim ~/.config/systemd/user/milton-phone-listener.service

# Reload systemd after editing
systemctl --user daemon-reload

# Restart service to apply changes
systemctl --user restart milton-phone-listener.service
```

### Environment Variables

Set in `.env` file:

```bash
# ntfy topic
NTFY_TOPIC=milton-briefing-YOUR_UNIQUE_ID

# Dry-run mode (no ntfy connection, testing only)
PHONE_LISTENER_DRY_RUN=false

# State directory
STATE_DIR=~/.local/state/milton
```

---

## Troubleshooting

### Service Won't Start

**Symptom**: `systemctl --user status milton-phone-listener.service` shows failed state

**Check**:
1. Verify `.env` file exists and has `NTFY_TOPIC` set
2. Check logs: `journalctl --user -u milton-phone-listener.service -n 50`
3. Test script directly: `python scripts/ask_from_phone.py --listen`
4. Verify PATH includes conda env: `which python3`

**Solution**:
```bash
# Check service status
systemctl --user status milton-phone-listener.service

# View error logs
journalctl --user -u milton-phone-listener.service --since "10 minutes ago"

# Test script manually
cd /home/cole-hanan/milton
python scripts/ask_from_phone.py --listen
```

### Messages Not Received

**Symptom**: Send message via ntfy, but listener doesn't respond

**Check**:
1. Verify service is running: `systemctl --user status milton-phone-listener.service`
2. Check topic name matches: `{NTFY_TOPIC}-ask` for sending
3. View logs for incoming messages: `journalctl --user -u milton-phone-listener.service -f`
4. Test with curl: `curl -d "test" ntfy.sh/{TOPIC}-ask`

**Solution**:
```bash
# Check if listener is connected
journalctl --user -u milton-phone-listener.service | grep "Connected to"

# Verify topic in .env
cat .env | grep NTFY_TOPIC

# Test message delivery
curl -d "Test message" ntfy.sh/$(grep NTFY_TOPIC .env | cut -d= -f2)-ask
```

### No Audit Log Created

**Symptom**: Audit log directory empty or file missing

**Check**:
1. Verify STATE_DIR is writable
2. Check permissions: `ls -la ~/.local/state/milton/logs/phone_listener/`
3. Test audit log manually: `python scripts/ask_from_phone.py --test "test"`

**Solution**:
```bash
# Create log directory if missing
mkdir -p ~/.local/state/milton/logs/phone_listener

# Set permissions
chmod 755 ~/.local/state/milton/logs/phone_listener

# Test audit log
python scripts/ask_from_phone.py --test "Test audit log"
python scripts/ask_from_phone.py --show-audit
```

### NEXUS Routing Errors

**Symptom**: Questions fail with "Error routing request"

**Check**:
1. Verify NEXUS is working: `python -c "from agents.nexus import NEXUS; print(NEXUS().answer('test'))"`
2. Check LLM API is running: `curl http://localhost:8000/health` (if using vLLM)
3. View full error: `journalctl --user -u milton-phone-listener.service -n 50`

**Solution**:
```bash
# Test NEXUS directly
python -c "from agents.nexus import NEXUS; nexus = NEXUS(); print(nexus.answer('What is 2+2?'))"

# Check LLM API
curl http://localhost:8000/v1/models

# Restart listener
systemctl --user restart milton-phone-listener.service
```

---

## Threat Model

### Attack Surface

1. **ntfy.sh Topic**
   - Public server, anyone with topic name can send messages
   - Mitigation: Use unique, hard-to-guess topic names
   - Mitigation: Action allowlist prevents unauthorized operations

2. **Message Injection**
   - Attacker could send crafted messages to bypass allowlist
   - Mitigation: Strict message parsing with prefix validation
   - Mitigation: NEXUS routing (no eval, no shell execution)
   - Mitigation: Full audit trail of all attempts

3. **Denial of Service**
   - Flood listener with messages
   - Mitigation: Rate limiting in ntfy.sh
   - Mitigation: systemd restart limits (StartLimitBurst=6)

4. **Information Disclosure**
   - Responses could leak sensitive data
   - Mitigation: Single-user system (no multi-tenancy)
   - Mitigation: Audit logs track all queries

### Security Assumptions

1. **Trusted Device**: iPhone is assumed to be user's personal device
2. **Single-User**: No multi-user isolation required
3. **Network Security**: Standard network security practices apply
4. **Physical Security**: Physical access to server is controlled

### Recommended Practices

1. **Use Unique Topic Names**: Don't use default topic names
2. **Monitor Audit Logs**: Review regularly for anomalies
3. **Update Allowlist Carefully**: Only add necessary actions
4. **Restart After Changes**: Always restart service after config changes
5. **Backup Audit Logs**: Preserve for security review

---

## Performance Characteristics

### Response Times

- **Message to NEXUS**: < 100ms (parsing + routing)
- **NEXUS processing**: 1-5 seconds (LLM inference)
- **Total latency**: 1-5 seconds from send to receive

### Resource Usage

- **Memory**: ~100-200 MB (Python + NEXUS)
- **CPU**: < 5% idle, < 50% during inference
- **Network**: Minimal (ntfy stream + occasional API calls)
- **Disk**: ~1-5 MB/day audit logs

---

## Definition of Done Checklist

Phone Listener is "Works" when:

- [x] systemd service unit exists and is validated
- [x] Message prefix parsing (claude/cortex/frontier/status/briefing)
- [x] All requests route through NEXUS (single entrypoint)
- [x] Action allowlist enforced
- [x] Audit logging with full provenance
- [x] Security hardening in systemd unit
- [x] Dry-run mode for testing without ntfy
- [x] Documentation complete
- [x] Tests pass

**Status**: ✅ **PRODUCTION READY**

---

## References

- [NEXUS Orchestrator](./AGENTS.md)
- [Job Queue System](./JOB_QUEUE.md)
- [ntfy.sh Documentation](https://ntfy.sh/docs/)
- [systemd User Services](https://wiki.archlinux.org/title/Systemd/User)

---

**Last Updated**: 2026-01-02
**Version**: 1.0.0
**Status**: Production Ready ✅
