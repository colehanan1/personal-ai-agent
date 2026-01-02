# Milton Agent System - Implementation Plan v1.0

## Overview
Build production-grade multi-agent system within existing Milton repo, following SHARED_CONTEXT v1.1 architecture.

**Status**: Planning phase - awaiting approval before implementation

---

## Current State Assessment

### ✓ Already Have
- `/Prompts/` - Complete agent prompts (SHARED_CONTEXT, NEXUS, CORTEX, FRONTIER)
- `/integrations/weather.py` - Working OpenWeatherMap integration
- `/integrations/arxiv_api.py` - Working arXiv integration
- `schemas.py` - JSON output format structure
- `morning_briefing.py` - Basic briefing generator
- `.env` - API keys (weather configured)

### ✗ Need to Build
- Agent runtime system (NEXUS, CORTEX, FRONTIER)
- Memory system (3-tier)
- Goal tracking system
- Overnight queue system
- Missing integrations (Home Assistant, markets, news, hockey)
- Briefing workflows (morning/evening)
- LLM interface (vLLM server setup)

---

## Architecture Decision Points

### 1. LLM Backend
**Question**: Which LLM setup should we use?

**Options**:
- **A. vLLM + Llama 3.1 8B** (current production standard)
  - Pros: Good performance, reasonable resource usage, local, privacy
  - Cons: Requires ~16GB VRAM, setup complexity
  - Time: ~10 min download + setup

- **B. Ollama + Llama 3.1 8B** (alternative for testing)
  - Pros: Quick setup, works on standard hardware
  - Cons: Slightly slower than vLLM
  - Time: ~5 min setup

- **C. vLLM + Llama 3.1 405B** (future/optional upgrade)
  - Pros: Most powerful for complex reasoning
  - Cons: Requires 250GB download, ~90GB RAM, complex setup
  - Time: ~30 min download + setup

**Current Standard**: **Option A (vLLM + 8B)** is the production target. Option C (405B) can be considered for future upgrades if needed.

### 2. Memory System
**Question**: How should we store memory?

**Options**:
- **A. Simple file-based** (JSON/YAML files)
  - Pros: Simple, no dependencies, easy to debug
  - Cons: No vector search, manual compression
  - Structure: `memory/{short-term,working,long-term}/*.json`

- **B. SQLite database**
  - Pros: Structured queries, relationships, good for goals
  - Cons: No semantic search

- **C. Weaviate vector DB** (per original request)
  - Pros: Semantic search, compression, scalable
  - Cons: Docker dependency, more complex
  - Time: Additional setup

**Recommendation**: Start with **Option A (file-based)** for MVP, migrate to Option C later if needed.

### 3. Goal Tracking
**Question**: How complex should goal tracking be?

**Options**:
- **A. Simple YAML files** (per SHARED_CONTEXT spec)
  - Files: `goals/current/{monthly,weekly,daily}.yaml`
  - Manual updates via NEXUS conversations

- **B. Database with relationships**
  - Track dependencies, progress, time estimates
  - Automated rollover and archiving

**Recommendation**: **Option A** - matches SHARED_CONTEXT spec perfectly.

### 4. Overnight Queue
**Question**: How should overnight jobs work?

**Options**:
- **A. APScheduler** (Python library)
  - Pros: Full-featured, persistent, built-in
  - Cons: Requires always-running process

- **B. Cron + file queue**
  - Pros: OS-native, simple
  - Cons: Less flexible, harder to manage

- **C. Simple file queue** (check at 10 PM)
  - Pros: Dead simple, no daemon needed
  - Cons: No scheduling flexibility

**Recommendation**: **Option C** initially, upgrade to **Option A** if needed.

---

## Implementation Phases

### Phase 1: Foundation (2-3 hours)
**Goal**: Get basic NEXUS working with existing integrations

#### Tasks:
1. **LLM Setup** (30 min)
   - [ ] Install Ollama
   - [ ] Pull Llama 3.1 8B model
   - [ ] Test inference
   - [ ] Update `.env` with LLM_API_URL

2. **Agent Base Class** (30 min)
   - [ ] ✓ Already created: `agents/base.py`
   - [ ] Test prompt loading from `Prompts/`
   - [ ] Test LLM calls

