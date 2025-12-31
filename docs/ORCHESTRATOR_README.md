# Milton Orchestrator

A production-grade voice-to-code orchestrator that receives text commands from your iPhone via ntfy, uses Perplexity AI for research and prompt optimization, and executes code changes using Claude Code CLI.

## Features

- **iPhone Integration**: Receive coding requests from your iPhone via ntfy
- **AI-Powered Research**: Uses Perplexity AI to research and optimize prompts
- **Automated Code Execution**: Runs Claude Code CLI to implement changes
- **Real-time Status Updates**: Sends progress updates back to your iPhone
- **Robust Error Handling**: Retries, timeouts, and graceful fallbacks
- **Production-Ready**: Systemd service, logging, and crash-safe operation
- **Fully Tested**: Comprehensive unit tests with pytest

## Architecture

```
iPhone (ntfy) → Orchestrator → Perplexity AI → Claude Code → Target Repo
                     ↓
              Status Updates (ntfy) → iPhone
```

## Requirements

- Python 3.11 or higher
- Ubuntu or compatible Linux distribution
- Claude Code CLI installed
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

### CODE Request (Full Pipeline)

Prefix with `CODE:` or just send plain text:

```
CODE: Add a login feature to the web app with email and password authentication
```

```
Implement unit tests for the authentication module using pytest
```

This will:
1. Research the request with Perplexity
2. Build an optimized prompt
3. Execute Claude Code in your target repo
4. Send results back to your iPhone

### RESEARCH Request (No Code Changes)

Prefix with `RESEARCH:`:

```
RESEARCH: How does the authentication system work in this codebase?
```

This will:
1. Research the question with Perplexity
2. Send the research back to your iPhone
3. **No code changes will be made**

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
| `REQUEST_TIMEOUT` | Max execution time (seconds) | `600` |

### Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_DIR` | Log file directory | `~/.local/state/milton_orchestrator/logs` |
| `STATE_DIR` | State file directory | `~/.local/state/milton_orchestrator` |
| `MAX_OUTPUT_SIZE` | Max output before truncation | `4000` |

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

1. **File logs**: `~/.local/state/milton_orchestrator/logs/YYYY-MM-DD.log`
2. **Systemd journal**: `journalctl --user -u milton-orchestrator -f`

## Output Files

Full Claude Code outputs are saved to:
```
~/.local/state/milton_orchestrator/outputs/
```

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
└── orchestrator.py          # Main orchestration logic

tests/
├── test_prompt_builder.py   # Prompt building tests
├── test_perplexity_client.py # Perplexity client tests
├── test_claude_runner.py    # Claude runner tests
└── test_ntfy_parsing.py     # ntfy parsing tests

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
- Logs: Check `~/.local/state/milton_orchestrator/logs/`
