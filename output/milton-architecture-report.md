# Milton System Architecture Report

**Generated:** 2025-12-31 18:26:21
**Repository:** /home/cole-hanan/milton

---

## 1. Introduction

### 1.1 System Overview

**Milton** is a privacy-first, local-first AI agent system designed for researchers and professionals who require:

- **Complete data privacy**: All LLM inference runs locally on user hardware with zero cloud dependency
- **Persistent memory**: A 3-tier memory architecture that learns user patterns and preferences over time
- **Reproducible outputs**: Full provenance tracking (git commits, package versions, random seeds)
- **Intelligent automation**: Scheduled overnight task processing and morning briefing generation
- **Cost efficiency**: No per-token pricing; unlimited queries at electricity-only costs

The system employs a **multi-agent architecture** with three specialized agents (NEXUS, CORTEX, FRONTIER) that share a single vLLM inference server for efficient resource utilization.

### 1.2 Purpose and Scope

Milton addresses the critical needs of:

- **Healthcare researchers**: HIPAA/GDPR-compliant analysis (no patient data leaves local machine)
- **Academic institutions**: Reproducible research with full computational provenance
- **Privacy-conscious users**: Full control over data and inference without cloud dependencies
- **High-volume users**: Cost-effective alternative to cloud LLM APIs (33x cheaper at scale)

**Current Status**: Phase 2 Complete (December 2025) - All agents operational, 6/6 integration tests passing

### 1.3 Key Terminology

| Term | Definition |
|------|------------|
| **NEXUS** | Orchestration agent responsible for routing requests and generating briefings |
| **CORTEX** | Execution agent that generates work plans, writes code, and processes jobs |
| **FRONTIER** | Research agent specialized in arXiv paper discovery and monitoring |
| **vLLM** | High-performance LLM inference server with OpenAI-compatible API |
| **Weaviate** | Vector database used for 3-tier memory system |
| **Job Queue** | Directory-based task queue for overnight batch processing |
| **Orchestrator** | Voice-to-code coordination layer with ntfy notifications |

## 2. Architecture Overview

### 2.1 Logical Architecture

Milton follows a **layered agent-based architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│             USER INTERFACE LAYER                        │
│  - CLI commands (milton-orchestrator)                   │
│  - ntfy notifications (mobile integration)              │
│  - Systemd timers (automation)                          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           ORCHESTRATION LAYER                           │
│  ┌──────────────┐     ┌─────────────────────┐          │
│  │  NEXUS Agent │◄────┤ Orchestrator Engine │          │
│  │  (Router)    │     │ - Request routing   │          │
│  └──────┬───────┘     │ - Perplexity fallback│         │
│         │             │ - Reminder system    │          │
│         │             └─────────────────────┘          │
│    ┌────┴─────┬──────────────┐                         │
│    ▼          ▼              ▼                         │
│ CORTEX    FRONTIER    Integrations                     │
│ (Executor) (Scout)   (Weather/News/arXiv)              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              INFERENCE LAYER                            │
│  ┌──────────────────────────────────────┐              │
│  │   vLLM Server (localhost:8000)       │              │
│  │   - Llama-3.1-8B-Instruct            │              │
│  │   - OpenAI-compatible API            │              │
│  │   - Shared by all agents             │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              PERSISTENCE LAYER                          │
│  ┌────────────────┐    ┌───────────────────┐           │
│  │ Weaviate DB    │    │ File System       │           │
│  │ (port 8080)    │    │ - Job queue/      │           │
│  │ - Short-term   │    │ - outputs/        │           │
│  │ - Working      │    │ - logs/           │           │
│  │ - Long-term    │    │ - models/         │           │
│  └────────────────┘    └───────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Physical Deployment

**Single-node deployment on local hardware:**

- **Host OS**: Linux (Ubuntu/Debian) with systemd
- **GPU**: NVIDIA RTX 5090 (12GB+ VRAM required)
- **RAM**: 32GB+ system memory
- **Storage**: 70GB+ (50GB models, 20GB memory DB)
- **Network**: Local-only by default (optional external API access for Weather/News)

**Process architecture:**

1. **vLLM server**: GPU-bound inference process (Python, started via `scripts/start_vllm.py`)
2. **Weaviate container**: Docker containerized vector database
3. **Agent processes**: On-demand Python processes invoked by automation or user
4. **Systemd timers**: Scheduled automation triggers (morning briefing at 8 AM, job processor 10 PM - 6 AM)

### 2.3 Data Flow Architecture

**Primary request flow (synchronous):**

