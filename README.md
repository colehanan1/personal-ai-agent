# Milton

**NOTE**: This repository has been superseded by the **Cole's AI Agent System** located at `~/agent-system/`.

The original Milton was a simple morning-briefing helper. It has evolved into a production-grade multi-agent AI system with:
- **NEXUS** - Orchestration hub for briefings and request routing
- **CORTEX** - Execution agent for tasks and code generation
- **FRONTIER** - Research discovery agent for arXiv and news monitoring
- Full memory system (Weaviate vector DB)
- Job queue for overnight processing
- Integration with Home Assistant, Weather, arXiv, News APIs

## New System Location

The full agent system is now at:
```
~/agent-system/
```

See documentation:
- `~/agent-system/README.md` - Full system documentation
- `~/agent-system/SETUP_INSTRUCTIONS.txt` - Setup guide
- `~/agent-system/SETUP_COMPLETE.txt` - Setup summary

## Quick Start (New System)

1. Navigate to agent system:
   ```bash
   cd ~/agent-system
   ```

2. Follow setup instructions:
   ```bash
   cat SETUP_INSTRUCTIONS.txt
   ```

3. Start services and run tests:
   ```bash
   # Start vLLM server
   conda activate milton
   python scripts/start_vllm.py

   # Start Weaviate (in another terminal)
   docker-compose up -d

   # Run tests
   python test_all_systems.py
   ```

4. Generate your first briefing:
   ```python
   from agents.nexus import NEXUS
   nexus = NEXUS()
   print(nexus.generate_morning_briefing())
   ```

## Architecture

```
User (Cole) → NEXUS (orchestrator)
              ├─→ CORTEX (executor)
              ├─→ FRONTIER (discovery)
              └─→ Integrations (HA, Weather, arXiv, News)
```

**Infrastructure**:
- vLLM server (Llama 3.1 405B)
- Weaviate vector database
- APScheduler job queue
- Structured logging system

## Original Milton (Legacy)

The original simple briefing scripts are still in this directory but are deprecated in favor of the full agent system.

### Legacy Requirements
- Python 3.10+
- Dependencies: `requests`, `python-dotenv`, `feedparser`

### Legacy Setup
1) Create a `.env` in the repo root:
```
WEATHER_API_KEY=your_openweather_key
WEATHER_LOCATION=Newark,NJ
```

2) Install dependencies:
```
python3 -m pip install requests python-dotenv feedparser
```

### Legacy Usage
- Generate the JSON brief:
```
python3 morning_briefing.py
```

- Render a text summary:
```
python3 render_briefing.py
```

Output is written to `inbox/morning/brief_latest.json` and is ignored by git.

### Legacy Smoke checks
```
python3 test_weather.py
python3 test_arxiv.py
```

---

**Migration Note**: The legacy scripts still work but are no longer actively developed. All new features and improvements are in the `~/agent-system/` codebase.
