import importlib


def test_namespace_imports():
    modules = [
        "agents.base",
        "agents.cortex",
        "agents.frontier",
        "agents.nexus",
        "integrations.arxiv_api",
        "integrations.calendar",
        "integrations.home_assistant",
        "integrations.news_api",
        "integrations.weather",
        "integrations.web_search",
        "memory.init_db",
        "memory.operations",
        "milton_orchestrator",
        "milton_orchestrator.config",
        "milton_orchestrator.orchestrator",
        "milton_orchestrator.perplexity_client",
    ]

    for module_name in modules:
        importlib.import_module(module_name)
