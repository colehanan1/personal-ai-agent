#!/usr/bin/env python3
"""
Milton Morning Briefing Generator (Unified)
Generates morning briefing with goals, overnight results, weather, papers.
Auto-detects PhD mode when PhD research memories exist.
"""
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
from memory.store import add_memory, get_user_profile
from memory.retrieve import query_relevant
from milton_orchestrator.state_paths import resolve_state_dir


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    """Get state directory from args, env, or default."""
    return resolve_state_dir(base_dir)


def _now_utc(now: Optional[datetime] = None) -> datetime:
    """Get current time in UTC with timezone awareness."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime."""
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
    """Load completed jobs from archive since given timestamp."""
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
    """Extract goal text from goal dictionaries."""
    items: list[str] = []
    for goal in goals:
        text = str(goal.get("text", "")).strip()
        if not text:
            continue
        items.append(text)
    return items[:limit]


def _detect_phd_mode() -> bool:
    """Auto-detect if PhD mode should be enabled based on memory."""
    try:
        phd_memories = query_relevant("PhD research", limit=1, recency_bias=0.1)
        return len(phd_memories) > 0
    except Exception:
        return False


def _get_phd_context() -> dict[str, Any]:
    """Retrieve PhD research plan context from memory."""
    try:
        phd_memories = query_relevant(
            "PhD research plan olfactory BCI projects current year",
            limit=10,
            recency_bias=0.2
        )
    except Exception:
        phd_memories = []

    current_year_projects = []
    immediate_steps = []
    overall_goal = None

    for mem in phd_memories:
        if "phd" in mem.tags or "research-plan" in mem.tags:
            if "project-" in " ".join(mem.tags):
                year_tags = [tag for tag in mem.tags if tag.startswith("year-")]
                if year_tags and "year-1" in year_tags:
                    current_year_projects.append(mem.content)
            elif "immediate-action" in mem.tags or "next-step" in mem.tags:
                immediate_steps.append(mem.content)
            elif "long-term-goal" in mem.tags and not overall_goal:
                overall_goal = mem.content

    try:
        profile = get_user_profile()
        phd_facts = [f for f in profile.stable_facts if "phd" in f.lower() or "research" in f.lower()]
    except Exception:
        phd_facts = []

    return {
        "overall_goal": overall_goal,
        "current_year_projects": current_year_projects[:3],
        "immediate_steps": immediate_steps[:5],
        "phd_facts": phd_facts
    }


def _get_phd_relevant_papers(max_results: int = 3) -> list[dict[str, Any]]:
    """Get recent papers relevant to PhD research."""
    queries = [
        "olfactory calcium imaging Drosophila",
        "connectome neural decoding",
        "brain-computer interface olfaction"
    ]

    arxiv = ArxivAPI()
    papers: list[dict[str, Any]] = []

    for query in queries:
        try:
            results = arxiv.search_papers(query, max_results=1)
            papers.extend(results)
            if len(papers) >= max_results:
                break
        except Exception:
            continue

    return papers[:max_results]


def _default_weather_provider() -> dict[str, Any]:
    """Default weather provider using WeatherAPI."""
    return WeatherAPI().current_weather()


def _default_papers_provider(query: str, max_results: int) -> list[dict[str, Any]]:
    """Default papers provider using ArxivAPI."""
    return ArxivAPI().search_papers(query, max_results=max_results)


