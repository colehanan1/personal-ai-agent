from datetime import datetime, timedelta, timezone

import memory.compress as compress
from memory.backends import JsonlBackend
from memory.schema import MemoryItem
from memory.store import add_memory


def test_compress_short_to_long(tmp_path, monkeypatch):
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")
    fixed_now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(compress, "_now_utc", lambda: fixed_now)

    items = [
        MemoryItem(
            id="pref-1",
            ts=fixed_now - timedelta(hours=72),
            agent="NEXUS",
            type="preference",
            content="Prefers concise responses",
            tags=["style"],
            importance=0.6,
            source="chat",
        ),
        MemoryItem(
            id="fact-1",
            ts=fixed_now - timedelta(hours=72),
            agent="NEXUS",
            type="fact",
            content="Uses RTX 5090",
            tags=["hardware"],
            importance=0.8,
            source="chat",
        ),
        MemoryItem(
            id="proj-goal",
            ts=fixed_now - timedelta(hours=72),
            agent="NEXUS",
            type="project",
            content="Ship memory MVP",
            tags=["project:milton", "goal"],
            importance=0.7,
            source="chat",
        ),
        MemoryItem(
            id="proj-block",
            ts=fixed_now - timedelta(hours=72),
            agent="NEXUS",
            type="decision",
            content="Blocked by missing schema",
            tags=["project:milton", "blocker"],
            importance=0.5,
            source="chat",
        ),
    ]

    for item in items:
        add_memory(item, repo_root=tmp_path)

    result = compress.compress_short_to_long(cutoff_hours=48, repo_root=tmp_path)
    assert result["compressed"] == 4
    assert result["projects"] == 1
    assert result["profile"] == 1

    backend = JsonlBackend(tmp_path)
    profile = backend.get_user_profile()
    assert profile is not None
    assert "Prefers concise responses" in profile.preferences
    assert "Uses RTX 5090" in profile.stable_facts
    assert set(profile.evidence_ids) == {"pref-1", "fact-1"}

    projects = backend.list_project_memories()
    assert len(projects) == 1
    project = projects[0]
    assert project.project_name == "milton"
    assert "Ship memory MVP" in project.goals
    assert "Blocked by missing schema" in project.blockers
    assert set(project.evidence_ids) == {"proj-goal", "proj-block"}

    remaining = backend.list_short_term()
    assert remaining == []
