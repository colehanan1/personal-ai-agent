# Milton Orchestrator - Quick Start Guide

## What You Have

A complete voice-to-code system that:
- Receives text commands from your iPhone via ntfy
- Uses Perplexity AI to research and optimize prompts  
- Executes Claude Code to implement changes
- Sends status updates back to your iPhone

## Installation Steps

### 1. Install the Package

```bash
cd /home/cole-hanan/milton

# Run installation script (creates venv, installs deps)
./scripts/install.sh
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit with your values
nano .env
```

**Required settings:**
```bash
PERPLEXITY_API_KEY=your_key_here
TARGET_REPO=/home/cole-hanan/your-project-directory
```

### 3. Test the Installation

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
pytest

# Test the CLI
milton-orchestrator --help

# Test in dry-run mode
milton-orchestrator --dry-run
```

### 4. Install Systemd Service (Recommended)

```bash
# This makes the orchestrator run automatically
./scripts/install-service.sh

# Start the service
systemctl --user start milton-orchestrator

# Check status
systemctl --user status milton-orchestrator

# Enable at login (survives reboots)
systemctl --user enable milton-orchestrator
```

## How to Use

### From Your iPhone

Install the [ntfy app](https://ntfy.sh) and subscribe to your topics.

#### Send a Coding Request

Send a message to `milton-briefing-code-ask`:

```
CODE: Add a login feature with email and password authentication
```

The orchestrator will:
1. Send ACK to your phone
2. Research with Perplexity
3. Execute Claude Code  
4. Send results back to your phone

#### Send a Research Request

```
RESEARCH: How does the auth system work?
```

This only runs Perplexity research - no code changes.

### Example Messages

**Add a feature:**
```
CODE: Implement a REST API endpoint for user registration
```

**Fix a bug:**
```
CODE: Fix the memory leak in the background worker
```

**Write tests:**
```
Add pytest tests for the authentication module
```

**Research only:**
```
RESEARCH: What testing frameworks are used in this codebase?
```

## Monitoring

### View Logs

```bash
# Real-time logs
journalctl --user -u milton-orchestrator -f

# Last 50 entries
journalctl --user -u milton-orchestrator -n 50

# File logs (daily)
tail -f ~/.local/state/milton_orchestrator/logs/$(date +%Y-%m-%d).log
```

### Check Outputs

Full Claude Code outputs are saved to:
```bash
ls -lah ~/.local/state/milton_orchestrator/outputs/
```

### Service Status

```bash
# Check if running
systemctl --user status milton-orchestrator

# Start/stop/restart
systemctl --user start milton-orchestrator
systemctl --user stop milton-orchestrator
systemctl --user restart milton-orchestrator
```

## Troubleshooting

### "Configuration error: PERPLEXITY_API_KEY is required"

Set the environment variable:
```bash
export PERPLEXITY_API_KEY=your_key_here
# Or add to .env file
```

### "Configuration error: TARGET_REPO does not exist"

Create the target directory or fix the path:
```bash
mkdir -p /path/to/your/project
# Or update TARGET_REPO in .env
```

### Not receiving messages from iPhone

1. Check topic names match in ntfy app and .env
2. Test subscription:
   ```bash
   curl -s https://ntfy.sh/milton-briefing-code-ask/json
   ```
3. Send test message:
   ```bash
   curl -d "Test" https://ntfy.sh/milton-briefing-code-ask
   ```

### Claude Code not found

Install Claude Code or set CLAUDE_BIN:
```bash
# Check if installed
which claude

# Or set custom path in .env
CLAUDE_BIN=/path/to/claude
```

## Next Steps

1. **Test with a small request** - Send a simple CODE request from your phone
2. **Monitor logs** - Watch `journalctl` to see the workflow
3. **Check output** - Review the generated code and summaries
4. **Enable service** - Run `systemctl --user enable milton-orchestrator`

## File Tree

```
milton/
├── milton_orchestrator/        # Main package
│   ├── cli.py                  # Entrypoint
│   ├── config.py               # Config management
│   ├── orchestrator.py         # Main loop
│   ├── ntfy_client.py          # ntfy integration
│   ├── perplexity_client.py    # Perplexity API
│   ├── prompt_builder.py       # Prompt construction
│   └── claude_runner.py        # Claude Code wrapper
├── tests/                      # Unit tests (49 tests)
├── scripts/
│   ├── install.sh              # Installation script
│   └── install-service.sh      # Service installer
├── .env.example                # Config template
├── ORCHESTRATOR_README.md      # Full documentation
└── ORCHESTRATOR_QUICKSTART.md  # This file
```

## Getting Help

- Check logs: `~/.local/state/milton_orchestrator/logs/`
- Run tests: `pytest -v`
- Dry run: `milton-orchestrator --dry-run`
- Verbose mode: `milton-orchestrator -v`
