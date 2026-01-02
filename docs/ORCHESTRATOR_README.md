# Milton Orchestrator

A production-grade voice-to-code orchestrator that receives text commands from your iPhone via ntfy, uses Perplexity AI for research and prompt optimization, and executes code changes using Claude Code CLI with a Codex CLI fallback for rate limits or outages.

## Features

- **iPhone Integration**: Receive coding requests from your iPhone via ntfy
- **AI-Powered Research**: Uses Perplexity AI to research and optimize prompts
- **Automated Code Execution**: Runs Claude Code CLI to implement changes
- **Codex Fallback**: Automatically falls back to Codex CLI on Claude usage limits or missing binary (plan-first then execute)
- **Routing Controls**: Prefix or topic-based triggers for Claude/Codex/Research/Chat
- **Reminders**: Schedule reminders or alarms via ntfy messages
- **Real-time Status Updates**: Sends progress updates back to your iPhone
- **Robust Error Handling**: Retries, timeouts, and graceful fallbacks
- **Production-Ready**: Systemd service, logging, and crash-safe operation
- **Fully Tested**: Comprehensive unit tests with pytest

## Architecture

```
iPhone (ntfy) → Orchestrator → Perplexity AI → Claude Code → Target Repo
                                      ↘ Codex CLI (fallback) ↗
                     ↓
              Status Updates (ntfy) → iPhone
```

## Requirements

- Python 3.11 or higher
- Ubuntu or compatible Linux distribution
- Claude Code CLI installed
- Codex CLI installed (recommended for fallback)
- Perplexity API key
- ntfy.sh account (or self-hosted ntfy server)

## Installation

### 1. Navigate to Milton Directory

```bash
cd ~/milton
```

### 2. Run Installation Script

```bash
./scripts/install.sh
```

This will:
- Use the existing conda environment `milton`
- Install all dependencies via pip
- Install the `milton-orchestrator` command

### 3. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

**Required variables:**
- `PERPLEXITY_API_KEY`: Your Perplexity API key
- `TARGET_REPO`: Path to the repository where code changes will be made

**Optional variables:** See `.env.example` for all options.

### 3b. Install Codex CLI (Optional but Recommended)

If you want automatic fallback from Claude to Codex:

1. Install Codex CLI using your preferred method.
2. Verify it works:
   ```bash
   codex --help
   ```
3. Ensure authentication is configured (for example `OPENAI_API_KEY` if required).

### 4. Install Systemd Service (Optional)

```bash
./scripts/install-service.sh
```

This creates a systemd user service that runs the orchestrator automatically.

## Usage

### Manual Run

```bash
# Activate conda environment
conda activate milton

# Run orchestrator
milton-orchestrator

# Run with verbose logging
milton-orchestrator -v

# Run in dry-run mode (no actual Claude execution)
milton-orchestrator --dry-run
```

### Systemd Service

```bash
# Start service
systemctl --user start milton-orchestrator

# Check status
systemctl --user status milton-orchestrator

# View logs
journalctl --user -u milton-orchestrator -f

# Enable at login
systemctl --user enable milton-orchestrator

# Stop service
systemctl --user stop milton-orchestrator
```

## iPhone Message Formats

Send messages to your configured `ASK_TOPIC` (default: `milton-briefing-code-ask`):

### CLAUDE Request (Coding Pipeline)

Prefix with `CLAUDE:`:

```
CLAUDE: Add a login feature to the web app with email and password authentication
```

This will:
1. (Optional) Research the request with Perplexity
2. Build an optimized prompt
3. Execute Claude Code in your target repo (fallback to Codex if Claude is unavailable/limited)
4. Send results back to your iPhone

### CODEX Request (Codex-Only Pipeline)

Prefix with `CODEX:`:

```
CODEX: Implement unit tests for the authentication module using pytest
```

This will:
1. (Optional) Research the request with Perplexity
2. Build an optimized prompt
3. Execute Codex directly (no Claude)
4. Send results back to your iPhone

### RESEARCH Request (No Code Changes)

Prefix with `RESEARCH:`:

```
RESEARCH: How does the authentication system work in this codebase?
```

This will:
1. Research the question with Perplexity
2. Send a structured summary (with sources if returned)
3. **No code changes will be made**

