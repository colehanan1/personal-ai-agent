# Milton Runtime Operations

This guide covers starting, stopping, and monitoring Milton services using systemd user services.

## Overview

Milton runs two core services:
- **milton-api.service**: REST API server (port 8001)
- **milton-gateway.service**: OpenAI-compatible chat gateway (port 8081)

Both services are managed as systemd user units, ensuring deterministic startup, automatic restarts on failure, and centralized logging.

## Quick Start

```bash
# Start Milton services
./scripts/milton_up.sh

# Run smoke tests
./scripts/milton_smoke.sh

# Check service status
./scripts/milton_status.sh

# Stop services
./scripts/milton_down.sh
```

## Configuration

### Environment File

All configuration is centralized in `scripts/milton.env`:

```bash
# State directory (primary data location)
export MILTON_STATE_DIR="$HOME/.local/state/milton"

# Service endpoints
export MILTON_API_URL="http://localhost:8001"
export GATEWAY_URL="http://localhost:8081"

# Backend services
export LLM_API_URL="http://localhost:8000"
export WEAVIATE_URL="http://localhost:8080"

# Feature flags
export MILTON_GATEWAY_MEMORY_RETRIEVAL=1  # 1=enabled, 0=disabled
```

To customize:
1. Edit `scripts/milton.env` with your desired values
2. Re-run `./scripts/milton_up.sh` to apply changes

### Systemd Service Units

Service unit files are generated from templates in `scripts/systemd/` and installed to `~/.config/systemd/user/` when you run `milton_up.sh`.

The templates support:
- Automatic Python executable detection (venv, .venv, or system python)
- Environment variable substitution for paths
- Automatic restart on failure
- Structured logging to both journalctl and file

## Service Management

### Starting Services

```bash
./scripts/milton_up.sh
```

This script:
1. Sources `scripts/milton.env` for configuration
2. Detects Python executable (venv/bin/python, .venv/bin/python, or system python)
3. Generates and installs systemd service units
4. Starts services in correct order (API first, then Gateway)
5. Waits for health checks to pass
6. Shows service status and next steps

### Stopping Services

```bash
# Clean shutdown
./scripts/milton_down.sh

# Force shutdown (kills processes on Milton ports)
./scripts/milton_down.sh --force
```

### Checking Status

```bash
./scripts/milton_status.sh
```

Shows:
- Systemd service status
- Effective configuration
- Health check results for all endpoints
- Memory retrieval status
- Log file locations

### Manual systemd Commands

```bash
# Start/stop individual services
systemctl --user start milton-api
systemctl --user start milton-gateway
systemctl --user stop milton-api
systemctl --user stop milton-gateway

# Restart services
systemctl --user restart milton-api
systemctl --user restart milton-gateway

# View status
systemctl --user status milton-api milton-gateway --no-pager

# Enable/disable autostart
systemctl --user enable milton-api milton-gateway
systemctl --user disable milton-api milton-gateway

# Reload systemd configuration after manual edits
systemctl --user daemon-reload
```

## Logging

### Viewing Logs

Logs are available through both journalctl and log files:

```bash
# Via journalctl (recommended)
journalctl --user -u milton-api -f              # Follow API logs
journalctl --user -u milton-gateway -f          # Follow Gateway logs
journalctl --user -u milton-api -n 100 --no-pager   # Last 100 API entries

# Via log files
tail -f ~/.local/state/milton/logs/milton-api.log
tail -f ~/.local/state/milton/logs/milton-gateway.log
```

### Log Locations

- **Systemd journal**: `journalctl --user -u milton-api` / `-u milton-gateway`
- **Log files**: `$MILTON_STATE_DIR/logs/milton-{api,gateway}.log`
  - Default: `~/.local/state/milton/logs/`

## Smoke Tests

The smoke test script validates all critical functionality:

```bash
./scripts/milton_smoke.sh
```

