# Milton Documentation

Complete documentation for the Milton AI Agent System.

## Core Documentation

- **[SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)** - Complete system overview, architecture, and components
- **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** - Original implementation strategy and migration notes

## Quick Links

### Getting Started
- [Main README](../README.md) - Quick start guide
- [Requirements](../requirements.txt) - Python dependencies
- [Environment Setup](../README.md#configure-environment) - API keys and configuration

### Architecture
- [Agent System](SYSTEM_DOCUMENTATION.md#agent-architecture) - NEXUS, CORTEX, FRONTIER
- [Memory System](SYSTEM_DOCUMENTATION.md#memory-system) - 3-tier Weaviate implementation
- [Job Queue](SYSTEM_DOCUMENTATION.md#job-queue) - APScheduler overnight processing
- [Integrations](SYSTEM_DOCUMENTATION.md#integrations) - Weather, arXiv, News, HA, Calendar

### Development
- [Adding Integrations](../README.md#adding-new-integrations) - How to add new API wrappers
- [Modifying Agents](../README.md#modifying-agent-behavior) - Customizing agent prompts
- [Testing](../README.md#running-tests) - Running test suites

## Directory Organization

```
docs/
├── README.md                    # This file
├── SYSTEM_DOCUMENTATION.md      # Complete system overview
├── IMPLEMENTATION_PLAN.md       # Implementation strategy
└── (future additions)
    ├── API_REFERENCE.md         # Integration API docs
    ├── TROUBLESHOOTING.md       # Common issues and solutions
    └── DEPLOYMENT.md            # Production deployment guide
```

## Additional Resources

### System Prompts
The system prompts are located in `/Prompts/` (gitignored for local customization):
- `SHARED_CONTEXT.md` - Common context shared by all agents
- `NEXUS_v1.1.md` - Hub/orchestrator instructions
- `CORTEX_v1.1.md` - Executor/coder instructions
- `FRONTIER_v1.1.md` - Discovery/research instructions
- `MASTER_DEPLOY.md` - Deployment and runtime loading pattern

### Configuration Files
- [.env](../.env) - Environment variables and API keys
- [docker-compose.yml](../docker-compose.yml) - Weaviate service definition
- [requirements.txt](../requirements.txt) - Python dependencies

## Contributing

This is a private research project. For questions or issues, contact Cole.

---

**Last Updated:** December 2024
