# Milton Documentation Hub

Welcome to Milton's comprehensive documentation. This guide will help you understand, deploy, and extend Milton's **three-prong self-improvement system**.

---

## Quick Navigation

### Getting Started
- [Main README](../README.md) - System overview and quick start
- [Milton System Summary](MILTON_SYSTEM_SUMMARY.md) - Single source of truth for current system and goals
- [Phase 2 Deployment Guide](PHASE2_DEPLOYMENT.md) - Current system setup
- [Phase 2 Completion Report](PHASE2_COMPLETE.md) - Test results and validation

### Three-Prong Self-Improvement Strategy (NEW)
1. [Vision & Strategy](01-vision.md) - High-level overview of the three-prong approach
2. [Current System State](02-current-state.md) - Gap analysis and implementation status
3. [90-Day Roadmap](03-roadmap.md) - Detailed implementation plan
4. [Technical Architecture](04-architecture.md) - System design and data flow

### System Components
- [Memory System](MEMORY_SPEC.md) - 3-tier memory storage and retrieval
- [Agent Context Rules](AGENT_CONTEXT_RULES.md) - Evidence-backed routing
- [Daily OS Loop](DAILY_OS.md) - Automation workflows

### User Guides
- [iOS Output Access](IOS_OUTPUT_ACCESS.md) - Mobile notifications and click-to-open
- [Orchestrator Quickstart](ORCHESTRATOR_QUICKSTART.md) - ntfy and Tailscale setup
- [Morning Briefing Guide](MORNING_BRIEFING_GUIDE.md) - Daily automation

### Technical References
- [System Documentation](SYSTEM_DOCUMENTATION.md) - Architecture deep-dive
- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Original design decisions

### Legacy / Unrelated References
- [Milton, Delaware AMI architecture report](legacy/milton_delaware_ami_architecture_report.md) - Municipal AMI RFQ summary (not related to the AI system)

---

## What is Milton?

Milton is a **local-first AI agent system** that learns and improves from every conversation you have with it. Unlike static AI assistants, Milton employs a three-prong strategy to continuously evolve:

### Prong 1: Memory System
Milton remembers your conversations, preferences, and patterns using a 3-tier memory architecture:
- **Short-term** (24-48h): Recent conversations with full detail
- **Working memory**: Active tasks and ongoing projects
- **Long-term**: Compressed learnings and important patterns

