# schemas.py
from datetime import datetime, timezone
from typing import Any, Dict, List

def morning_briefing_payload(
    weather: Dict[str, Any],
    papers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "type": "BRIEFING",
        "agent": "NEXUS",
        "ts": datetime.now(timezone.utc).isoformat() + "Z",
        "summary": "Morning brief: weather + papers.",
        "details": [
            {
                "item": "weather",
                "metric": f"{round(weather['temp'])}F, {weather['condition']}",
                "action": "Dress appropriately.",
            },
            {
                "item": "papers",
                "metric": f"{len(papers)} items",
                "action": "Skim top 1–2 today.",
            },
        ],
        "artifacts": [
            {
                "path": "inbox/morning/brief_latest.json",
                "type": "report",
            }
        ],
    }

