#!/usr/bin/env python3
"""PhD-aware morning briefing with research goal tracking."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
import argparse
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv()

from integrations.weather import WeatherAPI
from integrations.arxiv_api import ArxivAPI
from goals.api import list_goals
from memory.schema import MemoryItem
from memory.store import add_memory, get_user_profile
from memory.retrieve import query_relevant
from scripts.enhanced_morning_briefing import (
    _state_dir,
    _now_utc,
    _load_completed_jobs,
    _summarize_goals
)


def _get_phd_context() -> dict[str, Any]:
    """Retrieve PhD research plan context from memory."""
    # Query for PhD-related memories
    phd_memories = query_relevant(
        "PhD research plan olfactory BCI projects current year",
        limit=10,
        recency_bias=0.2  # Emphasize relevance over recency for long-term goals
    )

    # Extract PhD information
    current_year_projects = []
    immediate_steps = []
    overall_goal = None

    for mem in phd_memories:
        if "phd" in mem.tags or "research-plan" in mem.tags:
            if "project-" in " ".join(mem.tags):
                # Extract year from tags
                year_tags = [tag for tag in mem.tags if tag.startswith("year-")]
                if year_tags and "year-1" in year_tags:  # Focus on current year
                    current_year_projects.append(mem.content)
            elif "immediate-action" in mem.tags or "next-step" in mem.tags:
                immediate_steps.append(mem.content)
            elif "long-term-goal" in mem.tags and not overall_goal:
                overall_goal = mem.content

    # Get user profile for PhD facts
    profile = get_user_profile()
    phd_facts = [f for f in profile.stable_facts if "phd" in f.lower() or "research" in f.lower()]

    return {
        "overall_goal": overall_goal,
        "current_year_projects": current_year_projects[:3],  # Top 3 current projects
        "immediate_steps": immediate_steps[:5],  # Top 5 immediate steps
        "phd_facts": phd_facts
    }


def _get_relevant_papers(max_results: int = 3) -> list[dict[str, Any]]:
    """Get recent papers relevant to PhD research."""
    # Query based on PhD research topics
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


def _build_phd_aware_markdown(
    now: datetime,
    goals_today: list[str],
    overnight_jobs: list[dict[str, Any]],
    weather: Optional[dict[str, Any]],
    weather_error: Optional[str],
    papers: list[dict[str, Any]],
    phd_context: dict[str, Any],
    next_actions: list[str],
) -> str:
    """Build markdown briefing with PhD research focus."""
    date_label = now.strftime("%Y-%m-%d (%A)")
    lines = [
        f"# Morning Briefing - {date_label}",
        "",
        f"Generated at: {now.strftime('%I:%M %p')}",
        "",
        "=" * 70,
        ""
    ]

    # PhD Research Focus Section
    lines.append("## 🎓 PhD Research Focus")
    if phd_context.get("overall_goal"):
        lines.append(f"\n**Overall Goal:** {phd_context['overall_goal']}\n")

    if phd_context.get("current_year_projects"):
        lines.append("**Current Year Projects:**")
        for project in phd_context["current_year_projects"]:
            # Shorten if too long
            display = project if len(project) <= 150 else project[:147] + "..."
            lines.append(f"- {display}")
        lines.append("")

    if phd_context.get("immediate_steps"):
        lines.append("**Immediate Next Steps:**")
        for step in phd_context["immediate_steps"]:
            # Extract the step text (remove "PhD immediate next step N:")
            step_text = step.split(":", 1)[-1].strip()
            lines.append(f"- {step_text}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("")

    # Today's Goals
    lines.append("## ✓ Goals for Today")
    if goals_today:
        lines.extend([f"- {goal}" for goal in goals_today])
    else:
        lines.append("- No specific goals set - focus on PhD immediate steps above")
    lines.append("")

    # Overnight Results
    lines.append("## 🌙 Overnight Results")
    if overnight_jobs:
        for record in overnight_jobs:
            task = record.get("task") or record.get("payload", {}).get("task") or "(no task)"
            artifacts = record.get("artifacts", [])
            artifact_note = f" (artifacts: {', '.join(artifacts)})" if artifacts else ""
            completed_at = record.get("completed_at", "")
            lines.append(f"- {record.get('job_id', 'job')}: {task}{artifact_note}")
    else:
        lines.append("- No completed jobs overnight")
    lines.append("")

    # Weather
    lines.append("## ☀️ Weather")
    if weather:
        lines.append(
            f"- {weather.get('location', 'Unknown')}: {weather.get('temp')}°F, {weather.get('condition')}"
        )
        lines.append(
            f"- Range: {weather.get('low')}°F - {weather.get('high')}°F, Humidity: {weather.get('humidity')}%"
        )
    elif weather_error:
        lines.append(f"- Weather unavailable: {weather_error}")
    else:
        lines.append("- Weather unavailable")
    lines.append("")

    # Relevant Papers
    lines.append("## 📄 Recent Papers (PhD-Relevant)")
    if papers:
        for paper in papers:
            title = paper.get("title", "Untitled")
            authors = ", ".join(paper.get("authors", [])[:2])
            arxiv_id = paper.get("arxiv_id", "unknown")
            lines.append(f"- **{title}**")
            lines.append(f"  {authors} | [arXiv:{arxiv_id}]")
    else:
        lines.append("- No papers found")
    lines.append("")

    # Next Actions (priority tasks for today)
    lines.append("## 🎯 Priority Actions for Today")
    if next_actions:
        lines.extend([f"- {action}" for action in next_actions])
    else:
        if goals_today:
            lines.extend([f"- {goal}" for goal in goals_today[:3]])
        if phd_context.get("immediate_steps"):
            for step in phd_context["immediate_steps"][:2]:
                step_text = step.split(":", 1)[-1].strip()
                lines.append(f"- {step_text}")
    lines.append("")

    # Suggested Focus Areas
    lines.append("## 💡 Additional Suggestions")
    if overnight_jobs:
        lines.append("- Review overnight job results")
    if papers:
        lines.append("- Skim relevant papers during breaks")
    if not next_actions and not goals_today:
        lines.append("- Work on immediate PhD steps listed above")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_phd_aware_morning_briefing(
    *,
    now: Optional[datetime] = None,
    state_dir: Optional[Path] = None,
    max_papers: int = 3,
    overnight_hours: int = 12,
) -> Path:
    """Generate morning briefing with PhD research awareness."""
    timestamp = _now_utc(now)
    base = _state_dir(state_dir)

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
        weather = WeatherAPI().current_weather()
    except Exception as exc:
        weather_error = str(exc)

    # Get PhD-relevant papers
    papers: list[dict[str, Any]] = []
    try:
        papers = _get_relevant_papers(max_results=max_papers)
    except Exception:
        papers = []

    # Get PhD context
    phd_context = _get_phd_context()

    # Build next actions (combining goals and PhD steps)
    next_actions = goals_today[:3]  # Top 3 daily goals
    if not next_actions and overnight_jobs:
        next_actions = [job.get("task", "Review overnight results") for job in overnight_jobs[:3]]
    if not next_actions and phd_context.get("immediate_steps"):
        # Extract clean text from immediate steps
        next_actions = [
            step.split(":", 1)[-1].strip()
            for step in phd_context["immediate_steps"][:3]
        ]

    # Build markdown
    output_dir = base / "inbox" / "morning"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y-%m-%d')}_phd_aware.md"
    output_path = output_dir / filename

    output_path.write_text(
        _build_phd_aware_markdown(
            timestamp,
            goals_today,
            overnight_jobs,
            weather,
            weather_error,
            papers,
            phd_context,
            next_actions
        ),
        encoding="utf-8",
    )

    # Store summary in memory
    summary_parts: list[str] = []
    if phd_context.get("current_year_projects"):
        summary_parts.append(f"PhD projects active: {len(phd_context['current_year_projects'])}")
    if goals_today:
        summary_parts.append("Goals: " + "; ".join(goals_today[:2]))
    if overnight_jobs:
        summary_parts.append(f"Overnight jobs: {len(overnight_jobs)}")

    if summary_parts:
        item = MemoryItem(
            agent="system",
            type="result",
            content=" | ".join(summary_parts),
            tags=["briefing", "morning", "phd-aware", f"date:{timestamp.strftime('%Y-%m-%d')}"],
            importance=0.4,
            source=str(output_path),
            evidence=[str(output_path)],
        )
        try:
            add_memory(item)
        except Exception:
            pass

    return output_path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate PhD-aware morning briefing.")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD)")
    parser.add_argument("--state-dir", help="Override base state directory")
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

    output_path = generate_phd_aware_morning_briefing(
        now=now,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        max_papers=args.max_papers,
        overnight_hours=args.overnight_hours,
    )
    print(f"PhD-aware morning briefing written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
