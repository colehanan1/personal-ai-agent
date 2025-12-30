# Milton - AI Agent System

Production-grade multi-agent AI system for Cole's research and automation needs.

## Overview

Milton is a three-agent system built on Llama 3.1 405B with persistent memory, job scheduling, and comprehensive integrations.

**Agents:**
- **NEXUS** - Orchestration hub for briefings and request routing
- **CORTEX** - Execution agent for tasks and code generation
- **FRONTIER** - Research discovery agent for arXiv and news monitoring

**Infrastructure:**
- vLLM server (local LLM inference with OpenAI-compatible API)
- Weaviate vector database (3-tier memory: short-term, working, long-term)
- APScheduler job queue (overnight processing with SQLite persistence)
- Structured logging system

**Integrations:**
- Weather API (OpenWeather)
- arXiv API (research paper discovery)
- News API (current events monitoring)
- Home Assistant (home automation control)
- Calendar API (scheduling, stub implementation)

## Quick Start

### 1. Install Dependencies

```bash
conda activate milton
pip install -r requirements.txt
```

### 2. Configure Environment

Edit [.env](.env) with your API keys:
```bash
# Already configured
WEATHER_API_KEY=<your_key>
WEATHER_LOCATION=St. Louis,US

# Add these if you have them
HOME_ASSISTANT_URL=http://your-ha-instance:8123
HOME_ASSISTANT_TOKEN=<your_token>
NEWS_API_KEY=<your_newsapi_key>
```

### 3. Start Services

```bash
# Start Weaviate (vector database)
docker-compose up -d

# Start vLLM server (in another terminal)
conda activate milton
python scripts/start_vllm.py
```

### 4. Test the System

```bash
conda activate milton
python test_all_systems.py
```

### 5. Generate Your First Briefing

```python
from agents.nexus import NEXUS

nexus = NEXUS()
briefing = nexus.generate_morning_briefing()
print(briefing)
```

## Architecture

```
User (Cole)
    ↓
NEXUS (orchestrator)
    ├─→ CORTEX (executor)
    ├─→ FRONTIER (discovery)
    └─→ Integrations (Weather, arXiv, News, HA, Calendar)
    └─→ Memory (Weaviate)
    └─→ Job Queue (APScheduler)
```

## Documentation

- [System Documentation](docs/SYSTEM_DOCUMENTATION.md) - Complete system overview
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) - Original implementation strategy
- [API Reference](docs/API_REFERENCE.md) - Integration APIs and usage (coming soon)

## Directory Structure

```
milton/
├── agents/              # Agent implementations (NEXUS, CORTEX, FRONTIER)
├── integrations/        # API wrappers (Weather, arXiv, News, HA, Calendar)
├── memory/              # Weaviate memory operations
├── job_queue/           # APScheduler job management
├── agent_logging/       # Structured logging setup
├── Prompts/             # System prompts (v1.1) - gitignored, local config
├── scripts/             # Utility scripts (vLLM startup, etc.)
├── docs/                # Documentation
├── logs/                # Runtime logs (gitignored)
├── outputs/             # Agent outputs (gitignored)
├── cache/               # Model cache (gitignored)
├── models/              # Model storage (gitignored)
└── goals/               # Goal tracking (gitignored)
```

## Development

### Running Tests

```bash
# Test all systems
python test_all_systems.py

# Test specific integration
python test_weather.py
python test_arxiv.py
```

### Adding New Integrations

1. Create a new file in [integrations/](integrations/)
2. Implement the API wrapper class
3. Add export to [integrations/__init__.py](integrations/__init__.py)
4. Update agent prompts if needed

### Modifying Agent Behavior

Agent system prompts are in `/Prompts/` (gitignored for local customization):
- `SHARED_CONTEXT.md` - Common context for all agents
- `NEXUS_v1.1.md` - NEXUS-specific instructions
- `CORTEX_v1.1.md` - CORTEX-specific instructions
- `FRONTIER_v1.1.md` - FRONTIER-specific instructions

See [MASTER_DEPLOY.md](Prompts/MASTER_DEPLOY.md) for prompt loading pattern.

## Hardware Requirements

**Recommended:**
- AMD Ryzen 9 9950X (or equivalent)
- NVIDIA RTX 5090 24GB (or 2x RTX 4090)
- 128GB RAM
- 500GB+ SSD for models

**Minimum:**
- 8-core CPU
- 24GB VRAM GPU
- 64GB RAM
- 200GB SSD

## License

Private research project - not licensed for public use.

---

**Status:** ✅ Fully migrated and operational (Dec 2024)