Tests performed:
1. API `/config` endpoint returns `state_dir`
2. API `/health` endpoint responds
3. Gateway `/health` endpoint responds (checks LLM and memory backend status)
4. Gateway `/memory/status` accessible
5. Gateway `/v1/chat/completions` with memory query succeeds
6. Gateway memory retrieval verification (when enabled)
7. Gateway logs have no ResourceWarning or Con004 errors

Exit codes:
- `0`: All tests passed
- `1`: One or more tests failed (see output for details)

## Ship Checklist

Before considering Milton "ship-ready":

1. **Start services**: `./scripts/milton_up.sh`
2. **Run smoke tests**: `./scripts/milton_smoke.sh` (must exit 0)
3. **Check status**: `./scripts/milton_status.sh`
4. **Review logs**: `journalctl --user -u milton-gateway -n 200 --no-pager`

All steps should complete without errors.

## Common Failure Modes

### Port Already in Use

**Symptom**: Service fails to start, logs show "Address already in use"

**Diagnosis**:
```bash
lsof -iTCP:8001 -sTCP:LISTEN -n -P  # API port
lsof -iTCP:8081 -sTCP:LISTEN -n -P  # Gateway port
```

**Resolution**:
```bash
# Option 1: Stop conflicting process
./scripts/milton_down.sh --force

# Option 2: Change ports in scripts/milton.env
export MILTON_API_PORT=8002
export MILTON_CHAT_PORT=8082
./scripts/milton_up.sh
```

### Memory Status Not Updating

**Symptom**: `/memory/status` shows `"last_retrieval": null` after chat requests

**Diagnosis**:
- Check `MILTON_GATEWAY_MEMORY_RETRIEVAL` in `scripts/milton.env` (should be `1`)
- Check Weaviate is running: `curl -fsS http://localhost:8080/v1/meta`
- Check gateway logs for memory-related errors

**Resolution**:
```bash
# Ensure memory retrieval is enabled
grep MILTON_GATEWAY_MEMORY_RETRIEVAL scripts/milton.env

# Restart gateway with memory retrieval enabled
export MILTON_GATEWAY_MEMORY_RETRIEVAL=1
systemctl --user restart milton-gateway

# Verify with smoke test
./scripts/milton_smoke.sh
```

### LLM Backend Unreachable

**Symptom**: Gateway `/health` shows `"llm": "down"`

**Diagnosis**:
```bash
# Check LLM is running
curl -fsS http://localhost:8000/v1/models

# Check LLM_API_URL in config
grep LLM_API_URL scripts/milton.env
```

**Resolution**:
- Start your LLM backend (e.g., vLLM, llama.cpp, Ollama)
- Update `LLM_API_URL` in `scripts/milton.env` if needed
- Restart gateway: `systemctl --user restart milton-gateway`

### Service Starts Then Dies Immediately

**Symptom**: `systemctl status` shows service as `failed` or `inactive (dead)`

**Diagnosis**:
```bash
# Check recent logs for Python errors
journalctl --user -u milton-api -n 50 --no-pager
journalctl --user -u milton-gateway -n 50 --no-pager
```

**Resolution**:
- Common causes: missing dependencies, Python import errors, invalid config
- Verify Python environment: `./scripts/milton_up.sh` shows detected Python
- Test manual start: `python scripts/start_api_server.py`

## State Directory

All persistent data lives under `$MILTON_STATE_DIR` (default: `~/.local/state/milton`):

```
~/.local/state/milton/
├── logs/                  # Service logs
│   ├── milton-api.log
│   └── milton-gateway.log
├── goals/                 # Goals YAML files
├── job_queue/             # Overnight job queue
├── inbox/                 # Briefing outputs
├── briefing.sqlite3       # Briefing items DB
├── reminders.sqlite3      # Reminders DB
└── ...
```

To use a different state directory:
```bash
# Edit scripts/milton.env
export MILTON_STATE_DIR="/path/to/custom/state"

# Or set per-invocation
MILTON_STATE_DIR=/path/to/custom/state ./scripts/milton_up.sh
```