```
User Input → Orchestrator → NEXUS.route_request()
                              ↓
                    [Routing decision]
                              ↓
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
      CORTEX              FRONTIER           Integration
   (execution)           (research)          (API call)
          │                   │                   │
          └───────────────────┴───────────────────┘
                              ↓
                    [vLLM API call]
                              ↓
                         Response
                              ↓
                    [Store in Memory]
                              ↓
                      Return to User
```

**Overnight job flow (asynchronous):**

```
User creates job_queue/tonight/task.json
          ↓
Systemd timer triggers (10 PM)
          ↓
scripts/job_processor.py scans queue
          ↓
CORTEX.process_overnight_job()
          ↓
Plan → Execute steps → Generate report
          ↓
Save to outputs/{job_id}/ with provenance
          ↓
Move job to job_queue/archive/
```

## 3. System Components

### 3.1 Agents Component

**Location**: `agents/`

**Description**: Multi-agent system with NEXUS orchestrator, CORTEX executor, and FRONTIER researcher

**Key Files**:

- `frontier.py`
- `nexus.py`
- `cortex.py`
- `base.py`

**Interfaces**:

- `NEXUS()`: Main orchestrator
  - `.route_request(user_input)` → routing decision
  - `.generate_morning_briefing()` → formatted briefing string
  - `.process_message(message)` → agent response

- `CORTEX()`: Execution agent
  - `.generate_plan(task)` → work plan JSON
  - `.write_code(task)` → generated code
  - `.process_overnight_job(job)` → execution report

- `FRONTIER()`: Research agent
  - `.search_papers(query)` → arXiv results
  - `.monitor_topics(topics)` → new publications

### 3.2 Integrations Component

**Location**: `integrations/`

**Description**: External API integrations: Weather, News, arXiv, Web Search, Calendar, Home Assistant

**Key Files**:

- `weather.py`
- `web_search.py`
- `calendar.py`
- `arxiv_api.py`
- `home_assistant.py`
- `news_api.py`

### 3.3 Memory Component

**Location**: `memory/`

**Description**: 3-tier memory system (short-term, working, long-term) using Weaviate vector DB

**Key Files**:

- `operations.py`
- `init_db.py`

**Memory Tiers**:

1. **Short-term** (24-48 hours): Recent conversations and context
2. **Working memory** (active tasks): Current projects and multi-turn interactions
3. **Long-term** (compressed): Learned patterns, preferences, research interests

**Operations** (`memory/operations.py`):

- `add_short_term(agent, content, context)` → store recent memory
- `get_recent_short_term(hours, agent)` → retrieve context
- `add_long_term(category, summary, importance, tags)` → persistent learning

### 3.4 Orchestrator Component

**Location**: `milton_orchestrator/`

**Description**: Voice-to-code orchestrator with ntfy, Perplexity integration, Claude Code runner

**Key Files**:

- `ntfy_client.py`
- `orchestrator.py`
- `perplexity_client.py`
- `ntfy_summarizer.py`
- `prompt_builder.py`
- `config.py`
- `claude_runner.py`
- `reminders.py`
- `cli.py`
- `codex_runner.py`

**Orchestrator Modes**:

1. **ntfy mode**: Voice-to-code via mobile notifications
2. **Perplexity fallback**: Switch to Perplexity API when Claude unavailable
3. **Codex mode**: Alternative code execution backend
4. **Reminder system**: Schedule future notifications

**Key Classes**:

- `Orchestrator`: Main coordination loop
- `ClaudeRunner`: Execute Claude Code commands
- `PerplexityClient`: Fallback LLM API
- `ReminderScheduler`: Time-based notification system

### 3.5 Automation Component

**Location**: `scripts/`

**Description**: Automation scripts: morning briefings, job processing, health checks, vLLM startup

**Key Files**:

- `start_vllm.py`
- `frontier_morning.py`
- `send_briefing_to_phone.py`
- `health_check.py`
- `schemas.py`
- `job_processor.py`
- `ask_from_phone.py`
- `render_briefing.py`
- `enhanced_morning_briefing.py`
- `morning_briefing.py`

### 3.6 Job_Queue Component

**Location**: `job_queue/`

**Description**: Overnight task queue with scheduled execution (10 PM - 6 AM)

### 3.7 Perplexity Component

**Location**: `perplexity_integration/`

**Description**: Perplexity API integration with structured prompting and context management

**Key Files**:

- `response_schemas.py`
- `context_manager.py`
- `api_client.py`
- `prompting_system.py`

## 4. Key Workflows

### 4.1 Morning Briefing Workflow

**Trigger**: Systemd timer at 8:00 AM daily

**Sequence**:

1. `scripts/nexus_morning.py` invoked by systemd
2. NEXUS agent instantiated
3. Parallel API calls:
   - `WeatherAPI.format_current_weather()` → local forecast
   - `NewsAPI.get_top_headlines(category='technology')` → tech news
   - `CalendarAPI.get_today_events()` → schedule
   - `HomeAssistantAPI` → smart home status (if configured)
4. NEXUS formats combined briefing (70-character width)
5. Save to `inbox/morning/brief_YYYYMMDD.json`
6. Optional: Send to phone via ntfy notification

### 4.2 Code Execution via Orchestrator

**User sends voice message via ntfy:**

1. User publishes to ntfy topic (e.g., `milton-requests`)
2. `Orchestrator.subscribe_topics_with_reconnect()` receives message
3. Deduplicate via `RequestTracker.is_processed(message_id)`
4. Parse command: Check for reminder syntax or code request
5. If code request:
   - `PerplexityClient` (optional): Enhance prompt with structured context
   - `ClaudePromptBuilder.build_prompt()`: Inject repo context
   - `ClaudeRunner.run_once()`: Execute Claude Code with `--dangerously-skip-permissions`
6. Capture output and save to `outputs/{timestamp}/`
7. Publish result summary to ntfy `answer_topic`
8. Mark message as processed

### 4.3 Research Paper Discovery

**Scheduled or on-demand:**

1. NEXUS routes research query to FRONTIER agent
2. FRONTIER.search_papers() calls `ArxivAPI`
3. Query arXiv API with filters (date range, category, keywords)
4. Parse results: title, authors, abstract, PDF link
5. Store in working memory (Weaviate) with embeddings
6. FRONTIER generates summary via vLLM
7. Return formatted results to user
8. Optional: Add to morning briefing if high relevance

## 5. Architecture Justification & Design Rationale

### 5.1 Multi-Agent Pattern

**Decision**: Three specialized agents (NEXUS, CORTEX, FRONTIER) instead of monolithic assistant

**Rationale**:

- **Separation of concerns**: Each agent has clear responsibility (routing vs. execution vs. research)
- **System prompt optimization**: Specialized prompts yield better results than general-purpose
- **Resource efficiency**: All agents share single vLLM server (no 3x memory overhead)
- **Scalability**: Easy to add new specialized agents without refactoring core

**Trade-offs**:

- ✅ **Pro**: Cleaner code, better task performance, easier testing
- ⚠️ **Con**: Routing latency (~200ms), potential for mis-routing edge cases

### 5.2 Local-First Architecture

**Decision**: Run vLLM + Weaviate locally instead of cloud APIs (OpenAI, Anthropic)

**Rationale**:

- **Privacy compliance**: HIPAA/GDPR require data never leave local machine
- **Cost efficiency**: $0.50/day electricity vs. $500/month GPT-4 API at high volume
- **Reproducibility**: Fixed model weights ensure bit-identical outputs
- **Offline capability**: Works without internet (except external integrations)

**Capabilities enabled**:

- Unlimited queries (no rate limits or token costs)
- Full audit trail for research reproducibility
- Sensitive data analysis (medical records, proprietary research)

**Risks mitigated**:

- ⚠️ **GPU dependency**: Mitigated by Phase 3 CPU/quantized model support
- ⚠️ **Model quality gap**: Llama-3.1-8B vs GPT-4 performance - acceptable for most tasks
- ⚠️ **Maintenance burden**: User manages updates vs. cloud auto-upgrade - documented procedures provided

### 5.3 3-Tier Memory System

**Decision**: Weaviate vector DB with short-term/working/long-term tiers vs. stateless

**Rationale**:

- **Learning over time**: System adapts to user preferences (research interests, workflow patterns)
- **Context persistence**: Multi-day projects maintain state across sessions
- **Efficient retrieval**: Vector search enables semantic memory lookup

**Compression strategy** (Phase 3 planned):

- Daily: Short-term (48h) → Working memory summary
- Weekly: Working → Long-term compressed facts with importance scoring
- Monthly: Prune low-importance (<0.3) long-term memories

### 5.4 Directory-Based Job Queue

**Decision**: File system queue (`job_queue/tonight/*.json`) vs. database/Redis queue

**Rationale**:

- **Simplicity**: No additional infrastructure; human-readable JSON files
- **Transparency**: User can inspect/modify queued jobs directly
- **Crash recovery**: Job files persist across system restarts
- **Low volume**: Designed for 1-10 overnight jobs, not enterprise scale

**Limitations acknowledged**:

- Not suitable for high-frequency task queuing (>100 jobs/hour)
- No distributed processing (single-node only)
- Manual priority management via filename sorting

## 6. Technology Stack