### REMIND / ALARM (Reminders)

```
REMIND: in 30m | Stretch
ALARM: at 07:00 | Wake up
REMIND: list
REMIND: cancel 12
```

Reminders are scheduled locally and delivered via ntfy when due.

### CHAT (Default)

Messages without prefixes are handled as chat (no Perplexity, no code execution).

### Topic-Based Triggers

You can route messages by topic instead of prefixes:

- `CLAUDE_TOPIC`: any message arriving on this topic runs the Claude pipeline
- `CODEX_TOPIC`: any message arriving on this topic runs the Codex pipeline

Topic routing takes priority over prefixes.

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `PERPLEXITY_API_KEY` | Your Perplexity API key | `pplx-abc123...` |
| `TARGET_REPO` | Repository path for code changes | `/home/user/myproject` |

### ntfy Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `NTFY_BASE_URL` | ntfy server URL | `https://ntfy.sh` |
| `ASK_TOPIC` | Topic for incoming requests | `milton-briefing-code-ask` |
| `ANSWER_TOPIC` | Topic for responses | `milton-briefing-code` |
| `CLAUDE_TOPIC` | Optional topic for Claude pipeline | *(empty)* |
| `CODEX_TOPIC` | Optional topic for Codex pipeline | *(empty)* |

### Routing Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_PREFIX_ROUTING` | Enable prefix routing (CLAUDE:/CODEX:/RESEARCH:/REMIND:/ALARM:) | `true` |
| `ENABLE_CLAUDE_PIPELINE` | Enable Claude pipeline | `true` |
| `ENABLE_CODEX_PIPELINE` | Enable Codex pipeline | `true` |
| `ENABLE_RESEARCH_MODE` | Enable research mode | `true` |
| `ENABLE_REMINDERS` | Enable reminders | `true` |
| `PERPLEXITY_IN_CLAUDE_MODE` | Use Perplexity in Claude pipeline | `true` |
| `PERPLEXITY_IN_CODEX_MODE` | Use Perplexity in Codex pipeline | `true` |
| `PERPLEXITY_IN_RESEARCH_MODE` | Use Perplexity in research mode | `true` |

### Perplexity Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PERPLEXITY_MODEL` | Model to use | `sonar-pro` |
| `PERPLEXITY_TIMEOUT` | API timeout (seconds) | `60` |
| `PERPLEXITY_MAX_RETRIES` | Max retry attempts | `3` |

### Claude Code Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_BIN` | Path to Claude binary | `claude` |
| `CLAUDE_TIMEOUT` | Claude execution timeout in seconds (`0` = no timeout) | `0` |
| `REQUEST_TIMEOUT` | Legacy default timeout in seconds | `600` |

### Codex CLI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CODEX_BIN` | Path to Codex binary | `codex` |
| `CODEX_MODEL` | Codex model override (`default` to use CLI default) | `gpt-5.2-codex` |
| `CODEX_TIMEOUT` | Codex execution timeout in seconds (`0` = no timeout) | `0` |
| `CODEX_EXTRA_ARGS` | Extra Codex CLI flags (quoted string) | *(empty)* |
| `ENABLE_CODEX_FALLBACK` | Enable Codex fallback (`always` = any Claude failure) | `true` |
| `CLAUDE_FALLBACK_ON_LIMIT` | Fallback only on usage/rate limits | `true` |

### Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_DIR` | Log file directory | `~/.local/state/milton/logs` |
| `STATE_DIR` | State file directory | `~/.local/state/milton` |
| `MAX_OUTPUT_SIZE` | Max output before truncation | `4000` |

Note: `STATE_DIR` is shared with the core Milton runtime by default. To keep the legacy orchestrator-only layout, set `STATE_DIR=~/.local/state/milton_orchestrator` explicitly.

## Testing

Run the test suite:

```bash
# Activate conda environment
conda activate milton

# Run all tests
pytest

# Run with coverage
pytest --cov=milton_orchestrator

# Run specific test file
pytest tests/test_prompt_builder.py

# Run with verbose output
pytest -v
```

## Logs

Logs are stored in two places:

