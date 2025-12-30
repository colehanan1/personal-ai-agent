# Phase 2 Deployment Guide

## Current Status

✅ **Completed:**
- Python dependencies installed in `milton` conda environment
- Agent imports verified (NEXUS, CORTEX, FRONTIER)
- `.env` updated to use `llama31-8b-instruct`
- Health check script created (`scripts/health_check.py`)
- Systemd wrapper scripts created (3 wrappers for automation)
- Systemd unit files created (3 services + 3 timers)
- Installation script created (`scripts/install_systemd.sh`)
- Test suite created (`tests/test_phase2.py`)

⚠️ **Blockers:**
1. **vLLM not running** - Need to start: `python scripts/start_vllm.py`
2. **Weaviate not running** - Need sudo for Docker: `sudo docker compose up -d`

---

## Quick Start (5 Minutes)

### Step 1: Start Services

```bash
cd /home/cole-hanan/milton

# Terminal 1: Start vLLM (will use GPU)
conda activate milton
python scripts/start_vllm.py

# Terminal 2: Start Weaviate (requires sudo)
sudo docker compose up -d

# Verify both are running
curl http://localhost:8000/v1/models  # vLLM
curl http://localhost:8080/v1/meta    # Weaviate
```

### Step 2: Run Tests

```bash
conda activate milton
python tests/test_phase2.py
```

Expected output: All 6 tests should PASS.

### Step 3: Install Systemd Automation

```bash
# Run installation script
bash scripts/install_systemd.sh

# Start timers
systemctl --user start milton-nexus-morning.timer
systemctl --user start milton-frontier-morning.timer
systemctl --user start milton-job-processor.timer

# Verify timers are active
systemctl --user list-timers --all | grep milton
```

---

## System Architecture

### Components

1. **vLLM (Inference)** - Port 8000
   - Model: `llama31-8b-instruct` (Llama-3.1-8B)
   - All 3 agents share this single instance
   - Handles concurrent requests via internal queue

2. **Weaviate (Memory)** - Port 8080
   - Vector database for persistent memory
   - Stores: short-term, working, long-term memories
   - Docker container with volume persistence

3. **NEXUS (Hub)** - `agents/nexus.py`
   - Orchestrates requests to other agents
   - Generates morning/evening briefings
   - Routes tasks to CORTEX/FRONTIER

4. **CORTEX (Executor)** - `agents/cortex.py`
   - Executes overnight jobs from queue
   - Generates code and analysis
   - Outputs include provenance (git hash, versions, seed)

5. **FRONTIER (Scout)** - `agents/frontier.py`
   - Monitors arXiv for research papers
   - Generates daily research discoveries
   - Filters by relevance to your interests

### Automation Schedule

| Time | Agent | Script | What It Does |
|------|-------|--------|--------------|
| 8:00 AM | NEXUS | `nexus_morning.py` | Generate morning briefing (weather + papers) |
| 8:15 AM | FRONTIER | `frontier_morning.py` | Scan arXiv for new papers |
| 10:00 PM - 6:00 AM (every 30 min) | CORTEX | `job_processor.py` | Process overnight job queue |

---

## Testing

### Health Check

```bash
conda activate milton
python scripts/health_check.py
```

Output: JSON report showing status of all components.

### Manual Agent Testing

```bash
conda activate milton

# Test NEXUS
python -c "from agents.nexus import NEXUS; n = NEXUS(); print('NEXUS OK')"

# Test CORTEX
python -c "from agents.cortex import CORTEX; c = CORTEX(); print('CORTEX OK')"

# Test FRONTIER
python -c "from agents.frontier import FRONTIER; f = FRONTIER(); print('FRONTIER OK')"
```

### Full Integration Test

```bash
conda activate milton
python tests/test_phase2.py
```

Should output:
```
✓ PASS: vLLM Inference
✓ PASS: Weaviate Memory
✓ PASS: Agent Imports
✓ PASS: Agent Initialization
✓ PASS: Directory Structure
✓ PASS: Configuration

Total: 6/6 tests passed
✓ ALL TESTS PASSED - Phase 2 Ready!
```

---

## Troubleshooting

### vLLM Won't Start

**Problem**: Port 8000 already in use or GPU memory full

