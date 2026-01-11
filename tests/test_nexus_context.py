import agents.nexus as nexus_module
from agents.nexus import NEXUS, ContextPacket
from memory.schema import MemoryItem


def test_build_context_requires_evidence(monkeypatch):
    nexus = NEXUS()
    items = [
        MemoryItem(
            id="mem-1",
            agent="NEXUS",
            type="fact",
            content="User prefers concise summaries.",
            tags=["preference"],
            importance=0.7,
            source="chat",
        ),
        MemoryItem(
            id="",
            agent="NEXUS",
            type="fact",
            content="This should be skipped.",
            tags=["preference"],
            importance=0.5,
            source="chat",
        ),
    ]
    # Mock both query_relevant and query_relevant_hybrid for backward compatibility
    monkeypatch.setattr(nexus_module, "query_relevant", lambda *args, **kwargs: items)
    monkeypatch.setattr(nexus_module, "query_relevant_hybrid", lambda *args, **kwargs: items)

    packet = nexus.build_context("test request", budget_tokens=50)
    assert isinstance(packet, ContextPacket)
    assert packet.context_ids == ["mem-1"]
    assert all(bullet.evidence_ids for bullet in packet.bullets)
    assert all("" not in bullet.evidence_ids for bullet in packet.bullets)


def test_build_context_empty_memory(monkeypatch):
    nexus = NEXUS()
    # Mock both query_relevant and query_relevant_hybrid for backward compatibility
    monkeypatch.setattr(nexus_module, "query_relevant", lambda *args, **kwargs: [])
    monkeypatch.setattr(nexus_module, "query_relevant_hybrid", lambda *args, **kwargs: [])
    packet = nexus.build_context("test request", budget_tokens=50)
    assert packet.bullets == []
    assert packet.unknowns