3. **NEXUS Agent** (1 hour)
   - [ ] Create `agents/nexus.py`
   - [ ] Implement routing logic (answer | tool | delegate)
   - [ ] Integrate existing weather API
   - [ ] Integrate existing arXiv API
   - [ ] Test basic conversation

4. **Schemas Update** (30 min)
   - [ ] Expand `schemas.py` with all report types
   - [ ] Add validation functions
   - [ ] Test JSON output format

**Deliverable**: Working NEXUS agent that can answer questions, fetch weather, and find papers.

**Test**:
```python
from agents.nexus import NEXUS
nexus = NEXUS()
print(nexus.generate("What's the weather?"))
print(nexus.generate("Find me 3 papers on dopamine in Drosophila"))
```

---

### Phase 2: Briefings & Memory (2-3 hours)
**Goal**: Morning briefings with persistent memory

#### Tasks:
1. **Memory System** (1 hour)
   - [ ] Create `memory/` package
   - [ ] Implement file-based storage
   - [ ] Short-term: JSON files with timestamps
   - [ ] Working memory: Active task tracking
   - [ ] Long-term: Compressed summaries
   - [ ] Test CRUD operations

2. **Morning Briefing** (1 hour)
   - [ ] Refactor existing `morning_briefing.py`
   - [ ] Add 3-phase delivery (per SHARED_CONTEXT)
   - [ ] Phase 1: Weather + sports
   - [ ] Phase 2: Markets + papers
   - [ ] Phase 3: Overnight results + priorities
   - [ ] Save to `inbox/morning/`

3. **Evening Briefing** (1 hour)
   - [ ] Create `evening_briefing.py`
   - [ ] Day review
   - [ ] Tomorrow planning
   - [ ] Capture mode ("Anything on your mind?")
   - [ ] Queue confirmation
   - [ ] Save to `inbox/evening/`

**Deliverable**: Automated morning/evening briefings saved to inbox.

**Test**:
```bash
python morning_briefing.py  # Generates phase 1-3
python evening_briefing.py  # Reviews day, plans tomorrow
```

---

### Phase 3: Goals & Queue (1-2 hours)
**Goal**: Track goals and queue overnight jobs

#### Tasks:
1. **Goal Tracking** (1 hour)
   - [ ] Create `goals/` package
   - [ ] YAML schema: monthly/weekly/daily
   - [ ] NEXUS integration: "Daily, weekly, or monthly?"
   - [ ] Update functions (add, complete, defer)
   - [ ] Archive old goals

2. **Overnight Queue** (1 hour)
   - [ ] Create `queue/` package
   - [ ] Simple file-based queue: `queue/tonight/*.json`
   - [ ] CORTEX reads queue at 10 PM
   - [ ] Archive completed: `queue/archive/`
   - [ ] Status tracking

**Deliverable**: Goal tracking through NEXUS conversations, overnight job queueing.

**Test**:
```python
nexus.generate("I need to finish thesis slides by Jan 15")
# NEXUS: "Daily, weekly, or monthly?"
# User: "Monthly"
# Creates goal in goals/current/monthly.yaml
```

---

### Phase 4: CORTEX & FRONTIER (2-3 hours)
**Goal**: Add executor and discovery agents

#### Tasks:
1. **CORTEX Agent** (1.5 hours)
   - [ ] Create `agents/cortex.py`
   - [ ] Work plan generation
   - [ ] Code generation (with templates)
   - [ ] Overnight execution workflow
   - [ ] Report generation (JSON format)
   - [ ] Infrastructure monitoring stubs

2. **FRONTIER Agent** (1.5 hours)
   - [ ] Create `agents/frontier.py`
   - [ ] Paper monitoring (enhanced arXiv)
   - [ ] Discovery reports
   - [ ] Opportunity memos
   - [ ] Weekly brief generation

**Deliverable**: All three agents operational.

**Test**:
```python
from agents.cortex import CORTEX
cortex = CORTEX()
plan = cortex.generate_work_plan("Optimize hyperparameters with Optuna")

from agents.frontier import FRONTIER
frontier = FRONTIER()
papers = frontier.find_relevant_papers("Drosophila olfaction")
```

---

### Phase 5: Missing Integrations (2-3 hours)
**Goal**: Add all remaining integrations

