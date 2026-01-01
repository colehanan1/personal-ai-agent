from datetime import datetime, timedelta, timezone

import memory.retrieve as retrieve
from memory.schema import MemoryItem
from memory.store import add_memory
from memory.retrieve import query_relevant


def test_query_relevant_deterministic_order(tmp_path, monkeypatch):
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    fixed_now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(retrieve, "_now_utc", lambda: fixed_now)

    items = [
        MemoryItem(
            id="a",
            ts=fixed_now - timedelta(hours=5),
            agent="NEXUS",
            type="fact",
            content="alpha beta",
            tags=["context"],
            importance=0.2,
            source="chat",
        ),
        MemoryItem(
            id="b",
            ts=fixed_now - timedelta(hours=1),
            agent="NEXUS",
            type="fact",
            content="alpha",
            tags=[],
            importance=0.9,
            source="chat",
        ),
        MemoryItem(
            id="c",
            ts=fixed_now - timedelta(hours=1),
            agent="NEXUS",
            type="fact",
            content="gamma",
            tags=[],
            importance=0.1,
            source="chat",
        ),
    ]

    for item in items:
        add_memory(item, repo_root=tmp_path)

    results = query_relevant(
        "alpha", limit=3, recency_bias=0.3, repo_root=tmp_path
    )
    assert [result.id for result in results] == ["b", "a", "c"]
