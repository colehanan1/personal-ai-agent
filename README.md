# Milton - Local-First AI Agent System

**Privacy-focused, reproducible, self-learning multi-agent AI for research and automation**

[![Phase 2](https://img.shields.io/badge/Phase_2-OPERATIONAL-brightgreen)](docs/PHASE2_COMPLETE.md)
[![Tests](https://img.shields.io/badge/tests-6%2F6_passing-success)](#test-results)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

<!-- Note: keep status badges aligned with docs/PHASE2_COMPLETE.md -->

---

## What is Milton?

Milton is a **local-first AI agent system** that runs entirely on your hardware. Unlike ChatGPT or Claude, your data never leaves your machine, your conversations are remembered forever, and every output is reproducible.

**Built for researchers who need:**
- 🔒 **Privacy** - HIPAA/GDPR compliant by design (zero cloud dependency)
- 🧠 **Memory** - Learns YOUR research patterns over weeks/months
- 📊 **Reproducibility** - Every output includes git hash, versions, random seed
- ⏰ **Automation** - Queue jobs at night, get results in the morning
- 💰 **Cost Control** - No per-token pricing, no rate limits

---

## Current Status: Phase 2 Complete ✅

| Component | Status | Details |
|-----------|--------|---------|
| **vLLM Inference** | ✅ OPERATIONAL | Llama-3.1-8B on port 8000 |
| **Weaviate Memory** | ✅ OPERATIONAL | 3-tier memory system (short/working/long-term) |
| **NEXUS Agent** | ✅ TESTED | Orchestrator & briefing generator |
| **CORTEX Agent** | ✅ TESTED | Code executor & job processor |
| **FRONTIER Agent** | ✅ TESTED | Research discovery & monitoring |
| **Automation** | ⚠️ READY | Systemd timers (pending install) |

**Test Results:** 6/6 integration tests passing ([see details](docs/PHASE2_COMPLETE.md))

---

## Architecture

### Three Specialized Agents

```
                    ┌──────────────┐
                    │    NEXUS     │  Orchestrator
                    │  (Hub/Router)│  - Routes requests
                    └──────┬───────┘  - Generates briefings
                           │          - Coordinates agents
            ┌──────────────┼──────────────┐
            │              │              │
      ┌─────▼─────┐  ┌────▼────┐  ┌─────▼──────┐
      │  CORTEX   │  │ FRONTIER│  │Integration │
      │ (Executor)│  │ (Scout) │  │   APIs     │
      └───────────┘  └─────────┘  └────────────┘
       - Code gen     - arXiv       - Weather
       - Analysis     - Research    - News
       - Jobs         - Monitoring  - Calendar
```

### Single Shared LLM (Not 3 Models!)

**All 3 agents share 1 vLLM server** - they make concurrent HTTP requests to `localhost:8000`. This is faster and more efficient than running 3 separate models.

### 3-Tier Memory System

```
Short-Term (24-48h)  →  Working (active tasks)  →  Long-Term (compressed)
     Weaviate              Weaviate                   Weaviate
   (live queries)        (task tracking)           (learned patterns)
```

Memory persists between restarts. The system learns your preferences, research interests, and common workflows over time.

---

## Quick Start

### Prerequisites

- **Hardware**: NVIDIA GPU with 12GB+ VRAM (tested on RTX 5090)
- **Software**: Docker, Conda/Miniconda, Python 3.10+
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
# ✓ PASS: vLLM Inference
# ✓ PASS: Weaviate Memory
# ✓ PASS: Agent Imports
# ✓ PASS: Agent Initialization
# ✓ PASS: Directory Structure
# ✓ PASS: Configuration
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

### Troubleshooting

- `scripts/dev_up.sh` fails on `.env`: run `cp .env.example .env` and fill required keys.
- vLLM not reachable: confirm `python scripts/start_vllm.py` runs and `LLM_API_URL` points to it.
- Weaviate down: run `docker compose up -d` and check `WEAVIATE_URL`.
- Healthcheck failures: run `python scripts/healthcheck.py` for exact status.

---

## Usage Examples

### Interactive Agent Chat

```python
from agents.nexus import NEXUS

nexus = NEXUS()

# NEXUS routes automatically based on request type
response = nexus.process_message("What's the weather today?")
# → Routes to Weather API integration

response = nexus.process_message("Find recent papers on reinforcement learning")
# → Routes to FRONTIER agent → arXiv search

response = nexus.process_message("Write a Python function to parse CSV files")
# → Routes to CORTEX agent → code generation
```

### Morning Automation

```bash
# Install systemd timers (runs at 8 AM daily)
bash scripts/install_systemd.sh

# Verify timers are active
systemctl --user list-timers | grep milton

# View logs
journalctl --user -u milton-nexus-morning.service -f
```

### Overnight Job Queue

```bash
# Queue a job before bed
cat > job_queue/tonight/my_task.json <<EOF
{
  "job_id": "analyze_data_$(date +%Y%m%d)",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "task": "Analyze yesterday's experiment data and generate summary plots",
  "priority": "HIGH"
}
EOF

# Job processes automatically between 10 PM - 6 AM
# Check results in the morning
ls outputs/analyze_data_*/
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

### 🔒 Privacy-First (Local Execution)

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

### 🧠 Persistent Memory (Learns Over Time)

Milton remembers:
- Your research interests (extracted from queries)
- Common workflows (morning routine, analysis patterns)
- Preferred output formats
- Past conversations and decisions

**Memory grows smarter:**
- Week 1: Generic responses
- Week 4: Personalized recommendations based on your actual usage

### 📊 Reproducible Outputs

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

Re-run the same job 90 days later → **bit-identical results**.

### ⏰ Overnight Automation

Schedule long-running tasks to execute while you sleep:
- **Morning briefing**: 8:00 AM (weather + news + arXiv papers)
- **Research discovery**: 8:15 AM (FRONTIER scans new publications)
- **Job processor**: 10 PM - 6 AM every 30 min (CORTEX executes queued tasks)

Wake up to completed analysis, not running scripts.

### 💰 Zero Marginal Cost

**No per-token pricing:**
- ChatGPT Plus: $20/month (limited queries)
- GPT-4 API: $0.03/1K tokens (expensive at scale)
- **Milton: Electricity only** (~$0.50/day for RTX 5090)

**1000 queries/month:**
- GPT-4 API: ~$500/month
- Milton: ~$15/month (electricity)

**33x cheaper at high volume.**

---

## Roadmap

### ✅ Phase 2 (COMPLETE - December 2025)

- [x] vLLM inference with Llama-3.1-8B
- [x] Weaviate 3-tier memory system
- [x] All 3 agents operational (NEXUS/CORTEX/FRONTIER)
- [x] Integration tests passing
- [x] Systemd automation scripts
- [x] Health monitoring

### 🚧 Phase 3 (Q1 2026 - In Planning)

**Priority 1: Memory Compression & Learning**
- [ ] Daily short-term → working memory compression
- [ ] Weekly working → long-term compression
- [ ] Importance scoring (auto-prune low-value memories)
- [ ] 30-day learning curve validation

**Priority 2: Edge Deployment**
- [ ] Quantize Llama-3.1-8B to 4-bit (GGUF)
- [ ] Raspberry Pi 5 support (6GB RAM target)
- [ ] Laptop-optimized mode (CPU fallback)
- [ ] Expand TAM from 10K (GPU owners) to 10M (any laptop)

**Priority 3: One-Click Installer**
- [ ] Docker Compose bundle (vLLM + Weaviate + agents)
- [ ] Web UI for setup (no .env editing)
- [ ] Auto-download models
- [ ] Windows/Mac/Linux binaries

**Priority 4: Lab Equipment Integrations**
- [ ] LIMS (Benchling) plugin
- [ ] Liquid handler automation (Tecan)
- [ ] Microscope image analysis
- [ ] Vertical lock-in for biotech labs

### 🔮 Phase 4 (2026+ - Vision)

- Agent marketplace (buy/sell custom CORTEX/FRONTIER agents)
- Continuous learning from usage patterns
- Multi-user support (lab-wide deployment)
- Cloud-hosted option for users without GPUs

---

## Documentation

- **[Phase 2 Deployment Guide](docs/PHASE2_DEPLOYMENT.md)** - Step-by-step setup instructions
- **[Phase 2 Completion Report](docs/PHASE2_COMPLETE.md)** - Test results & validation
- **[System Documentation](docs/SYSTEM_DOCUMENTATION.md)** - Architecture deep-dive
- **[Memory Spec](docs/MEMORY_SPEC.md)** - Deterministic memory storage + retrieval rules
- **[Orchestrator Quickstart](docs/ORCHESTRATOR_QUICKSTART.md)** - ntfy outputs via Tailscale click-to-open or SMB share
- **[Implementation Plan](docs/IMPLEMENTATION_PLAN.md)** - Original design decisions

---

## Click-to-Open Outputs

Use Tailscale Serve + ntfy Click headers so tapping a notification opens the full Milton output on your iPhone. Run `scripts/setup_tailscale_serve_outputs.sh` once and set `OUTPUT_BASE_URL` as described in `docs/ORCHESTRATOR_QUICKSTART.md`.

If you prefer a local-network alternative, configure the SMB share in `docs/ORCHESTRATOR_QUICKSTART.md` and set `OUTPUT_SHARE_URL` instead.

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
| Weaviate gRPC | 50051 | Disabled (REST only) |

### Directory Structure

```
milton/
├── agents/              # NEXUS, CORTEX, FRONTIER implementations
├── integrations/        # Weather, arXiv, News, Home Assistant APIs
├── memory/              # Weaviate operations (init, CRUD)
├── scripts/             # Automation wrappers, vLLM startup
├── systemd/             # User service & timer unit files
├── tests/               # Integration test suite
├── Prompts/             # Agent system prompts (gitignored)
├── logs/                # Runtime logs (gitignored)
│   ├── nexus/
│   ├── cortex/
│   └── frontier/
├── job_queue/           # Overnight task queue
│   ├── tonight/         # Pending jobs
│   └── archive/         # Completed jobs
├── inbox/               # Agent outputs
│   └── morning/         # Daily briefings
├── outputs/             # Job results (gitignored)
├── models/              # LLM weights (gitignored)
└── docs/                # Documentation
```

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
A: Phase 3 will add multi-user support. Current version is single-user. Contact for early access to lab deployment.

**Q: Is this just a wrapper around OpenAI API?**
A: No! Milton uses **local vLLM inference** (no OpenAI dependency). The API is OpenAI-*compatible* for ease of use, but runs entirely on your hardware.

**Q: How does memory compression work?**
A: Phase 3 feature (in development). Every 24h, short-term memories summarize into working memory. Every 7 days, working memory compresses into long-term with importance scoring. Low-value memories are pruned.

---

## Contributing

This is currently a private research project. Phase 3 will open-source the core system (Apache 2.0 license).

**Interested in beta testing?** Contact: [your contact info]

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

**Status:** ✅ Phase 2 Complete - All Systems Operational (December 30, 2025)

**Next Milestone:** Phase 3 Month 1 - Memory compression + 5 pilot users + competitive benchmarks