### 6.1 Core Technologies

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Language** | Python | 3.11+ | Primary development language |
| **LLM Inference** | vLLM | 0.13.0+ | High-performance local inference server |
| **Model** | Llama-3.1-8B-Instruct | - | Meta's instruction-tuned LLM |
| **Vector DB** | Weaviate | 4.0.0+ | Memory persistence and semantic search |
| **Web Framework** | Flask | 3.0.0+ | HTTP API server (optional dashboard) |
| **Containerization** | Docker Compose | 3.4+ | Weaviate deployment |
| **Automation** | systemd | - | Scheduled timers for briefings/jobs |

### 6.2 External APIs (Optional)

| Service | Purpose | Fallback Behavior |
|---------|---------|-------------------|
| OpenWeather API | Current weather & forecasts | Show 'unavailable' in briefing |
| News API | Tech news headlines | Skip news section |
| arXiv API | Research paper search | Return empty results |
| Home Assistant | Smart home status | Show 'integration ready' stub |
| Perplexity API | Enhanced prompt optimization | Fall back to Claude-only mode |

### 6.3 Python Dependencies (Key Libraries)

```
vllm>=0.13.0          # LLM inference server
torch>=2.9.0           # PyTorch for model execution
weaviate-client>=4.0   # Vector database client
requests>=2.31         # HTTP client for APIs
pydantic>=2.0          # Data validation
python-dotenv>=1.0     # Environment configuration
apscheduler>=3.10      # Job scheduling
```

## 7. Component Traceability

### 7.1 Architecture-to-Code Mapping

| Architectural Component | Implementation Files |
|-------------------------|----------------------|
| **NEXUS Agent** | `agents/nexus.py`, `agents/base.py` |
| **CORTEX Agent** | `agents/cortex.py`, `agents/base.py` |
| **FRONTIER Agent** | `agents/frontier.py`, `agents/base.py` |
| **Orchestrator** | `milton_orchestrator/orchestrator.py`, `milton_orchestrator/cli.py` |
| **Claude Runner** | `milton_orchestrator/claude_runner.py` |
| **Perplexity Client** | `milton_orchestrator/perplexity_client.py`, `perplexity_integration/` |
| **Memory System** | `memory/operations.py`, `memory/init_db.py` |
| **Integrations** | `integrations/weather.py`, `integrations/arxiv_api.py`, etc. |
| **Job Queue** | `job_queue/job_manager.py`, `scripts/job_processor.py` |
| **Automation** | `scripts/nexus_morning.py`, systemd units in `systemd/` |

### 7.2 API Endpoints

| Service | Endpoint | Protocol | Purpose |
|---------|----------|----------|---------|
| vLLM | `http://localhost:8000/v1/chat/completions` | HTTP/REST | LLM inference (OpenAI-compatible) |
| Weaviate | `http://localhost:8080/v1/` | HTTP/REST | Vector DB operations |
| ntfy | `https://ntfy.sh/{topic}` | HTTP/SSE | Mobile notifications |

### 7.3 File System Structure

```
milton/
├── agents/                  # Multi-agent implementation
│   ├── nexus.py            # Orchestrator agent
│   ├── cortex.py           # Execution agent
│   └── frontier.py         # Research agent
├── integrations/            # External API wrappers
├── memory/                  # Weaviate memory operations
├── milton_orchestrator/     # Voice-to-code orchestrator
│   ├── orchestrator.py     # Main coordination loop
│   ├── claude_runner.py    # Claude Code execution
│   └── reminders.py        # Notification scheduler
├── perplexity_integration/  # Perplexity API client
├── scripts/                 # Automation & utilities
│   ├── start_vllm.py       # vLLM server startup
│   ├── nexus_morning.py    # Morning briefing generator
│   └── job_processor.py    # Overnight job executor
├── job_queue/               # Task queue directory
│   ├── tonight/            # Pending overnight jobs
│   └── archive/            # Completed jobs
├── inbox/                   # Agent output storage
│   └── morning/            # Daily briefings
├── outputs/                 # Job execution results
├── models/                  # LLM weights (gitignored)
├── logs/                    # Runtime logs (gitignored)
├── tests/                   # Integration test suite
└── docs/                    # Documentation
```

## 8. Security & Privacy Architecture

### 8.1 Privacy Guarantees

**Data never leaves local machine:**

- ✅ All LLM inference via localhost:8000 (vLLM)
- ✅ Memory stored in local Weaviate instance (localhost:8080)
- ✅ Job outputs saved to local file system (`outputs/`)
- ⚠️ Optional external APIs (Weather, News) send only public query terms, no private data

**Verification method:**

