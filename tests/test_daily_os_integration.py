from datetime import datetime, timedelta, timezone

from goals.api import add_goal
import milton_queue as queue_api
from scripts.enhanced_morning_briefing import generate_morning_briefing


def test_morning_briefing_integration(tmp_path):
    now = datetime(2025, 1, 3, 8, 0, tzinfo=timezone.utc)

    add_goal(
        "daily",
        "Review experiment results",
        base_dir=tmp_path,
        now=now - timedelta(hours=10),
    )

    job_id = queue_api.enqueue_job(
        "cortex_task",
        {"task": "Summarize overnight logs"},
        priority="medium",
        base_dir=tmp_path,
        now=now - timedelta(hours=9),
    )
    queue_api.mark_done(
        job_id,
        artifact_paths=["outputs/log_summary.md"],
        base_dir=tmp_path,
        now=now - timedelta(hours=2),
    )

    def weather_provider():
        return {
            "location": "St. Louis,US",
            "temp": 72.0,
            "condition": "Clear",
            "low": 65.0,
            "high": 75.0,
            "humidity": 40,
        }

    def papers_provider(query, max_results):
        return [
            {
                "title": "Dopamine circuits in Drosophila",
                "authors": ["A. Researcher"],
                "summary": "...",
                "published": "2024-01-01",
                "arxiv_id": "1234.5678",
                "pdf_url": "https://arxiv.org/pdf/1234.5678.pdf",
            }
        ]

    output_path = generate_morning_briefing(
        now=now,
        state_dir=tmp_path,
        weather_provider=weather_provider,
        papers_provider=papers_provider,
        arxiv_query="dopamine drosophila",
        max_papers=1,
        overnight_hours=12,
    )

    content = output_path.read_text()
    assert "Review experiment results" in content
    assert job_id in content
    assert "Summarize overnight logs" in content
    assert "Dopamine circuits in Drosophila" in content