1. **File logs**: `~/.local/state/milton/logs/YYYY-MM-DD.log`
2. **Systemd journal**: `journalctl --user -u milton-orchestrator -f`

## Output Files

Full Claude Code outputs are saved to:
```
~/.local/state/milton/outputs/
```

Codex outputs (plan + execute) are saved alongside Claude outputs with `codex_*` filenames.
Each file is timestamped for easy reference.

## Troubleshooting

### Orchestrator won't start

1. Check environment variables:
   ```bash
   source .env
   env | grep -E "PERPLEXITY|TARGET_REPO"
   ```

2. Verify TARGET_REPO exists:
   ```bash
   ls -la $TARGET_REPO
   ```

3. Check logs:
   ```bash
   journalctl --user -u milton-orchestrator -n 50
   ```

### Not receiving messages from iPhone

1. Test ntfy subscription:
   ```bash
   curl -s https://ntfy.sh/milton-briefing-code-ask/json
   ```

2. Send a test message:
   ```bash
   curl -d "Test message" https://ntfy.sh/milton-briefing-code-ask
   ```

3. Verify topic names match in your ntfy app and .env file

### Perplexity API errors

1. Verify API key:
   ```bash
   echo $PERPLEXITY_API_KEY
   ```

2. Test API directly:
   ```bash
   curl -X POST https://api.perplexity.ai/chat/completions \
     -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"sonar-pro","messages":[{"role":"user","content":"test"}]}'
   ```

### Claude Code not executing

1. Verify Claude is installed:
   ```bash
   which claude
   claude --version
   ```

2. Test Claude manually:
   ```bash
   cd $TARGET_REPO
   claude -p "Show me the directory structure"
   ```

3. Check permissions on TARGET_REPO

### Codex fallback not triggering

1. Verify Codex CLI is installed:
   ```bash
   which codex
   codex --help
   ```

2. Ensure fallback is enabled:
   ```bash
   ENABLE_CODEX_FALLBACK=true
   CLAUDE_FALLBACK_ON_LIMIT=true
   ```

3. Check outputs and logs after a fallback:
   ```bash
   ls -lah ~/.local/state/milton/outputs/
   tail -f ~/.local/state/milton/logs/$(date +%Y-%m-%d).log
   ```

### Reminders not firing

1. Ensure reminders are enabled:
   ```bash
   ENABLE_REMINDERS=true
   ```
2. Check the reminders database:
   ```bash
   ls -lah ~/.local/state/milton/reminders.sqlite3
   ```
3. Watch logs for scheduler activity:
   ```bash
   tail -f ~/.local/state/milton/logs/$(date +%Y-%m-%d).log
   ```

## Security

- **Never commit .env file**: It contains secrets
- **Use environment variables**: All sensitive data should be in .env
- **Systemd security**: Service runs with NoNewPrivileges and PrivateTmp
- **Input validation**: All inputs are validated before processing
- **Safe subprocess handling**: Timeouts and resource limits applied

## Project Structure

```
milton_orchestrator/
├── __init__.py              # Package initialization
├── cli.py                   # CLI entrypoint
├── config.py                # Configuration management
├── ntfy_client.py           # ntfy subscription and publishing
├── perplexity_client.py     # Perplexity API client
├── prompt_builder.py        # Claude prompt construction
├── claude_runner.py         # Claude Code subprocess wrapper
├── codex_runner.py          # Codex CLI subprocess wrapper
├── reminders.py             # Reminders and scheduling
└── orchestrator.py          # Main orchestration logic

tests/
├── test_prompt_builder.py   # Prompt building tests
├── test_perplexity_client.py # Perplexity client tests
├── test_claude_runner.py    # Claude runner tests
├── test_ntfy_parsing.py     # ntfy parsing tests
├── test_orchestrator_fallback.py # Fallback logic tests
├── test_reminders.py        # Reminder scheduling tests
└── test_routing_modes.py    # Routing mode tests

scripts/
├── install.sh               # Installation script
└── install-service.sh       # Systemd service installer

pyproject.toml               # Project metadata and dependencies
ORCHESTRATOR_README.md       # This file
.env.example                 # Example environment variables
```

## License

MIT License

## Support

For issues and questions:
- Logs: Check `~/.local/state/milton/logs/`
