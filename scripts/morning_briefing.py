# morning_briefing.py
import json
from pathlib import Path

from integrations.weather import WeatherAPI
from integrations.arxiv_api import ArxivAPI
from scripts.schemas import morning_briefing_payload

def generate_morning_brief(
    query: str = "cat:q-bio.NC AND (dopamine OR olfaction)",
    max_papers: int = 3,
):
    weather = WeatherAPI().current_weather()
    papers = ArxivAPI().search_papers(query, max_results=max_papers)

    payload = morning_briefing_payload(weather, papers)

    out_dir = Path("inbox/morning")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "brief_latest.json"

    with out_file.open("w") as f:
        json.dump(
            {
                "brief": payload,
                "weather": weather,
                "papers": papers,
            },
            f,
            indent=2,
        )

    print(f"✓ Morning brief written to {out_file.resolve()}")
    return out_file

if __name__ == "__main__":
    generate_morning_brief()

