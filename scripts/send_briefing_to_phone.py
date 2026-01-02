#!/home/cole-hanan/miniconda3/envs/milton/bin/python3
"""
Send Morning Briefing to iPhone
Supports multiple delivery methods: ntfy.sh push, formatted output, SSH
"""
import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = Path(
    os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR") or ROOT_DIR
)

LEGACY_JSON_BRIEF = ROOT_DIR / "inbox" / "morning" / "enhanced_brief_latest.json"


def _latest_briefing_path(briefing_type: str) -> Path | None:
    candidates: list[Path] = []
    for base in (STATE_DIR, ROOT_DIR):
        folder = base / "inbox" / briefing_type
        if not folder.exists():
            continue
        candidates.extend(folder.glob("*.md"))
        candidates.extend(folder.glob("*.txt"))

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_briefing_payload(briefing_type: str) -> dict | None:
    """Load the latest briefing data (JSON or Markdown)."""
    latest_path = _latest_briefing_path(briefing_type)
    if not latest_path:
        if briefing_type != "morning" or not LEGACY_JSON_BRIEF.exists():
            return None
        try:
            with open(LEGACY_JSON_BRIEF) as f:
                return {"format": "json", "data": json.load(f)}
        except Exception:
            return None

    try:
        text = latest_path.read_text(encoding="utf-8")
    except Exception:
        text = latest_path.read_text(errors="replace")
    return {"format": "text", "text": text, "path": str(latest_path)}


def format_briefing_text(payload: dict | None, briefing_type: str) -> str:
    """Format briefing as readable text with links."""
    if not payload:
        return (
            f"❌ No {briefing_type} briefing data available. "
            "Run the briefing generator and try again."
        )

    if payload.get("format") == "text":
        text = payload.get("text", "").strip()
        return text or f"❌ {briefing_type.capitalize()} briefing file was empty."

    data = payload.get("data") or {}
    timestamp = datetime.fromisoformat(data['timestamp']).strftime('%B %d, %Y at %I:%M %p')

    # Weather section
    weather = data.get('weather', {})
    weather_text = f"""☀️ MORNING BRIEFING
{timestamp}

📍 WEATHER
Location: {weather.get('location', 'Unknown')}
Current: {weather.get('temp', 0):.0f}°F, {weather.get('condition', 'Unknown')}
Range: {weather.get('low', 0):.0f}°F - {weather.get('high', 0):.0f}°F
Humidity: {weather.get('humidity', 0)}%"""

    # Benchmark section
    benchmarks = data.get('benchmarks', {})
    summaries = benchmarks.get('summaries', [])

    if summaries:
        latest = summaries[0]['summary']
        total_queries = benchmarks.get('total_queries', 0)
        benchmark_text = f"""

🧪 AI PERFORMANCE
{latest}
Total queries in memory: {total_queries}"""
    else:
        benchmark_text = "\n\n🧪 AI PERFORMANCE\nNo benchmark data"

    # System status
    system = data.get('system_status', {})
    system_text = f"""

🖥️ SYSTEM STATUS
Memory vectors: {system.get('memory_vectors', 0)}
Status: {system.get('status', 'unknown').upper()}"""

    # Links
    links_text = """

📱 LINKS
Dashboard: http://localhost:5173
API Status: http://localhost:8001/api/system-state
Full briefing: ~/milton/inbox/morning/enhanced_brief_latest.json"""

    return weather_text + benchmark_text + system_text + links_text


def send_via_ntfy(briefing_text, topic=None, title=None):
    """Send briefing via ntfy.sh push notification."""
    if not topic:
        topic = (
            os.getenv("NTFY_TOPIC")
            or os.getenv("ANSWER_TOPIC")
            or "milton-briefing"
        )

    # Use simple ASCII text for title, full text for body
    title = title or "Milton Briefing"
    body = briefing_text

    # Send to ntfy.sh
    try:
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": "default",
                "Tags": "sunny,star"
            },
            timeout=10
        )

        if response.status_code == 200:
            return f"✅ Sent via ntfy.sh to topic: {topic}"
        else:
            return f"❌ Failed to send (status {response.status_code})"

    except Exception as e:
        return f"❌ Error sending via ntfy: {e}"


def send_via_telegram(briefing_text):
    """Send briefing via Telegram (if configured)."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return "ℹ️  Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": briefing_text,
                "parse_mode": "HTML"
            },
            timeout=10
        )

        if response.status_code == 200:
            return "✅ Sent via Telegram"
        else:
            return f"❌ Telegram failed (status {response.status_code})"

    except Exception as e:
        return f"❌ Error sending via Telegram: {e}"


def main():
    """Main function - send briefing via configured methods."""
    import argparse

    parser = argparse.ArgumentParser(description="Send morning briefing to iPhone")
    parser.add_argument("--method", choices=["ntfy", "telegram", "print", "all"],
                       default="print", help="Delivery method")
    parser.add_argument(
        "--briefing",
        choices=["morning", "evening"],
        default="morning",
        help="Which briefing to send",
    )
    parser.add_argument("--topic", help="ntfy.sh topic name (default: milton-briefing)")
    args = parser.parse_args()

    # Load and format briefing
    payload = load_briefing_payload(args.briefing)
    briefing_text = format_briefing_text(payload, args.briefing)
    title = f"Milton {args.briefing.capitalize()} Briefing"

    if args.method == "print" or args.method == "all":
        print(briefing_text)
        print()

    if args.method == "ntfy" or args.method == "all":
        result = send_via_ntfy(briefing_text, args.topic, title=title)
        print(result)

    if args.method == "telegram" or args.method == "all":
        result = send_via_telegram(briefing_text)
        print(result)


if __name__ == "__main__":
    main()
