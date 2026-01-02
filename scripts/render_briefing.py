# render_briefing.py
import json
from pathlib import Path

from dotenv import load_dotenv
from milton_orchestrator.state_paths import resolve_state_dir

ROOT_DIR = Path(__file__).resolve().parents[1]

load_dotenv()

def render_brief(json_path: str | Path | None = None) -> str:
    if json_path is None:
        candidate = resolve_state_dir() / "inbox" / "morning" / "brief_latest.json"
        if not candidate.exists():
            candidate = ROOT_DIR / "inbox" / "morning" / "brief_latest.json"
        json_path = candidate
    data = json.loads(Path(json_path).read_text())
    weather = data["weather"]
    papers = data["papers"]

    lines = []
    lines.append("Good morning, Cole.")
    lines.append(
        f"Right now it's about {round(weather['temp'])}°F with {weather['condition'].lower()} "
        f"in {weather.get('location', 'your area')}."
    )
    lines.append(
        f"Today's high will be around {round(weather['high'])}°F, "
        f"with a low near {round(weather['low'])}°F."
    )
    lines.append(" ")

    if papers:
        lines.append("Here are a few recent papers related to your dopamine / neuro topics:")
        for i, p in enumerate(papers[:3], start=1):
            lines.append(f"{i}. {p['title']} ({p['published'][:10]})")
    else:
        lines.append("No new arXiv papers matched your query this morning.")

    return "\n".join(lines)

if __name__ == "__main__":
    print(render_brief())
