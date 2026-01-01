from agents.nexus import NEXUS, ContextPacket, ContextBullet
from agents.tool_registry import ToolResult


def _fixed_context(query: str) -> ContextPacket:
    return ContextPacket(
        query=query,
        bullets=[
            ContextBullet(text="Project: Milton memory MVP", evidence_ids=["mem-1"]),
            ContextBullet(text="Prefers concise summaries", evidence_ids=["mem-2"]),
        ],
        unknowns=[],
        assumptions=["Assume request is self-contained."],
    )


def test_golden_weather_route(monkeypatch):
    nexus = NEXUS()
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: _fixed_context("q"))

    def fake_dispatch(tool_name, user_text):
        assert tool_name == "weather"
        return ToolResult(text="72F and clear", citations=["weather:openweather"])

    monkeypatch.setattr(nexus.tool_registry, "dispatch", fake_dispatch)

    response = nexus.process_message("What's the weather tomorrow?")
    assert response.to_dict() == {
        "text": "72F and clear",
        "citations": ["weather:openweather"],
        "route_used": "tool:weather",
        "context_used": ["mem-1", "mem-2"],
    }


def test_golden_project_summary(monkeypatch):
    nexus = NEXUS()
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: _fixed_context("q"))
    monkeypatch.setattr(nexus, "_safe_llm_call", lambda *args, **kwargs: "Known projects: Milton memory MVP.")

    response = nexus.process_message("Summarize what you know about my current projects")
    assert response.to_dict() == {
        "text": "Known projects: Milton memory MVP.",
        "citations": [],
        "route_used": "nexus",
        "context_used": ["mem-1", "mem-2"],
    }


def test_golden_arxiv_route(monkeypatch):
    nexus = NEXUS()
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: _fixed_context("q"))

    def fake_dispatch(tool_name, user_text):
        assert tool_name == "arxiv"
        return ToolResult(
            text="- Paper A\n- Paper B\n- Paper C",
            citations=["https://arxiv.org/pdf/1.pdf"],
        )

    monkeypatch.setattr(nexus.tool_registry, "dispatch", fake_dispatch)

    response = nexus.process_message("Find 3 papers on dopamine in Drosophila")
    assert response.to_dict() == {
        "text": "- Paper A\n- Paper B\n- Paper C",
        "citations": ["https://arxiv.org/pdf/1.pdf"],
        "route_used": "tool:arxiv",
        "context_used": ["mem-1", "mem-2"],
    }