## Setting MILTON_STATE_DIR / Environment Variables

### Persistent Configuration

Edit `scripts/milton.env`:
```bash
export MILTON_STATE_DIR="$HOME/milton-data"
export LLM_API_URL="http://192.168.1.100:8000"
```

Then restart services:
```bash
./scripts/milton_down.sh
./scripts/milton_up.sh
```

### One-Time Override

```bash
MILTON_STATE_DIR=/tmp/test-milton ./scripts/milton_up.sh
```

### Verifying Configuration

```bash
# Check what the API server is using
curl -s http://localhost:8001/config | jq .state_dir

# Check environment in running service
systemctl --user show milton-api --property=Environment
```

## Integration with External Services

### Weaviate (Vector Database)

Milton expects Weaviate at `$WEAVIATE_URL` (default: `http://localhost:8080`).

If Weaviate is managed outside Milton (e.g., Docker):
```bash
# Start Weaviate (example)
docker run -d -p 8080:8080 semitechnologies/weaviate:latest

# Verify
curl -fsS http://localhost:8080/v1/meta
```

Milton services will report degraded health if Weaviate is down, but will continue operating.

### LLM Backend

Milton expects an OpenAI-compatible LLM at `$LLM_API_URL` (default: `http://localhost:8000`).

Supported backends:
- vLLM
- llama.cpp server
- Ollama
- Any OpenAI-compatible API

If LLM is managed outside Milton:
```bash
# Example: vLLM
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000

# Verify
curl -fsS http://localhost:8000/v1/models
```

## Adding Weaviate/LLM to systemd (Optional)

You can optionally create systemd user services for Weaviate and LLM backends:

```bash
# Example: Weaviate via Docker
# Create ~/.config/systemd/user/weaviate.service
[Unit]
Description=Weaviate Vector Database
After=docker.service
Requires=docker.service

[Service]
Type=simple
ExecStart=/usr/bin/docker run --rm --name weaviate -p 8080:8080 semitechnologies/weaviate:latest
ExecStop=/usr/bin/docker stop weaviate

[Install]
WantedBy=default.target
```

Then:
```bash
systemctl --user daemon-reload
systemctl --user enable --now weaviate.service
```

## Troubleshooting

### Service Won't Start

1. Check systemd status: `systemctl --user status milton-api milton-gateway`
2. Check logs: `journalctl --user -u milton-api -n 100 --no-pager`
3. Verify Python: `which python3`
4. Test manual start: `python scripts/start_api_server.py`

### Health Checks Failing

1. Check ports are not blocked: `nc -z localhost 8001`
2. Check firewall rules: `sudo ufw status`
3. Verify services are listening: `lsof -iTCP:8001 -sTCP:LISTEN`

### Memory Retrieval Not Working

1. Enable verbose logging: Set `LOG_LEVEL=DEBUG` in `scripts/milton.env`
2. Check Weaviate: `curl http://localhost:8080/v1/meta`
3. Check gateway logs for "memory retrieval" messages
4. Run smoke test: `./scripts/milton_smoke.sh`

## Reference

### Service Dependencies

- **milton-api.service**: No dependencies
- **milton-gateway.service**: After=milton-api.service, Wants=milton-api.service

Gateway waits for API to be healthy before starting.

### Default Ports

- 8001: Milton API (REST + WebSocket)
- 8081: Milton Gateway (OpenAI-compatible chat API)
- 8000: LLM Backend (external)
- 8080: Weaviate (external)

### Key Files

- `scripts/milton.env`: Environment configuration
- `scripts/milton_up.sh`: Start services
- `scripts/milton_down.sh`: Stop services
- `scripts/milton_status.sh`: Check status
- `scripts/milton_smoke.sh`: Run smoke tests
- `scripts/systemd/*.service.template`: Service unit templates
- `~/.config/systemd/user/milton-{api,gateway}.service`: Installed service units
