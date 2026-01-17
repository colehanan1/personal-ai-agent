from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def client():
    from scripts.start_api_server import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.mark.integration(reason="API server setup is slow; opt-in only.")
def test_api_ask_attachment_goal_briefing(client, tmp_path, monkeypatch):
    from scripts import start_api_server as api_server
    from scripts.enhanced_morning_briefing import generate_morning_briefing

    monkeypatch.setattr(api_server, "STATE_DIR", tmp_path)

    payload = {
        "attachments": [
            {
                "name": "payload.json",
                "content": {"input": "Goal: Write thesis draft"},
            }
        ]
    }

    response = client.post("/api/ask", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["goal_capture"]["text"] == "Write thesis draft"
    assert data["goal_capture"]["id"]

    def weather_provider():
        return {
            "location": "Test,US",
            "temp": 70.0,
            "condition": "Sunny",
            "low": 60.0,
            "high": 80.0,
            "humidity": 30,
        }

    def papers_provider(query, max_results):
        return []

    output_path = generate_morning_briefing(
        now=datetime(2025, 1, 3, 8, 0, tzinfo=timezone.utc),
        state_dir=tmp_path,
        weather_provider=weather_provider,
        papers_provider=papers_provider,
        max_papers=0,
        overnight_hours=0,
        phd_aware=False,
    )

    content = output_path.read_text()
    assert "Write thesis draft" in content
