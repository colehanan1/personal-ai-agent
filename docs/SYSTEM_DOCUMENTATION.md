# Agent System Documentation

## Overview
This folder contains a local multi-agent system built for research, automation,
and personal assistance. It runs a local LLM via vLLM, stores memory in Weaviate,
and schedules jobs with APScheduler. The main agents are:

- NEXUS: orchestration and briefing generation
- CORTEX: execution and code generation
- FRONTIER: research discovery and curation

## What Was Built
- Agent modules in `agents/` for NEXUS, CORTEX, and FRONTIER.
- Integrations for Home Assistant, OpenWeatherMap, arXiv, NewsAPI, and a Calendar stub in `integrations/`.
- Memory system backed by Weaviate in `memory/`.
- Job queue manager (APScheduler + SQLite) in `queue/`.
- Structured logging utilities in `logging/`.
- vLLM startup script in `scripts/`.
- Weaviate Docker Compose service in `docker-compose.yml`.
- Config and prompts in `config/`.
- Comprehensive test suite in `test_all_systems.py`.
- Setup documentation in `SETUP_INSTRUCTIONS.txt` and `SETUP_COMPLETE.txt`.

## Architecture and Data Flow

```
User input
   |
   v
NEXUS (route + briefings)
   |  \
   |   \--> Integrations (weather, news, home, calendar)
   |
   +--> CORTEX (execution, code, reports)
   |
   +--> FRONTIER (research discovery + briefs)
   |
   +--> vLLM (LLM inference, used by NEXUS/CORTEX/FRONTIER)
   |
   +--> Weaviate (short/working/long-term memory)
   |
   +--> APScheduler job queue (overnight jobs)
```

Key flows:
- Routing: `NEXUS.route_request()` calls the LLM to classify a request and returns a target.
- Briefings: NEXUS pulls weather/news/calendar/home status and composes a text briefing.
- Execution: CORTEX creates a plan, executes steps via LLM, and produces reports.
- Discovery: FRONTIER searches arXiv, optionally scores relevance, and saves briefs.
- Memory: Weaviate collections store short-term, working, and long-term entries.
- Jobs: APScheduler persists jobs in `queue/jobs.db` and runs them on schedule.

## Component Map (What Each File Does)

### Agents
- `agents/nexus.py`
  - Orchestrator that loads `config/system_prompts/NEXUS.md`.
  - Routes requests via LLM (`route_request`).
  - Generates morning/evening briefings and writes bedtime briefings to `inbox/evening/`.
- `agents/cortex.py`
  - Execution agent that creates work plans, runs step execution via LLM, and generates reports.
  - Includes a `run_script` helper and overnight job processing workflow.
- `agents/frontier.py`
  - Research discovery agent using arXiv and News.
  - Generates research briefs and writes them to `outputs/`.

### Integrations
- `integrations/home_assistant.py`
  - Home Assistant REST API wrapper with convenience helpers.
- `integrations/weather.py`
  - OpenWeatherMap wrapper for current weather and forecast.
- `integrations/arxiv.py`
  - arXiv search and response parsing.
- `integrations/news_api.py`
  - NewsAPI wrapper for headlines and search.
- `integrations/calendar.py`
  - Calendar stub (no OAuth yet).
- `integrations/__init__.py`
  - Re-exports integration classes for easy import.

### Memory System
- `memory/init_db.py`
  - Initializes Weaviate collections: ShortTermMemory, WorkingMemory, LongTermMemory.
- `memory/operations.py`
  - CRUD operations for each memory tier plus compression helpers.

### Job Queue
- `queue/job_manager.py`
  - APScheduler-backed job manager with SQLite persistence.
  - Supports one-time, recurring, and overnight jobs.
- `queue/__init__.py`
  - Re-exports the job manager.

### Logging
- `logging/setup.py`
  - Rotating file logging and optional console output.
  - Creates per-agent log directories in `logs/`.
- `logging/__init__.py`
  - Re-exports logging helpers.

### Scripts and Infrastructure
- `scripts/start_vllm.py`
  - Starts the vLLM OpenAI-compatible API server for Llama 3.1 8B (production target).
- `docker-compose.yml`
  - Weaviate service definition and persistent volume.
- `requirements.txt`
  - Python dependencies for the system.
- `test_all_systems.py`
  - End-to-end system validation (vLLM, Weaviate, memory, integrations, queue, logging).

### Configuration
- `config/.env`
  - Environment variables for API keys, model, and service URLs.
- `config/nexus.yaml`, `config/cortex.yaml`, `config/frontier.yaml`
  - Agent behavior settings (briefing times, research interests, job limits).
- `config/system_prompts/*.md`
  - LLM instruction prompts per agent plus shared context.

## How It Works End-to-End

1. Start core services:
   - vLLM server (`python scripts/start_vllm.py`)
   - Weaviate (`docker-compose up -d`)
2. Initialize memory schema (via `memory/init_db.py` or `test_all_systems.py`).
3. NEXUS processes user requests:
   - Uses LLM for routing.
   - Handles briefings and simple integration calls.
4. CORTEX executes multi-step tasks:
   - Generates a plan, executes steps via LLM, and produces a report.
5. FRONTIER discovers research:
   - Searches arXiv, formats briefs, and saves to `outputs/`.
6. Memory and queue persist state:
   - Memory stored in Weaviate.
   - Jobs stored in SQLite and executed by APScheduler.

## Operational Commands (Local)

```bash
# Start vLLM server
python scripts/start_vllm.py

# Start Weaviate
docker-compose up -d

# Run tests
python test_all_systems.py
```

## Limitations and Stubs
- Calendar integration is a stub; OAuth is not implemented yet.
- NEXUS routing currently returns a routing decision string, but does not invoke CORTEX or FRONTIER directly.
- Weaviate collections are configured with `Vectorizer.none()`, so searches are manual filters, not vector similarity.

## Extension Points
- Add a new integration: create `integrations/<name>.py`, export it in `integrations/__init__.py`, add config keys to `config/.env`, and add a test in `test_all_systems.py`.
- Add a new agent: create `agents/<name>.py`, add a system prompt in `config/system_prompts/`, and update NEXUS routing.
- Customize behavior: edit YAML files in `config/` and prompts in `config/system_prompts/`.

## Security Notes
- API keys are stored in `config/.env`. Keep this file local and private.
- Logs in `logs/` may contain request metadata. Review before sharing.
