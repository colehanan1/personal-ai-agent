# Milton - Local-First AI Agent System

**Privacy-focused, reproducible, self-learning multi-agent AI for research and automation**

[![Phase 2](https://img.shields.io/badge/Phase_2-OPERATIONAL-brightgreen)](docs/PHASE2_COMPLETE.md)
[![Tests](https://img.shields.io/badge/tests-71%2B_passing-success)](#testing)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Lines of Code](https://img.shields.io/badge/LOC-~47%2C000-informational)](#)

<!-- Note: keep status badges aligned with docs/PHASE2_COMPLETE.md -->

---

## Project Overview

Milton is a **local-first AI agent system** that runs entirely on your hardware and **continuously improves** by learning from your conversations. Unlike ChatGPT or Claude, your data never leaves your machine, your conversations are remembered forever, every output is reproducible, and the AI gets smarter every week.

**Built for researchers who need:**
- **Privacy** - HIPAA/GDPR compliant by design (zero cloud dependency)
- **Memory** - Learns YOUR research patterns over weeks/months
- **Reproducibility** - Every output includes git hash, versions, random seed
- **Automation** - Queue jobs at night, get results in the morning
- **Cost Control** - No per-token pricing, no rate limits (~$0.50/day electricity)
- **Self-Improving** - Continuous learning via three-prong strategy (see [Vision](docs/01-vision.md))

---

## Current Status: Phase 2 Complete

| Component | Status | Details |
|-----------|--------|---------|
| **vLLM Inference** | OPERATIONAL | Llama-3.1-8B on port 8000 |
| **Weaviate Memory** | OPERATIONAL | 3-tier memory system (short/working/long-term) |
| **NEXUS Agent** | TESTED | Orchestrator & briefing generator |
| **CORTEX Agent** | TESTED | Code executor & job processor |
| **FRONTIER Agent** | TESTED | Research discovery & monitoring |
| **Milton Dashboard** | OPERATIONAL | React/TypeScript monitoring UI |
| **Milton Orchestrator** | OPERATIONAL | Voice-to-code via ntfy |
| **Reminders System** | OPERATIONAL | Persistent SQLite + ntfy notifications |
| **Automation** | READY | Systemd timers (pending install) |

**Test Results:** 71+ test files, 6/6 Phase 2 integration tests passing ([see details](docs/PHASE2_COMPLETE.md))

---

## Architecture

### System Overview

```
User Input (CLI/iPhone/Dashboard)
           |
           v
    +----------------+
    |  ORCHESTRATOR  |  (ntfy listener, optional Perplexity research)
    +-------+--------+
            |
    +-------v---------+
    |  Input Routing  |
    | (Prefix-based)  |
    +--------+--------+
             |
    +--------v----------------------------------------+
    |            Agent Layer (Concurrent)             |
    |  +------------------------------------------+   |
    |  |  NEXUS        CORTEX        FRONTIER     |   |
    |  | (Router)    (Executor)    (Discovery)    |   |
    |  +--------------------+---------------------+   |
    +---------------------------+---------------------+
                     |
    +----------------v-----------------+
    |   Shared vLLM Server (port 8000) |
    |   Llama-3.1-8B + Optional LoRA   |
    +----------------+-----------------+
                     |
    +----------------v------------------+
    |   Memory System (Weaviate)        |
    |  +- Short-term (24-48h)           |
    |  +- Working (active tasks)        |
    |  +- Long-term (compressed)        |
    |   + JSONL fallback in data/memory |
    +-----------------------------------+
             |
             v
    +------------------------------+
    |  Integrations                |
    |  +- Weather (OpenWeatherMap) |
    |  +- arXiv (paper search)     |
    |  +- News API                 |
    |  +- Calendar (Google)        |
    |  +- Home Assistant           |
    |  +- Web Search               |
    +------------------------------+
```

### Three Specialized Agents

```
                    +---------------+
                    |    NEXUS      |  Orchestrator
                    |  (Hub/Router) |  - Routes requests
                    +-------+-------+  - Generates briefings
                            |          - Coordinates agents
            +---------------+---------------+
            |               |               |
      +-----v-----+   +-----v-----+   +-----v------+
      |  CORTEX   |   | FRONTIER  |   |Integration |
      | (Executor)|   |  (Scout)  |   |   APIs     |
      +-----------+   +-----------+   +------------+
       - Code gen      - arXiv        - Weather
       - Analysis      - Research     - News
       - Jobs          - Monitoring   - Calendar
```

**All 3 agents share 1 vLLM server** - they make concurrent HTTP requests to `localhost:8000`. This is faster and more efficient than running 3 separate models.

### 3-Tier Memory System

```
Short-Term (24-48h)  ->  Working (active tasks)  ->  Long-Term (compressed)
     Weaviate              Weaviate                   Weaviate
   (live queries)        (task tracking)           (learned patterns)
```

Memory persists between restarts. The system learns your preferences, research interests, and common workflows over time.

---

## Quick Start

### Prerequisites

- **Hardware**: NVIDIA GPU with 12GB+ VRAM (tested on RTX 5090)
- **Software**: Docker, Conda/Miniconda, Python 3.11+
- **Model**: Llama-3.1-8B-Instruct-HF (auto-downloaded or place in `models/`)

### Installation

```bash
# 1. Clone repository
cd /home/cole-hanan/milton

# 2. Activate conda environment
conda activate milton

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys (Weather, News optional)

# 5. Start Weaviate (vector database)
docker compose up -d

# 6. Initialize memory schema
python memory/init_db.py

# 7. Start vLLM server (in separate terminal)
python scripts/start_vllm.py
# Wait 30-60 seconds for model to load
```

### Quickstart (dev_up)

```bash
conda activate milton
./scripts/dev_up.sh
python scripts/healthcheck.py
python scripts/nexus_morning.py
```

### From iPhone (ntfy -> Click-to-Open -> Memory)

From iPhone: **send** request -> **receive** summary + tap-to-open link -> **memory updated** with request_id + evidence.

See `docs/IOS_OUTPUT_ACCESS.md` for tailnet-only click-to-open setup and message prefixes.

To shut services down:

```bash
./scripts/dev_down.sh
```

### Verify Installation

```bash
# Run integration tests
conda activate milton
python tests/test_phase2.py

# Expected output:
# PASS: vLLM Inference
# PASS: Weaviate Memory
# PASS: Agent Imports
# PASS: Agent Initialization
# PASS: Directory Structure
# PASS: Configuration
# Total: 6/6 tests passed
```

### Smoke Test (CI)

```bash
pytest -q
```

### Generate Your First Morning Briefing

```bash
conda activate milton
python scripts/nexus_morning.py

# Check output
cat inbox/morning/brief_*.json | jq '.brief'
```

### Daily OS Loop (Evening -> Overnight -> Morning)

```bash
conda activate milton
python scripts/evening_briefing.py
python scripts/enhanced_morning_briefing.py
```

Optional: set `STATE_DIR` in `.env` to write goals/queue/inbox outside the repo root.

### Troubleshooting

- `scripts/dev_up.sh` fails on `.env`: run `cp .env.example .env` and fill required keys.
- vLLM not reachable: confirm `python scripts/start_vllm.py` runs and `LLM_API_URL` points to it.
- Weaviate down: run `docker compose up -d` and check `WEAVIATE_URL`.
- Healthcheck failures: run `python scripts/healthcheck.py` for exact status.

---

## Key Components

### Milton Dashboard (React/TypeScript)

A modern web dashboard for monitoring and interacting with Milton.

**Features:**
- Real-time agent status monitoring
- Interactive chat interface with streaming responses
- System metrics and health visualization
- WebSocket integration for live updates

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS

**Location:** `milton-dashboard/`

**Start the dashboard:**
```bash
cd milton-dashboard
npm install
npm run dev
```

### Milton Orchestrator (Voice-to-Code)

Bridge between mobile/voice input and code execution.

**Features:**
- Listens to ntfy notifications (iPhone push requests)
- Optional Perplexity API integration for research context
- Dispatches to Claude Code CLI or Codex CLI
- Publishes results back via ntfy with click-to-open links
- Stores outputs to tailnet-accessible location

**Location:** `milton_orchestrator/`

**Key modules:**
- `orchestrator.py` - Main request processing loop
- `ntfy_client.py` - ntfy subscription/publish with reconnect logic
- `claude_runner.py` - Claude Code CLI wrapper
- `codex_runner.py` - Codex CLI wrapper with fallback
- `reminders.py` - Persistent reminder scheduling

### PhD Context System

Milton includes PhD-aware context injection for researchers on multi-year timelines.

**Features:**
- 4.5-year timeline tracking (configurable)
- Research milestone awareness
- Priority scaling based on deadlines
- Context injection for all agent responses

**Configuration:** `phd_context.py`

See `docs/PHD_BRIEFING_SYSTEM.md` for details.

### Prompting Middleware

Quality improvement layer for prompt optimization.

**Pipeline stages:**
1. **Intent Classification** - Categorize prompts (research, coding, simple_query)
2. **Prompt Reshaping** - Rewrite for optimization (scaffold, LLM calls planned)
3. **Chain-of-Verification (CoVe)** - Multi-step verification framework
4. **Memory Storage** - Store artifacts for future tuning

**Location:** `prompting/`

**Environment flags:**
- `PROMPTING_ENABLE_RESHAPE` (default: false)
- `PROMPTING_ENABLE_COVE` (default: false)

---

## Milton Outputs Web Viewer

Browse and download Milton's output files from your iPhone or any device on your Tailscale network.

**Quick Setup:**
```bash
sudo ./scripts/setup_milton_outputs_server.sh
```

**Access URL:** `http://100.117.64.117:8090/`

This sets up a persistent, Tailscale-only Nginx server with:
- Read-only directory listing of `milton_outputs/` (symlinked to `shared_outputs/`)
- Restricted to Tailscale CGNAT range (100.64.0.0/10)
- Survives reboots (systemd-managed)
- No public internet exposure

See [docs/milton_outputs_server.md](docs/milton_outputs_server.md) for detailed documentation.

---

## Usage

### Interactive Agent Chat

```python
from agents.nexus import NEXUS

nexus = NEXUS()

# NEXUS routes automatically based on request type
response = nexus.process_message("What's the weather today?")
# -> Routes to Weather API integration

response = nexus.process_message("Find recent papers on reinforcement learning")
# -> Routes to FRONTIER agent -> arXiv search

response = nexus.process_message("Write a Python function to parse CSV files")
# -> Routes to CORTEX agent -> code generation
```

### Morning Automation

```bash
# Install daily OS systemd timers (evening capture, overnight queue, morning briefing)
bash scripts/systemd/install_daily_os.sh

# Verify timers are active
systemctl --user list-timers | grep milton

# View logs
journalctl --user -u milton-nexus-morning.service -f
```

### Overnight Job Queue

```bash
# Queue a job before bed
python - <<'PY'
from milton_queue import enqueue_job
enqueue_job("cortex_task", {"task": "Analyze yesterday's experiment data"}, priority="high")
PY

# Job processes automatically between 10 PM - 6 AM
# Check results in the morning
ls job_queue/archive/
```

### Memory Operations

```python
from memory.operations import MemoryOperations

with MemoryOperations() as mem:
    # Store short-term memory
    mem.add_short_term(
        agent="nexus",
        content="User prefers neuroscience papers over ML theory",
        context="preference_learning"
    )

    # Retrieve recent memories
    recent = mem.get_recent_short_term(hours=24, agent="nexus")

    # Add long-term fact
    mem.add_long_term(
        category="preference",
        summary="Interested in: RL, neuroscience, protein folding",
        importance=0.9,
        tags=["research_interests"]
    )
```

---

## Key Features

### Reminders + Notifications

**Milton includes a first-class reminders system:**
- **Persistent reminders** stored in SQLite (survive restarts)
- **Push notifications** via ntfy (works on iOS/Android)
- **Timezone-aware** scheduling (America/New_York by default)
- **Natural language** parsing ("tomorrow at 9am", "in 2 hours")
- **Automatic retries** with exponential backoff
- **Multiple interfaces** - CLI, NEXUS agent, or orchestrator

**Quick example:**
```bash
# Terminal 1: Start scheduler
milton-reminders run

# Terminal 2: Create reminders
milton-reminders add "Team standup" --when "tomorrow at 9am"
milton-reminders add "Check build" --when "in 30 minutes"

# Or ask NEXUS
"remind me to call Bob in 2 hours"
```

**See [docs/reminders.md](docs/reminders.md) for complete setup guide.**

### Privacy-First (Local Execution)

**All inference runs on your hardware:**
- vLLM server: `localhost:8000` (never touches internet)
- Weaviate DB: `localhost:8080` (data stays local)
- Only public APIs called: arXiv, OpenWeather (no private data sent)

**Prove it yourself:**
```bash
# Monitor network traffic during agent operation
sudo tcpdump -i any port 443 | grep -v "arxiv\|openweathermap"
# Should show zero traffic to AI cloud providers
```

### Persistent Memory (Learns Over Time)

Milton remembers:
- Your research interests (extracted from queries)
- Common workflows (morning routine, analysis patterns)
- Preferred output formats
- Past conversations and decisions

**Memory grows smarter:**
- Week 1: Generic responses
- Week 4: Personalized recommendations based on your actual usage

### Reproducible Outputs

Every CORTEX output includes full provenance:
```json
{
  "result": "...",
  "provenance": {
    "git_commit": "5e76f05",
    "packages": {"torch": "2.9.0", "numpy": "2.0.0"},
    "random_seed": 42,
    "timestamp": "2025-12-30T22:00:00Z",
    "model": "llama31-8b-instruct"
  }
}
```

Re-run the same job 90 days later -> **bit-identical results**.

### Overnight Automation

Schedule long-running tasks to execute while you sleep:
- **Morning briefing**: 8:00 AM (weather + news + arXiv papers)
- **Research discovery**: 8:15 AM (FRONTIER scans new publications)
- **Job processor**: 10 PM - 6 AM every 30 min (CORTEX executes queued tasks)

Wake up to completed analysis, not running scripts.

### Zero Marginal Cost

**No per-token pricing:**
- ChatGPT Plus: $20/month (limited queries)
- GPT-4 API: $0.03/1K tokens (expensive at scale)
- **Milton: Electricity only** (~$0.50/day for RTX 5090)

**1000 queries/month:**
- GPT-4 API: ~$500/month
- Milton: ~$15/month (electricity)

**33x cheaper at high volume.**

---

## Testing

Milton includes 71+ test files covering unit tests, integration tests, and end-to-end validation.

### Test Coverage

| Category | Files | Purpose |
|----------|-------|---------|
| Phase 2 Integration | `test_phase2.py` | vLLM, Weaviate, agents validation |
| NEXUS Tests | `test_nexus_*.py` | Routing, context, tool registry |
| CORTEX Tests | `test_cortex_*.py` | Execution and memory integration |
| FRONTIER Tests | `test_frontier.py` | Research discovery |
| Memory Tests | `test_memory_*.py` | CRUD, compression, retrieval |
| Reminders Tests | `test_reminders.py` | Scheduling and notifications |
| Orchestrator Tests | `test_orchestrator_*.py` | Workflows |
| Prompting Tests | `test_prompting_*.py` | Pipeline and CoVe |
| Dashboard Tests | `test_dashboard_api.py` | API endpoints |

### Running Tests

```bash
# Quick validation
python tests/test_phase2.py

# Integration tests (opt-in; network/external services)
pytest -q -m "not integration"
RUN_INTEGRATION=1 pytest -q -m integration
# Integration selection includes system-level or long-running tests; use -m integration explicitly.

# Full test suite
pytest -q

# With coverage
pytest --cov=agents,memory,milton_orchestrator

# Specific test
pytest tests/test_nexus_routing.py -v
```

---

## Project Structure

```
milton/
├── agents/                  # Core agent implementations
│   ├── nexus.py            # NEXUS - Orchestrator & router
│   ├── cortex.py           # CORTEX - Executor & job processor
│   ├── frontier.py         # FRONTIER - Research discovery
│   ├── base.py             # Base agent class
│   ├── contracts.py        # Data models (TaskRequest, TaskResult, etc.)
│   ├── memory_hooks.py     # Memory integration
│   └── tool_registry.py    # Tool definition registry
│
├── memory/                  # 3-tier memory system
│   ├── operations.py       # CRUD operations for all tiers
│   ├── init_db.py          # Weaviate schema initialization
│   ├── backends.py         # Weaviate + JSONL dual backends
│   ├── retrieve.py         # Query execution & ranking
│   ├── store.py            # Persistence layer
│   ├── compress.py         # Memory compression
│   └── schema.py           # Memory item schemas
│
├── integrations/            # External API integrations
│   ├── weather.py          # OpenWeatherMap
│   ├── arxiv_api.py        # arXiv paper search
│   ├── news_api.py         # News headlines
│   ├── calendar.py         # Google Calendar (OAuth2)
│   ├── home_assistant.py   # Smart home control
│   └── web_search.py       # Web search
│
├── milton_orchestrator/     # Voice-to-code orchestrator
│   ├── orchestrator.py     # Main loop & request processing
│   ├── ntfy_client.py      # ntfy subscription/publish
│   ├── claude_runner.py    # Claude Code CLI wrapper
│   ├── codex_runner.py     # Codex CLI wrapper
│   ├── reminders.py        # Reminder scheduling
│   └── config.py           # Configuration management
│
├── milton-dashboard/        # React TypeScript dashboard
│   ├── src/
│   │   ├── components/     # ChatPanel, DashboardPanel, etc.
│   │   ├── api.ts          # REST + WebSocket client
│   │   └── App.tsx         # Main application
│   ├── package.json
│   └── vite.config.ts
│
├── prompting/               # Prompt middleware
│   ├── pipeline.py         # Main pipeline orchestrator
│   ├── classifier.py       # Intent classification
│   ├── reshape.py          # Prompt optimization
│   └── cove.py             # Chain-of-Verification
│
├── training/                # LoRA fine-tuning (Phase 3)
│   ├── continuous_trainer.py
│   ├── data_pipeline.py
│   ├── eval_metrics.py
│   └── adapter_manager.py
│
├── deployment/              # Edge deployment tools
│   ├── deployment_manager.py
│   └── edge_packager.py
│
├── benchmarks/              # Performance measurement
│
├── scripts/                 # Automation scripts
│   ├── start_vllm.py       # vLLM server launcher
│   ├── nexus_morning.py    # Morning briefing
│   ├── evening_briefing.py # Evening context capture
│   ├── job_processor.py    # Overnight queue processor
│   ├── healthcheck.py      # System health verification
│   ├── dev_up.sh           # Start all services
│   └── dev_down.sh         # Stop all services
│
├── systemd/                 # Service & timer units
│   ├── milton-morning-briefing.service
│   ├── milton-evening-briefing.service
│   └── milton-job-processor.service
│
├── tests/                   # 71+ test files
│
├── docs/                    # 50+ documentation files
│
├── job_queue/               # Overnight task queue
│   ├── tonight/            # Pending jobs
│   └── archive/            # Completed jobs
│
├── inbox/                   # Agent outputs
│   └── morning/            # Daily briefings
│
├── output/                  # Consolidated job results
│
├── data/                    # Memory JSONL fallback
│   └── memory/
│
├── logs/                    # Runtime logs (gitignored)
│
├── models/                  # LLM weights (gitignored)
│
├── Prompts/                 # Agent system prompts (gitignored)
│
├── docker-compose.yml       # Weaviate service
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Package metadata
├── phd_context.py          # PhD timeline & context
├── milton_queue.py         # Job queue API
├── .env.example            # Environment template
└── SECURITY.md             # Security policy
```

---

## Configuration

### Environment Variables (.env)

**Required:**
- `PERPLEXITY_API_KEY` - For orchestrator research
- `TARGET_REPO` - Where Claude Code makes changes

**LLM Configuration:**
- `LLM_API_URL` - vLLM server (default: http://localhost:8000)
- `LLM_MODEL` - Model name (default: llama31-8b-instruct)

**Memory:**
- `WEAVIATE_URL` - Weaviate endpoint (default: http://localhost:8080)

**Mobile/Orchestrator:**
- `NTFY_BASE_URL` - ntfy server (default: https://ntfy.sh)
- `ASK_TOPIC` - Incoming request topic
- `ANSWER_TOPIC` - Response topic
- `OUTPUT_BASE_URL` - Tailscale click-to-open base URL

**Integrations:**
- `OPENWEATHER_API_KEY` - Weather API
- `WEATHER_LAT`, `WEATHER_LON` - Coordinates
- `NEWS_API_KEY` - News API

**Feature Flags:**
- `PROMPTING_ENABLE_RESHAPE` - Enable prompt optimization
- `PROMPTING_ENABLE_COVE` - Enable verification
- `ENABLE_PREFIX_ROUTING` - Use CLAUDE:/CODEX: prefixes

### State Directory

Runtime state defaults to `~/.local/state/milton/`:
```
~/.local/state/milton/
├── logs/
├── job_queue/
├── inbox/
├── outputs/
├── reminders.sqlite3
└── goals/
```

Override with `STATE_DIR` environment variable.

---

## Roadmap

### Phase 2 (COMPLETE - December 2025)

- [x] vLLM inference with Llama-3.1-8B
- [x] Weaviate 3-tier memory system
- [x] All 3 agents operational (NEXUS/CORTEX/FRONTIER)
- [x] Integration tests passing (71+ test files)
- [x] Systemd automation scripts
- [x] Health monitoring
- [x] Milton Dashboard (React/TypeScript)
- [x] Milton Orchestrator (ntfy + Claude/Codex)
- [x] Reminders system

### Phase 3 (Q1 2026 - In Planning)

**Three-Prong Self-Improvement Strategy:**

1. **Memory System** (Prong 1) - Enhanced semantic search and context injection
   - [ ] Vector embeddings for conversations
   - [ ] Automated importance scoring
   - [ ] Context-aware response generation
   - [ ] Daily short-term -> working memory compression
   - [ ] Weekly working -> long-term compression

2. **Continuous Training** (Prong 2) - Weekly LoRA fine-tuning on your conversations
   - [ ] LoRA training pipeline (PEFT)
   - [ ] Automated daily/weekly retraining scheduler
   - [ ] Quality validation and rollback
   - [ ] Personalized model adapters

3. **Model Evolution** (Prong 3) - Systematic compression for edge deployment
   - [ ] Knowledge distillation from larger models
   - [ ] Progressive pruning (reduce model size)
   - [ ] 4-bit quantization (GPTQ/GGUF)
   - [ ] Raspberry Pi 5 / laptop deployment

**See detailed implementation plan:** [Three-Prong Roadmap](docs/03-roadmap.md)

**Priority: Edge Deployment**
- [ ] Laptop-optimized mode (CPU fallback)
- [ ] Expand from 10K users (GPU owners) to 10M (any laptop)
- [ ] One-click installer (Docker Compose bundle)
- [ ] Windows/Mac/Linux binaries

### Phase 4 (2026+ - Vision)

- Agent marketplace (buy/sell custom agents)
- Continuous learning from usage patterns
- Multi-user support (lab-wide deployment)
- Cloud-hosted option for users without GPUs

---

## Technical Details

### Hardware Requirements

**Current (Phase 2 - Llama-3.1-8B):**
- GPU: 12GB+ VRAM (RTX 3090, 4090, 5090)
- RAM: 32GB+ system memory
- Storage: 50GB for model + 20GB for memory DB

**Future (Phase 3 - Edge Optimized):**
- GPU: Optional (CPU fallback)
- RAM: 8GB (Raspberry Pi 5 target)
- Storage: 10GB (quantized model)

### Model Configuration

**Phase 2:** Llama-3.1-8B-Instruct
- Served name: `llama31-8b-instruct`
- Quantization: None (bfloat16)
- Context: 8192 tokens
- GPU utilization: 90% (RTX 5090)

**Phase 3 (planned):** Qwen3-30B or Llama-3.1-30B
- Better reasoning for multi-agent routing
- Longer context (32K tokens)
- Quantized to 4-bit for edge devices

### API Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| vLLM | 8000 | OpenAI-compatible inference API |
| Weaviate | 8080 | Vector database (HTTP) |
| Dashboard API | 5000 | Flask REST + WebSocket |
| Outputs Server | 8090 | Tailscale file browser |

### Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `vllm` | Local LLM inference | >=0.13.0 |
| `torch` | Deep learning | >=2.9.0 |
| `weaviate-client` | Vector DB | >=4.0.0 |
| `flask` | Web API | >=3.0.0 |
| `pydantic` | Data validation | >=2.0.0 |
| `apscheduler` | Job scheduling | >=3.10.0 |
| `dateparser` | Natural language time | >=1.2.0 |

---

## Documentation

### System Summary (Single Source of Truth)
- **[Milton System Summary](docs/MILTON_SYSTEM_SUMMARY.md)** - Comprehensive current-state architecture

### Three-Prong Self-Improvement Strategy
- **[Documentation Hub](docs/index.md)** - Complete documentation index
- **[Vision & Three-Prong Strategy](docs/01-vision.md)** - High-level approach to continuous learning
- **[Current System State](docs/02-current-state.md)** - Gap analysis and implementation status
- **[90-Day Roadmap](docs/03-roadmap.md)** - Detailed implementation plan
- **[Technical Architecture](docs/04-architecture.md)** - System design and data flow

### Features & Capabilities
- **[Reminders System](docs/reminders.md)** - Persistent reminders + push notifications
- **[Prompting Middleware](prompting/README.md)** - Prompt reshaping + Chain-of-Verification

### Current System (Phase 2)
- **[Phase 2 Deployment Guide](docs/PHASE2_DEPLOYMENT.md)** - Step-by-step setup
- **[Phase 2 Completion Report](docs/PHASE2_COMPLETE.md)** - Test results & validation
- **[System Documentation](docs/SYSTEM_DOCUMENTATION.md)** - Architecture deep-dive
- **[Memory Spec](docs/MEMORY_SPEC.md)** - Memory storage + retrieval rules
- **[Agent Context Rules](docs/AGENT_CONTEXT_RULES.md)** - Evidence-backed context + routing
- **[Daily OS Loop](docs/DAILY_OS.md)** - Goals, overnight queue, briefings
- **[iOS Output Access](docs/IOS_OUTPUT_ACCESS.md)** - Tailnet click-to-open outputs
- **[Orchestrator Quickstart](docs/ORCHESTRATOR_QUICKSTART.md)** - ntfy + Tailscale setup

### PhD System
- **[PhD Briefing System](docs/PHD_BRIEFING_SYSTEM.md)** - PhD context awareness
- **[PhD System-Wide Integration](docs/PHD_SYSTEM_WIDE_INTEGRATION.md)** - How PhD awareness works

---

## FAQ

**Q: Do I need 3 GPUs for 3 agents?**
A: No! All 3 agents share 1 vLLM server on 1 GPU. They make HTTP requests concurrently.

**Q: Can I use a smaller model than 8B?**
A: Yes, but routing quality degrades. 1B-3B models struggle with multi-agent coordination. 8B is the minimum recommended.

**Q: Does Milton work without internet?**
A: Partially. Inference and memory work offline. External integrations (Weather, arXiv) require internet for fresh data but use cached results as fallback.

**Q: How do I upgrade to a bigger model?**
A: Change `model_path` in `scripts/start_vllm.py` and update `LLM_MODEL` in `.env`. Restart vLLM server. Larger models need more VRAM.

**Q: Can I deploy this for my research lab?**
A: Phase 3 will add multi-user support. Current version is single-user.

**Q: Is this just a wrapper around OpenAI API?**
A: No! Milton uses **local vLLM inference** (no OpenAI dependency). The API is OpenAI-*compatible* for ease of use, but runs entirely on your hardware.

**Q: How does memory compression work?**
A: Phase 3 feature (in development). Every 24h, short-term memories summarize into working memory. Every 7 days, working memory compresses into long-term with importance scoring.

---

## Contributing

This is currently a private research project. Phase 3 will open-source the core system (Apache 2.0 license).

---

## License

**Phase 2:** Private research project
**Phase 3 (planned):** Apache 2.0 (core), Commercial licenses for enterprise features

---

## Acknowledgments

- **vLLM** - Fast local LLM inference ([github.com/vllm-project/vllm](https://github.com/vllm-project/vllm))
- **Weaviate** - Vector database for memory ([weaviate.io](https://weaviate.io))
- **Meta AI** - Llama 3.1 models ([ai.meta.com/llama](https://ai.meta.com/llama))

---

**Status:** Phase 2 Complete - All Systems Operational (December 2025)

**Next Milestone:** Phase 3 Month 1 - Memory compression + pilot users + competitive benchmarks
