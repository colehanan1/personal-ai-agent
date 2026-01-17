from agents.nexus import NEXUS, ContextPacket, ContextBullet
import pytest
from agents.tool_registry import ToolResult

pytestmark = pytest.mark.integration(reason="NEXUS initialization is slow; opt-in only.")


def test_process_message_returns_response(monkeypatch):
    nexus = NEXUS()
    packet = ContextPacket(
        query="test",
        bullets=[ContextBullet(text="Known preference", evidence_ids=["mem-1"])],
        unknowns=[],
        assumptions=["Assume request is self-contained."],
    )
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: packet)
    monkeypatch.setattr(nexus, "_safe_llm_call", lambda *args, **kwargs: "OK")

    response = nexus.process_message("Summarize my projects")
    assert response.text == "OK"
    assert response.context_used == ["mem-1"]
    assert response.route_used == "nexus"


def test_process_message_llm_failure(monkeypatch):
    nexus = NEXUS()
    packet = ContextPacket(query="test", bullets=[], unknowns=[], assumptions=[])
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: packet)
    monkeypatch.setattr(nexus, "_safe_llm_call", lambda *args, **kwargs: None)

    response = nexus.process_message("Summarize my projects")
    assert "LLM unavailable" in response.text


def test_process_message_tool_dispatch(monkeypatch):
    nexus = NEXUS()
    packet = ContextPacket(query="test", bullets=[], unknowns=[], assumptions=[])
    monkeypatch.setattr(nexus, "build_context", lambda *args, **kwargs: packet)

    def fake_dispatch(tool_name, user_text):
        return ToolResult(text="Weather OK", citations=["weather:openweather"])

    monkeypatch.setattr(nexus.tool_registry, "dispatch", fake_dispatch)

    response = nexus.process_message("What's the weather?")
    assert response.route_used.startswith("tool:")
    assert response.text == "Weather OK"
    assert response.citations == ["weather:openweather"]
