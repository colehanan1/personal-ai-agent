from __future__ import annotations

pytest_plugins = ("pytest_asyncio",)

from pathlib import Path
import fnmatch

import pytest


_INTEGRATION_PATTERNS = [
    "*/tests/benchmarks/*",
    "*/tests/deployment/*",
    "*/tests/test_all_systems.py",
    "*/tests/test_phase2.py",
    "*/tests/test_phone_listener.py",
    "*/tests/test_prompting_*.py",
    "*/tests/test_perplexity_integration.py",
    "*/tests/test_hybrid_retrieval.py",
    "*/tests/test_embeddings.py",
    "*/tests/test_kg*.py",
    "*/tests/test_gateway*.py",
    "*/tests/test_chat_gateway.py",
    "*/tests/test_queue_concurrency.py",
    "*/tests/test_job_queue_concurrency.py",
    "*/tests/test_model_registry.py",
    "*/tests/test_training_export.py",
    "*/tests/test_self_upgrade.py",
    "*/tests/test_reshape.py",
    "*/tests/test_*_integration.py",
]


def _is_integration_path(path: Path) -> bool:
    as_posix = path.as_posix()
    return any(fnmatch.fnmatch(as_posix, pattern) for pattern in _INTEGRATION_PATTERNS)


def pytest_collection_modifyitems(config, items) -> None:
    for item in items:
        if _is_integration_path(Path(str(item.fspath))):
            item.add_marker(
                pytest.mark.integration(
                    reason="System-level or long-running test (opt-in via -m integration)."
                )
            )