#### Tasks:
1. **Home Assistant** (45 min)
   - [ ] Create `integrations/home_assistant.py`
   - [ ] Basic API wrapper (lights, thermostat, plugs)
   - [ ] Entity state queries
   - [ ] Service calls
   - [ ] Add HA credentials to `.env`

2. **Markets** (30 min)
   - [ ] Create `integrations/markets.py`
   - [ ] S&P 500, NASDAQ endpoints
   - [ ] Daily summaries
   - [ ] Free API or scraping

3. **News** (30 min)
   - [ ] Create `integrations/news.py`
   - [ ] RSS feeds or NewsAPI
   - [ ] AI/neuro filters
   - [ ] Deduplication

4. **Hockey** (30 min)
   - [ ] Create `integrations/hockey.py`
   - [ ] NHL API (free)
   - [ ] Team scores, schedule
   - [ ] Game summaries

**Deliverable**: All integrations working, tested individually.

---

### Phase 6: Polish & Testing (1-2 hours)
**Goal**: Testing, documentation, deployment

#### Tasks:
1. **Test Suite** (1 hour)
   - [ ] Create `tests/` directory
   - [ ] Unit tests for each integration
   - [ ] Agent conversation tests
   - [ ] Briefing generation tests
   - [ ] End-to-end workflow test

2. **Documentation** (30 min)
   - [ ] Update README.md
   - [ ] Add USAGE.md with examples
   - [ ] Document .env variables
   - [ ] Add troubleshooting guide

3. **Scripts** (30 min)
   - [ ] `scripts/start_vllm.py` (if using vLLM)
   - [ ] `scripts/setup.sh` (initial setup)
   - [ ] `scripts/test_all.sh` (run all tests)

**Deliverable**: Fully tested, documented system ready for daily use.

---

## File Structure (Final)

```
milton/
├── .env                          # API keys & config
├── README.md                     # Updated with new system
├── IMPLEMENTATION_PLAN.md        # This file
│
├── Prompts/                      # ✓ Existing
│   ├── SHARED_CONTEXT.md
│   ├── NEXUS_v1.1.md
│   ├── CORTEX_v1.1.md
│   ├── FRONTIER_v1.1.md
│   └── MASTER_DEPLOY.md
│
├── agents/                       # NEW
│   ├── __init__.py              # ✓ Prompt loader
│   ├── base.py                  # ✓ Base agent class
│   ├── nexus.py                 # Hub agent
│   ├── cortex.py                # Executor agent
│   └── frontier.py              # Scout agent
│
├── integrations/                 # Expand existing
│   ├── __init__.py
│   ├── weather.py               # ✓ Existing
│   ├── arxiv_api.py             # ✓ Existing
│   ├── home_assistant.py        # NEW
│   ├── markets.py               # NEW
│   ├── news.py                  # NEW
│   └── hockey.py                # NEW
│
├── memory/                       # NEW
│   ├── __init__.py
│   ├── short_term/              # Recent (24-48h)
│   ├── working/                 # Active tasks
│   └── long_term/               # Compressed summaries
│
├── goals/                        # NEW
│   ├── current/
│   │   ├── monthly.yaml
│   │   ├── weekly.yaml
│   │   └── daily.yaml
│   └── archive/
│
├── queue/                        # NEW
│   ├── tonight/                 # Jobs for tonight
│   └── archive/                 # Completed jobs
│
├── inbox/                        # ✓ Existing, expand
│   ├── morning/
│   ├── evening/
│   └── urgent/
│
├── outputs/                      # NEW
│   └── YYYYMMDD/               # Date-based outputs
│
├── logs/                         # NEW
│   ├── nexus/
│   ├── cortex/
│   └── frontier/
│
├── scripts/                      # NEW
│   ├── setup.sh
│   ├── start_vllm.py
│   └── test_all.sh
│
├── tests/                        # NEW
│   ├── test_agents.py
│   ├── test_integrations.py
│   └── test_briefings.py
│
├── schemas.py                    # ✓ Existing, expand
├── morning_briefing.py           # ✓ Refactor
└── evening_briefing.py           # NEW
```

---

## Environment Variables (.env)

