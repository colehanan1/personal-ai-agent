from datetime import datetime, timedelta, timezone

import memory.retrieve as retrieve
from memory.schema import MemoryItem
from memory.store import add_memory
from memory.retrieve import query_recent
from memory.backends import memory_paths


def test_store_and_query_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    fixed_now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(retrieve, "_now_utc", lambda: fixed_now)
    ts = fixed_now - timedelta(hours=1)
    item = MemoryItem(
        id="mem-1",
        ts=ts,
        agent="NEXUS",
        type="fact",
        content="User likes dark roast coffee",
        tags=["preference"],
        importance=0.7,
        source="chat",
    )

    memory_id = add_memory(item, repo_root=tmp_path)
    assert memory_id == "mem-1"

    short_path, _long_path = memory_paths(tmp_path)
    assert short_path.exists()

    results = query_recent(
        hours=48, tags=["preference"], limit=5, repo_root=tmp_path
    )
    assert len(results) == 1
    assert results[0].id == "mem-1"