```bash
# Monitor network traffic during agent operation
sudo tcpdump -i any port 443 | grep -v 'arxiv\|openweathermap'
# Should show zero traffic to openai.com, anthropic.com, etc.
```

### 8.2 Credential Management

**Environment-based configuration:**

- API keys stored in `.env` (gitignored)
- `.env.example` template provided (no secrets)
- Secrets loaded via `python-dotenv` at runtime
- No hardcoded credentials in source code

**Access control:**

- File permissions: `chmod 600 .env` (owner read/write only)
- Weaviate: No authentication enabled (localhost-only binding)
- vLLM: Optional API key via `VLLM_API_KEY` env var

## 9. Deployment Model

### 9.1 Installation Steps

1. **Environment setup**: Conda environment with Python 3.11+
2. **Dependency installation**: `pip install -r requirements.txt`
3. **Docker services**: `docker compose up -d` (Weaviate)
4. **Memory initialization**: `python memory/init_db.py`
5. **vLLM startup**: `python scripts/start_vllm.py` (30-60s load time)
6. **Verification**: `python tests/test_phase2.py` (6/6 tests pass)

### 9.2 Runtime Monitoring

**Health checks:**

- `scripts/health_check.py`: Verify vLLM + Weaviate availability
- Systemd service logs: `journalctl --user -u milton-nexus-morning.service -f`
- GPU monitoring: `nvidia-smi` (90%+ utilization normal during inference)

### 9.3 Failure Modes & Recovery

| Failure Scenario | Detection | Recovery |
|------------------|-----------|----------|
| vLLM crash | HTTP 500 on inference call | Restart: `python scripts/start_vllm.py` |
| Weaviate unavailable | Connection refused on port 8080 | Restart: `docker compose restart weaviate` |
| Overnight job timeout | No output after 5 hours | Manual kill, re-queue job |
| GPU OOM | CUDA out-of-memory error | Reduce batch size or use smaller model |
| Routing failure | 'NEXUS' fallback in routing response | Check system prompt, validate LLM output format |

## 10. Performance Characteristics

### 10.1 Latency Metrics (Phase 2)

| Operation | Typical Latency | Notes |
|-----------|----------------|-------|
| vLLM inference (200 tokens) | 500-800ms | RTX 5090, 90% GPU utilization |
| NEXUS routing decision | 700-1000ms | Includes LLM call + JSON parse |
| Memory vector search | 10-50ms | Weaviate 10K objects |
| Morning briefing generation | 3-5 seconds | Parallel API calls + formatting |
| Code generation (100 lines) | 2-4 seconds | Depends on complexity |

### 10.2 Scalability Limits

**Current architecture (Phase 2):**

- **Concurrent requests**: 1 (single vLLM server, sequential processing)
- **Memory size**: ~1M vectors (Weaviate), 50GB storage
- **Job queue**: 10-20 overnight jobs (file system based)
- **Users**: Single user (no multi-tenancy)

**Planned Phase 3 improvements:**

- Quantized 4-bit models → 4x smaller VRAM (run on 6GB GPU)
- Batch inference → 2-3x throughput for job queue
- Memory compression → 10x longer retention before pruning

## 11. Summary & Recommendations

### 11.1 Architecture Strengths

1. **Privacy-first design**: True local-first architecture with verifiable guarantees
2. **Clean separation**: Multi-agent pattern enables specialized performance
3. **Operational simplicity**: Minimal infrastructure (Docker + systemd)
4. **Cost efficiency**: 33x cheaper than cloud APIs at high usage
5. **Reproducibility**: Full provenance tracking for research compliance

### 11.2 Known Limitations

1. **Hardware dependency**: Requires NVIDIA GPU (12GB+ VRAM)
2. **Single-user only**: No multi-tenancy support (Phase 3 planned)
3. **Routing latency**: ~700ms overhead from agent routing layer
4. **Model quality gap**: Llama-3.1-8B weaker than GPT-4 for complex reasoning

### 11.3 Future Evolution (Phase 3+)

**Immediate priorities (Q1 2026):**

- Memory compression & learning curves (30-day validation)
- Edge deployment (Raspberry Pi 5, CPU fallback, 4-bit quantization)
- One-click installer (Docker bundle, web UI, auto model download)

**Long-term vision:**

- Agent marketplace (buy/sell custom CORTEX/FRONTIER agents)
- Lab equipment integrations (LIMS, liquid handlers, microscopes)
- Multi-user support (lab-wide deployment)
- Cloud-hosted option for non-GPU users

---

**Report generated**: 2025-12-31 18:26:21
**Total character count**: 22724

**Status**: Phase 2 Complete - All systems operational (6/6 tests passing)