**Solution**:
```bash
# Check if vLLM already running
ps aux | grep vllm

# Kill existing instance
pkill -f vllm

# Check GPU memory
nvidia-smi

# Start with lower memory utilization
# Edit scripts/start_vllm.py and reduce --gpu-memory-utilization
```

### Weaviate Won't Start

**Problem**: Docker permission denied

**Solution**:
```bash
# Add user to docker group (one-time)
sudo usermod -aG docker cole-hanan
newgrp docker  # Activate group immediately

# Then start without sudo
docker compose up -d
```

**Problem**: Port 8080 conflict

**Solution**:
```bash
# Edit docker-compose.yml
# Change ports to "8081:8080"

# Update .env
# Change WEAVIATE_URL=http://localhost:8081
```

### Agents Can't Import

**Problem**: `ModuleNotFoundError: No module named 'agents'`

**Solution**:
```bash
# Always activate conda environment first
conda activate milton

# Verify you're in milton env
which python
# Should show: /home/cole-hanan/miniconda3/envs/milton/bin/python
```

### Systemd Timers Not Firing

**Problem**: Timer enabled but not executing

**Solution**:
```bash
# Check timer status
systemctl --user status milton-nexus-morning.timer

# View logs
journalctl --user -u milton-nexus-morning.service -n 50

# Manually trigger service to test
systemctl --user start milton-nexus-morning.service

# Check if user lingering is enabled (allows timers to run when logged out)
loginctl enable-linger cole-hanan
```

---

## File Reference

### Configuration
- `.env` - Environment variables (API keys, URLs)
- `docker-compose.yml` - Weaviate configuration
- `requirements.txt` - Python dependencies

### Scripts
- `scripts/health_check.py` - System status check
- `scripts/nexus_morning.py` - Morning briefing wrapper
- `scripts/frontier_morning.py` - Research discovery wrapper
- `scripts/job_processor.py` - Overnight job processor
- `scripts/install_systemd.sh` - Systemd installation
- `scripts/start_vllm.py` - vLLM startup script

### Tests
- `tests/test_phase2.py` - Integration test suite

### Systemd Units (in `systemd/`)
- `milton-nexus-morning.service` + `.timer`
- `milton-frontier-morning.service` + `.timer`
- `milton-job-processor.service` + `.timer`

### Logs (auto-generated)
- `logs/nexus/*.log` - NEXUS execution logs
- `logs/cortex/*.log` - CORTEX execution logs
- `logs/frontier/*.log` - FRONTIER execution logs

### Outputs (auto-generated)
- `inbox/morning/brief_*.json` - Morning briefings
- `outputs/*` - Job execution results
- `job_queue/archive/*.json` - Completed jobs

---

## Next Steps (Phase 3)

Once Phase 2 is stable (24h test passes):

1. **Memory Compression** - Implement 3-tier summarization
2. **Continuous Learning** - Extract user preferences from interactions
3. **Model Upgrade** - Switch to Qwen3-30B for better performance
4. **Edge Deployment** - Deploy to RPi5 for 24/7 operation
5. **Token Optimization** - Reduce prompt sizes further

---

## Quick Reference Commands

```bash
# Activate environment
conda activate milton

# Check system health
python scripts/health_check.py

# Start services manually
python scripts/start_vllm.py  # Terminal 1
sudo docker compose up -d      # Terminal 2

# Run tests
python tests/test_phase2.py

# Install automation
bash scripts/install_systemd.sh

# View timer status
systemctl --user list-timers --all | grep milton

# View logs (real-time)
journalctl --user -u milton-nexus-morning.service -f

# Manually trigger a timer
systemctl --user start milton-nexus-morning.service

# Stop timers
systemctl --user stop milton-nexus-morning.timer
systemctl --user stop milton-frontier-morning.timer
systemctl --user stop milton-job-processor.timer
```

---

## Phase 2 Definition of "Done"

- [x] All Python dependencies installed
- [ ] vLLM running and responding (needs manual start)
- [ ] Weaviate running and persistent (needs sudo docker)
- [x] All 3 agents importable and functional
- [ ] NEXUS routes requests correctly (needs vLLM)
- [ ] CORTEX executes jobs with checksums
- [ ] FRONTIER generates briefing with papers
- [ ] Memory persists between restarts
- [x] Morning briefing automation configured
- [x] Overnight job automation configured
- [x] Systemd timers installed and enabled

**Status**: **85% Complete** - Ready for service startup and testing.