```bash
# Current
WEATHER_API_KEY=187253855972163c4881236674f973d8
WEATHER_LOCATION=St. Louis,US

# Need to Add
LLM_API_URL=http://localhost:8000     # vLLM default (production)
LLM_MODEL=llama31-8b-instruct         # Production model (8B standard)

# Optional (Phase 5)
HOME_ASSISTANT_URL=http://localhost:8123
HOME_ASSISTANT_TOKEN=your_token_here
NEWS_API_KEY=your_key_here
HOCKEY_TEAM=STL  # St. Louis Blues?
```

---

## Time Estimates

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| 1. Foundation | LLM + NEXUS + Schemas | 2-3 hours |
| 2. Briefings & Memory | Morning/Evening + Storage | 2-3 hours |
| 3. Goals & Queue | Tracking + Overnight | 1-2 hours |
| 4. Agents | CORTEX + FRONTIER | 2-3 hours |
| 5. Integrations | HA + Markets + News + Hockey | 2-3 hours |
| 6. Polish | Tests + Docs | 1-2 hours |
| **Total** | | **10-16 hours** |

**Conservative estimate**: 2-3 work days if focused.

---

## Critical Decisions Needed

Before I start building, please decide:

### 1. LLM Backend
- [x] **Option A**: vLLM + Llama 8B (production standard - currently deployed)
- [ ] **Option B**: Ollama + Llama 8B (alternative for testing)
- [ ] **Option C**: vLLM + Llama 405B (future upgrade, optional)

### 2. Memory System
- [ ] **Option A**: File-based (simple, start here)
- [ ] **Option B**: SQLite (structured)
- [ ] **Option C**: Weaviate (vector DB, overkill for MVP?)

### 3. Implementation Order
- [ ] **Build in phases** (test each phase before moving on)
- [ ] **Build all at once** (faster but riskier)

### 4. Scope for MVP
Which phases are essential for your first working version?
- [ ] Phase 1: Foundation (**Required**)
- [ ] Phase 2: Briefings & Memory (**Recommended**)
- [ ] Phase 3: Goals & Queue (Nice to have)
- [ ] Phase 4: CORTEX & FRONTIER (Can defer)
- [ ] Phase 5: Integrations (Add as needed)
- [ ] Phase 6: Polish (Always last)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM setup fails | Blocker | Start with Ollama (easier than vLLM) |
| Insufficient VRAM for larger models | Can't upgrade from 8B | 8B is the production standard; larger models optional |
| Integration APIs change | Integrations break | Build with fallbacks |
| Overnight jobs fail silently | Miss results | Email/notify on failure |
| Complex memory system | Slow development | Start simple (files), upgrade later |

---

## Success Criteria

**MVP Complete When**:
✓ NEXUS responds to questions
✓ Morning briefing generates automatically
✓ Weather + arXiv data included
✓ Responses follow JSON schema
✓ Memory persists between sessions
✓ Goals tracked in YAML files

**Production Ready When**:
✓ All three agents operational
✓ Evening briefings working
✓ Overnight queue functional
✓ All integrations connected
✓ Test suite passing
✓ Documentation complete

---

## Questions for You

1. **Which LLM option** do you want to start with? (A, B, or C)

2. **Which phases** are must-have for your first version? (1-2? 1-3? All?)

3. **St. Louis** - Is that your current location? (For weather/hockey/local data)

4. **Home Assistant** - Do you have this set up? If so, I'll prioritize that integration.

5. **Hardware** - The prompts mention "AMD 9950X, RTX 5090, 128GB RAM" - is that accurate? (Affects LLM choice)

6. **Timeline** - Do you want me to:
   - Build Phase 1 today and get your feedback?
   - Build everything and present completed system?
   - Build incrementally with approval at each phase?

---

## Approval Checklist

Before I proceed, please confirm:

- [ ] Architecture decisions reviewed (LLM, memory, queue)
- [ ] File structure approved
- [ ] Phase ordering makes sense
- [ ] Time estimates reasonable
- [ ] Ready for me to start building

**Next Step**: Once approved, I'll start with Phase 1 (Foundation) and create a working NEXUS agent integrated with your existing weather/arXiv code.

---

*Implementation Plan v1.0 - December 30, 2024*
*Awaiting approval to proceed*