def _build_markdown(
    now: datetime,
    goals_today: list[str],
    overnight_jobs: list[dict[str, Any]],
    weather: Optional[dict[str, Any]],
    weather_error: Optional[str],
    papers: list[dict[str, Any]],
    next_actions: list[str],
    phd_context: Optional[dict[str, Any]] = None,
) -> str:
    """Build markdown briefing content."""
    date_label = now.strftime("%Y-%m-%d (%A)" if phd_context else "%Y-%m-%d")
    lines = [
        f"# Morning Briefing - {date_label}",
        "",
        f"Generated at: {now.strftime('%I:%M %p') if phd_context else now.isoformat()}",
        ""
    ]

    if phd_context:
        lines.append("=" * 70)
        lines.append("")

    # PhD Research Focus Section (if PhD mode)
    if phd_context:
        lines.append("## 🎓 PhD Research Focus")
        if phd_context.get("overall_goal"):
            lines.append(f"\n**Overall Goal:** {phd_context['overall_goal']}\n")

        if phd_context.get("current_year_projects"):
            lines.append("**Current Year Projects:**")
            for project in phd_context["current_year_projects"]:
                display = project if len(project) <= 150 else project[:147] + "..."
                lines.append(f"- {display}")
            lines.append("")

        if phd_context.get("immediate_steps"):
            lines.append("**Immediate Next Steps:**")
            for step in phd_context["immediate_steps"]:
                step_text = step.split(":", 1)[-1].strip()
                lines.append(f"- {step_text}")
            lines.append("")

        lines.append("=" * 70)
        lines.append("")

    # Goals Section
    goal_emoji = "✓ " if phd_context else ""
    lines.append(f"## {goal_emoji}{'Goals for Today' if phd_context else 'Top Goals Today'}")
    if goals_today:
        lines.extend([f"- {goal}" for goal in goals_today])
    else:
        if phd_context:
            lines.append("- No specific goals set - focus on PhD immediate steps above")
        else:
            lines.append("- No goals set")
    lines.append("")

    # Overnight Results
    overnight_emoji = "🌙 " if phd_context else ""
    lines.append(f"## {overnight_emoji}Overnight Results")
    if overnight_jobs:
        for record in overnight_jobs:
            task = record.get("task") or record.get("payload", {}).get("task") or "(no task)"
            artifacts = record.get("artifacts", [])
            artifact_note = f" (artifacts: {', '.join(artifacts)})" if artifacts else ""
            lines.append(f"- {record.get('job_id', 'job')}: {task}{artifact_note}")
    else:
        lines.append("- No completed jobs" + (" overnight" if phd_context else ""))
    lines.append("")

    # Weather
    weather_emoji = "☀️ " if phd_context else ""
    temp_unit = "°F" if phd_context else "F"
    lines.append(f"## {weather_emoji}Weather")
    if weather:
        lines.append(
            f"- {weather.get('location', 'Unknown')}: {weather.get('temp')}{temp_unit}, {weather.get('condition')}"
        )
        lines.append(
            f"- Range: {weather.get('low')}{temp_unit} - {weather.get('high')}{temp_unit}, Humidity: {weather.get('humidity')}%"
        )
    elif weather_error:
        lines.append(f"- Weather unavailable: {weather_error}")
    else:
        lines.append("- Weather unavailable")
    lines.append("")

    # Papers
    papers_emoji = "📄 " if phd_context else ""
    papers_title = "Recent Papers (PhD-Relevant)" if phd_context else "Papers"
    lines.append(f"## {papers_emoji}{papers_title}")
    if papers:
        for paper in papers:
            title = paper.get("title", "Untitled")
            authors = ", ".join(paper.get("authors", [])[:2 if phd_context else 3])
            arxiv_id = paper.get("arxiv_id", "unknown")
            if phd_context:
                lines.append(f"- **{title}**")
                lines.append(f"  {authors} | [arXiv:{arxiv_id}]")
            else:
                lines.append(f"- {title} ({authors}) [arXiv:{arxiv_id}]")
    else:
        lines.append("- No papers found")
    lines.append("")

    # Next Actions
    actions_emoji = "🎯 " if phd_context else ""
    actions_title = "Priority Actions for Today" if phd_context else "Next Actions"
    lines.append(f"## {actions_emoji}{actions_title}")
    if next_actions:
        lines.extend([f"- {action}" for action in next_actions])
    else:
        if phd_context:
            if goals_today:
                lines.extend([f"- {goal}" for goal in goals_today[:3]])
            if phd_context.get("immediate_steps"):
                for step in phd_context["immediate_steps"][:2]:
                    step_text = step.split(":", 1)[-1].strip()
                    lines.append(f"- {step_text}")
        else:
            lines.append("- No next actions specified")
    lines.append("")

    # Additional Suggestions (PhD mode only)
    if phd_context:
        lines.append("## 💡 Additional Suggestions")
        if overnight_jobs:
            lines.append("- Review overnight job results")
        if papers:
            lines.append("- Skim relevant papers during breaks")
        if not next_actions and not goals_today:
            lines.append("- Work on immediate PhD steps listed above")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _store_summary(
    now: datetime,
    goals_today: list[str],
    overnight_jobs: list[dict[str, Any]],
    output_path: Path,
    state_dir: Path,
    phd_aware: bool = False,
    phd_context: Optional[dict[str, Any]] = None,
) -> None:
    """Store briefing summary in memory."""
    summary_parts: list[str] = []

    if phd_aware and phd_context and phd_context.get("current_year_projects"):
        summary_parts.append(f"PhD projects active: {len(phd_context['current_year_projects'])}")

    if goals_today:
        summary_parts.append("Goals: " + "; ".join(goals_today[:2]))

    if overnight_jobs:
        summary_parts.append(f"Overnight jobs: {len(overnight_jobs)}")

    content = " | ".join(summary_parts).strip()
    if not content:
        return

    tags = ["briefing", "morning", f"date:{now.strftime('%Y-%m-%d')}"]
    if phd_aware:
        tags.append("phd-aware")

    item = MemoryItem(
        agent="system",
        type="result",
        content=content,
        tags=tags,
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
    phd_aware: Optional[bool] = None,
) -> Path:
    """
    Generate morning briefing with optional PhD-awareness.

    Args:
        now: Override current timestamp
        state_dir: Override state directory
        weather_provider: Custom weather provider function
        papers_provider: Custom papers provider function
        arxiv_query: Custom arXiv query (ignored in PhD mode)
        max_papers: Maximum papers to fetch
        overnight_hours: Hours back to check for overnight jobs
        phd_aware: Force PhD-aware mode (auto-detects if None)

    Returns:
        Path to generated briefing file
    """
    timestamp = _now_utc(now)
    base = _state_dir(state_dir)

    # Auto-detect PhD mode if not explicitly set
    if phd_aware is None:
        phd_aware = _detect_phd_mode()

    # Get today's goals
    goals_today = _summarize_goals(list_goals("daily", base_dir=base))
    if not goals_today:
        goals_today = _summarize_goals(list_goals("weekly", base_dir=base))

    # Get overnight jobs
    overnight_since = timestamp - timedelta(hours=overnight_hours)
    overnight_jobs = _load_completed_jobs(base, overnight_since)

    # Get weather
    weather_error: Optional[str] = None
    weather: Optional[dict[str, Any]] = None
    try:
        weather_provider = weather_provider or _default_weather_provider
        weather = weather_provider()
    except Exception as exc:
        weather_error = str(exc)

    # Get papers
    papers: list[dict[str, Any]] = []
    if phd_aware and papers_provider is None:
        # PhD mode with no custom provider - use PhD-specific queries
        try:
            papers = _get_phd_relevant_papers(max_results=max_papers)
        except Exception:
            papers = []
    else:
        # Use custom provider or standard query
        query = arxiv_query or os.getenv("MORNING_ARXIV_QUERY") or "cat:q-bio.NC AND (dopamine OR olfaction)"
        try:
            papers_provider = papers_provider or _default_papers_provider
            papers = papers_provider(query, max_papers)
        except Exception:
            papers = []

    # Get PhD context if in PhD mode
    phd_context = _get_phd_context() if phd_aware else None

    # Build next actions
    next_actions = goals_today[:3]
    if not next_actions and overnight_jobs:
        next_actions = [job.get("task", "Review overnight results") for job in overnight_jobs[:3]]
    if not next_actions and phd_aware and phd_context and phd_context.get("immediate_steps"):
        next_actions = [
            step.split(":", 1)[-1].strip()
            for step in phd_context["immediate_steps"][:3]
        ]

    # Generate output
    output_dir = base / "inbox" / "morning"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y-%m-%d')}" + ("_phd_aware.md" if phd_aware else ".md")
    output_path = output_dir / filename

    output_path.write_text(
        _build_markdown(
            timestamp,
            goals_today,
            overnight_jobs,
            weather,
            weather_error,
            papers,
            next_actions,
            phd_context=phd_context
        ),
        encoding="utf-8",
    )

    _store_summary(
        timestamp,
        goals_today,
        overnight_jobs,
        output_path,
        base,
        phd_aware=phd_aware,
        phd_context=phd_context
    )

    return output_path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate morning briefing (auto-detects PhD mode)."
    )
    parser.add_argument("--date", help="Override date (YYYY-MM-DD)")
    parser.add_argument("--state-dir", help="Override base state directory")
    parser.add_argument("--arxiv-query", help="Override arXiv query (non-PhD mode)")
    parser.add_argument("--max-papers", type=int, default=3, help="Max papers to fetch")
    parser.add_argument("--overnight-hours", type=int, default=12, help="Hours back for overnight jobs")
    parser.add_argument("--phd-aware", action="store_true", help="Force PhD-aware mode")
    parser.add_argument("--no-phd-aware", action="store_true", help="Force non-PhD mode")

    args = parser.parse_args()

    now = None
    if args.date:
        try:
            now = datetime.fromisoformat(args.date)
        except ValueError:
            print("Invalid --date format; expected YYYY-MM-DD", file=sys.stderr)
            return 2

    phd_aware = None
    if args.phd_aware:
        phd_aware = True
    elif args.no_phd_aware:
        phd_aware = False

    output_path = generate_morning_briefing(
        now=now,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        arxiv_query=args.arxiv_query,
        max_papers=args.max_papers,
        overnight_hours=args.overnight_hours,
        phd_aware=phd_aware,
    )

    mode = "PhD-aware" if "_phd_aware" in output_path.name else "standard"
    print(f"Morning briefing ({mode}) written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
