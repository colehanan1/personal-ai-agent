from agents.nexus import NEXUS
import pytest

pytestmark = pytest.mark.integration(reason="NEXUS initialization is slow; opt-in only.")


def test_tool_registry_weather_dispatch(monkeypatch):
    nexus = NEXUS()

    def fake_weather():
        return {
            "location": "St. Louis,US",
            "temp": 72,
            "condition": "Clear",
            "high": 75,
            "low": 60,
        }

    monkeypatch.setattr(nexus.weather, "current_weather", fake_weather)
    result = nexus.tool_registry.dispatch("weather", "weather now")
    assert "St. Louis" in result.text
    assert result.citations


def test_tool_registry_arxiv_dispatch(monkeypatch):
    nexus = NEXUS()

    def fake_search(query, max_results=3):
        return [
            {
                "title": "Dopamine circuits in Drosophila",
                "authors": ["A", "B", "C"],
                "summary": "Summary",
                "published": "2024-01-01",
                "arxiv_id": "1234.5678",
                "pdf_url": "https://arxiv.org/pdf/1234.5678.pdf",
            }
        ]

    monkeypatch.setattr(nexus.arxiv, "search_papers", fake_search)
    result = nexus.tool_registry.dispatch("arxiv", "find 1 paper on dopamine")
    assert "Dopamine circuits" in result.text
    assert result.citations == ["https://arxiv.org/pdf/1234.5678.pdf"]
