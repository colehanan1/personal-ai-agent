#!/usr/bin/env python3
"""Generate morning briefing with goals, overnight results, weather, and papers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
import argparse
import json
import os
import sys

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

from integrations.weather import WeatherAPI
from integrations.arxiv_api import ArxivAPI
from goals.api import list_goals
from memory.schema import MemoryItem
from memory.store import add_memory


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    env_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR")
    if env_dir:
        return Path(env_dir)
    return ROOT_DIR


def _now_utc(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _load_completed_jobs(base: Path, since: datetime) -> list[dict[str, Any]]:
    archive_dir = base / "job_queue" / "archive"
    if not archive_dir.exists():
        return []
    completed: list[dict[str, Any]] = []
    for path in archive_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        completed_at = _parse_iso(record.get("completed_at"))
        if completed_at and completed_at >= since:
            completed.append(record)
    return completed


def _summarize_goals(goals: list[dict[str, Any]], limit: int = 5) -> list[str]:
    items: list[str] = []
    for goal in goals:
        text = str(goal.get("text", "")).strip()
        if not text:
            continue
        items.append(text)
    return items[:limit]


def _default_weather_provider() -> dict[str, Any]:
    return WeatherAPI().current_weather()


def _default_papers_provider(query: str, max_results: int) -> list[dict[str, Any]]:
    return ArxivAPI().search_papers(query, max_results=max_results)


def _build_markdown(
    now: datetime,
    goals_today: list[str],
    overnight_jobs: list[dict[str, Any]],
    weather: Optional[dict[str, Any]],
    weather_error: Optional[str],
    papers: list[dict[str, Any]],
    next_actions: list[str],
) -> str:
    date_label = now.strftime("%Y-%m-%d")
    lines = [f"# Morning Briefing - {date_label}", "", f"Generated at: {now.isoformat()}", ""]

    lines.append("## Top Goals Today")
    if goals_today:
        lines.extend([f"- {goal}" for goal in goals_today])
    else:
        lines.append("- No goals set")
    lines.append("")

    lines.append("## Overnight Results")
    if overnight_jobs:
        for record in overnight_jobs:
            task = record.get("task") or record.get("payload", {}).get("task") or "(no task)"
            artifacts = record.get("artifacts", [])
            artifact_note = f" (artifacts: {', '.join(artifacts)})" if artifacts else ""
            lines.append(f"- {record.get('job_id', 'job')}: {task}{artifact_note}")
    else:
        lines.append("- No completed jobs")
    lines.append("")

    lines.append("## Weather")
    if weather:
        lines.append(
            f"- {weather.get('location', 'Unknown')}: {weather.get('temp')}F, {weather.get('condition')}"
        )
        lines.append(
            f"- Range: {weather.get('low')}F - {weather.get('high')}F, Humidity: {weather.get('humidity')}%"
        )
    elif weather_error:
        lines.append(f"- Weather unavailable: {weather_error}")
    else:
        lines.append("- Weather unavailable")
    lines.append("")

    lines.append("## Papers")
    if papers:
        for paper in papers:
            title = paper.get("title", "Untitled")
            authors = ", ".join(paper.get("authors", [])[:3])
            arxiv_id = paper.get("arxiv_id", "unknown")
            lines.append(f"- {title} ({authors}) [arXiv:{arxiv_id}]")
    else:
        lines.append("- No papers found")
    lines.append("")

    lines.append("## Next Actions")
    if next_actions:
        lines.extend([f"- {item}" for item in next_actions])
    else:
        lines.append("- No next actions specified")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def _store_summary(now: datetime, goals_today: list[str], overnight_jobs: list[dict[str, Any]], output_path: Path, state_dir: Path) -> None:
    summary_parts: list[str] = []
    if goals_today:
        summary_parts.append("Goals: " + "; ".join(goals_today))
    if overnight_jobs:
        summary_parts.append(f"Overnight jobs: {len(overnight_jobs)}")
    content = " | ".join(summary_parts).strip()
    if not content:
        return

    item = MemoryItem(
        agent="system",
        type="result",
        content=content,
        tags=["briefing", "morning", f"date:{now.strftime('%Y-%m-%d')}"],
        importance=0.4,
        source=str(output_path),
        evidence=[str(output_path)],
    )
    try:
        add_memory(item, repo_root=state_dir)
    except Exception:
        pass


def generate_morning_briefing(
    *,
    now: Optional[datetime] = None,
    state_dir: Optional[Path] = None,
    weather_provider: Optional[Callable[[], dict[str, Any]]] = None,
    papers_provider: Optional[Callable[[str, int], list[dict[str, Any]]]] = None,
    arxiv_query: Optional[str] = None,
    max_papers: int = 3,
    overnight_hours: int = 12,
) -> Path:
    timestamp = _now_utc(now)
    base = _state_dir(state_dir)

    goals_today = _summarize_goals(list_goals("daily", base_dir=base))
    if not goals_today:
        goals_today = _summarize_goals(list_goals("weekly", base_dir=base))

    overnight_since = timestamp - timedelta(hours=overnight_hours)
    overnight_jobs = _load_completed_jobs(base, overnight_since)

    weather_error: Optional[str] = None
    weather: Optional[dict[str, Any]] = None
    try:
        weather_provider = weather_provider or _default_weather_provider
        weather = weather_provider()
    except Exception as exc:
        weather_error = str(exc)

    papers: list[dict[str, Any]] = []
    query = arxiv_query or os.getenv("MORNING_ARXIV_QUERY") or "cat:q-bio.NC AND (dopamine OR olfaction)"
    try:
        papers_provider = papers_provider or _default_papers_provider
        papers = papers_provider(query, max_papers)
    except Exception:
        papers = []

    next_actions = goals_today[:3]
    if not next_actions and overnight_jobs:
        next_actions = [job.get("task", "Review overnight results") for job in overnight_jobs[:3]]

    output_dir = base / "inbox" / "morning"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y-%m-%d')}.md"
    output_path = output_dir / filename

    output_path.write_text(
        _build_markdown(timestamp, goals_today, overnight_jobs, weather, weather_error, papers, next_actions),
        encoding="utf-8",
    )

    _store_summary(timestamp, goals_today, overnight_jobs, output_path, base)

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate morning briefing.")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD)")
    parser.add_argument("--state-dir", help="Override base state directory")
    parser.add_argument("--arxiv-query", help="Override arXiv query")
    parser.add_argument("--max-papers", type=int, default=3, help="Max papers to fetch")
    parser.add_argument("--overnight-hours", type=int, default=12, help="Hours back for overnight jobs")

    args = parser.parse_args()

    now = None
    if args.date:
        try:
            now = datetime.fromisoformat(args.date)
        except ValueError:
            print("Invalid --date format; expected YYYY-MM-DD", file=sys.stderr)
            return 2

    output_path = generate_morning_briefing(
        now=now,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        arxiv_query=args.arxiv_query,
        max_papers=args.max_papers,
        overnight_hours=args.overnight_hours,
    )
    print(f"Morning briefing written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