[Learn more →](01-vision.md#prong-1-conversational-memory-system)

### Prong 2: Continuous Training
Milton fine-tunes its language model weekly using LoRA (Low-Rank Adaptation) on your actual conversations:
- **Privacy-preserving**: All training happens on your hardware
- **Efficient**: Updates take 10-15 minutes, not days
- **Automated**: Runs overnight via systemd timers

[Learn more →](01-vision.md#prong-2-lightweight-continuous-retraining)

### Prong 3: Model Evolution
Milton systematically compresses and optimizes itself for edge deployment:
- **Knowledge distillation**: Learn from larger teacher models
- **Progressive pruning**: Remove unnecessary weights
- **Quantization**: Compress to 4-bit for CPU inference

[Learn more →](01-vision.md#prong-3-model-evolution-pipeline)

---

## Current Status

**Phase 2 Complete** (December 2025) ✅
- vLLM inference server operational
- Weaviate 3-tier memory system working
- All 3 agents tested (NEXUS, CORTEX, FRONTIER)
- Automation infrastructure ready

**Phase 3 Planning** (January 2026) 🚧
- Implementing three-prong self-improvement strategy
- Adding semantic search to memory
- Building LoRA training pipeline
- Quantizing model for edge deployment

[See detailed roadmap →](03-roadmap.md)

---

## Architecture Overview

```
User Conversation
        │
        ▼
┌─────────────────┐
│  Agent Layer    │  NEXUS (Router), CORTEX (Executor), FRONTIER (Scout)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌────────┐
│ Memory │ │  LLM   │
│ (Prong │ │ +LoRA  │
│   1)   │ │(Prong  │
└────┬───┘ │   2)   │
     │     └────────┘
     │
     ▼
┌────────────────┐
│ Daily Training │
│ (Prong 2)      │
└────────────────┘
     │
     ▼
┌────────────────┐
│ Model Evolution│
│ (Prong 3)      │
└────────────────┘
```

[See detailed architecture →](04-architecture.md)

---

## Key Features

### 🔒 Privacy-First
- **100% local execution** - Your data never leaves your machine
- **No cloud dependencies** - Works completely offline
- **HIPAA/GDPR compliant** by design

### 🧠 Persistent Memory
- **Remembers forever** - Conversations stored in Weaviate
- **Semantic search** - Find relevant past context automatically
- **Importance scoring** - Prioritize valuable memories

### 📊 Reproducible
- **Every output tracked** - Git commit, package versions, random seed
- **Deterministic** - Re-run 90 days later → identical results

### ⏰ Automated Learning
- **Daily LoRA updates** - Model improves while you sleep
- **Weekly compression** - Memories summarized intelligently
- **Monthly evolution** - Model optimization and distillation

### 💰 Cost-Effective
- **No per-token pricing** - Pay only for electricity (~$0.50/day)
- **33x cheaper** than GPT-4 API at high volume
- **Unlimited queries** - No rate limits

---

## Documentation Map

### For New Users
1. Start with [Main README](../README.md) for system overview
2. Read [Vision](01-vision.md) to understand the three-prong strategy
3. Follow [Phase 2 Deployment](PHASE2_DEPLOYMENT.md) to set up current system
4. Review [Roadmap](03-roadmap.md) to see what's coming

### For Developers
1. Read [Architecture](04-architecture.md) for technical design
2. Review [Current State](02-current-state.md) to understand implementation gaps
3. Check [Roadmap](03-roadmap.md) for contribution opportunities
4. Reference [System Documentation](SYSTEM_DOCUMENTATION.md) for implementation details

### For Researchers
1. Read [Vision](01-vision.md) for the three-prong learning approach
2. Review [Memory Spec](MEMORY_SPEC.md) for memory architecture
3. Check [Implementation Plan](IMPLEMENTATION_PLAN.md) for design rationale

---

## Frequently Asked Questions

**Q: How is Milton different from ChatGPT or Claude?**

Milton runs entirely on your hardware with persistent memory and continuous learning. ChatGPT/Claude are cloud-based with ephemeral context and no personalization.

**Q: Do I need 3 GPUs for the 3 agents?**

No! All 3 agents share a single vLLM server. They make concurrent HTTP requests.

**Q: How long does LoRA training take?**

10-15 minutes on consumer GPU (RTX 5090) for daily updates.

**Q: Can Milton run without a GPU?**

Phase 2 requires GPU (12GB+ VRAM). Phase 3 will support CPU inference with quantized models.

**Q: Is my data private?**

Yes. All inference and training happens locally. No data sent to cloud (except optional integrations like weather API).

**Q: How much does Milton cost to run?**

Electricity only (~$0.50/day for RTX 5090). No API fees or subscriptions.

---

## Getting Help

### Documentation Issues
- Found a bug in docs? [Report on GitHub](https://github.com/colehanan1/milton/issues)
- Have a question? Check existing docs first, then open an issue

### System Issues
- Can't start vLLM? See [Phase 2 Deployment](PHASE2_DEPLOYMENT.md#troubleshooting)
- Memory system errors? Check [Memory Spec](MEMORY_SPEC.md)
- Agent failures? Review [Agent Context Rules](AGENT_CONTEXT_RULES.md)

### Feature Requests
- Want a new capability? Review [Roadmap](03-roadmap.md) to see if planned
- Not listed? Open an issue with use case description

---

## Contributing

Milton is currently a private research project (Phase 2). Phase 3 will open-source core components.

**Interested in beta testing?** Contact the maintainer (see README).

---

## License

**Phase 2**: Private research project
**Phase 3** (planned): Apache 2.0 (core), Commercial licenses for enterprise features

---

## Document History

| Date | Update |
|------|--------|
| 2026-01-01 | Created documentation hub and three-prong strategy docs |
| 2025-12-30 | Phase 2 completion documentation |
| 2025-12-15 | Initial system documentation |

---

**Last Updated**: January 1, 2026
**System Status**: Phase 2 Complete, Phase 3 In Planning
**Next Milestone**: LoRA Training Pipeline (Week 2, 2026)
