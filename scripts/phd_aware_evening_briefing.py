#!/usr/bin/env python3
"""PhD-aware evening briefing with research progress reflection."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import argparse
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv()

from goals.api import list_goals
from memory.schema import MemoryItem
from memory.store import add_memory, get_user_profile
from memory.retrieve import query_relevant
import milton_queue as queue_api
from scripts.evening_briefing import (
    _state_dir,
    _now_utc,
    _split_items,
    _prompt_list,
    _read_stdin_payload,
    _coerce_list,
    _summarize_goals
)


def _get_phd_reflection_context() -> dict[str, Any]:
    """Get PhD context for evening reflection."""
    # Query for recent PhD-related activities
    recent_phd = query_relevant(
        "PhD research olfactory BCI project progress today",
        limit=8,
        recency_bias=0.8  # Emphasize recent activities
    )

    # Categorize memories
    today_activities = []
    blockers = []
    progress = []

    for mem in recent_phd:
        if "phd" in mem.tags or "research" in mem.tags:
            # Check if it's from today (rough approximation)
            content_lower = mem.content.lower()
            if any(word in content_lower for word in ["completed", "finished", "done", "implemented"]):
                progress.append(mem.content)
            elif any(word in content_lower for word in ["blocked", "issue", "problem", "stuck"]):
                blockers.append(mem.content)
            else:
                today_activities.append(mem.content)

    # Get user profile for current year info
    profile = get_user_profile()
    current_year_fact = None
    for fact in profile.stable_facts:
        if "current year" in fact.lower():
            current_year_fact = fact
            break

    return {
        "today_activities": today_activities[:3],
        "progress": progress[:5],
        "blockers": blockers[:3],
        "current_year": current_year_fact
    }


def _collect_phd_aware_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Collect evening briefing inputs with PhD awareness."""
    stdin_payload = _read_stdin_payload() if args.use_stdin or not sys.stdin.isatty() else {}

    summary = args.summary or stdin_payload.get("summary", "")
    wins = _split_items(args.wins or []) + _coerce_list(stdin_payload.get("wins"))
    blockers = _split_items(args.blockers or []) + _coerce_list(stdin_payload.get("blockers"))
    tomorrow = _split_items(args.tomorrow or []) + _coerce_list(stdin_payload.get("tomorrow"))
    notes = _split_items(args.notes or []) + _coerce_list(stdin_payload.get("notes"))
    jobs = _split_items(args.jobs or []) + _coerce_list(stdin_payload.get("jobs"))

    # PhD-specific inputs
    phd_progress = _split_items(args.phd_progress or []) + _coerce_list(stdin_payload.get("phd_progress"))
    papers_read = _split_items(args.papers_read or []) + _coerce_list(stdin_payload.get("papers_read"))

    if args.non_interactive:
        return {
            "summary": summary,
            "wins": wins,
            "blockers": blockers,
            "tomorrow": tomorrow,
            "notes": notes,
            "jobs": jobs,
            "phd_progress": phd_progress,
            "papers_read": papers_read,
        }

    # Interactive prompts
    if not summary:
        summary = input("Day summary: ").strip()
    if not wins:
        wins = _prompt_list("Wins")
    if not phd_progress:
        phd_progress = _prompt_list("PhD research progress today")
    if not blockers:
        blockers = _prompt_list("Blockers")
    if not papers_read:
        papers_read = _prompt_list("Papers read/skimmed today (optional)")
    if not tomorrow:
        tomorrow = _prompt_list("Tomorrow priorities (including PhD)")
    if not notes:
        notes = _prompt_list("Notes/decisions")
    if not jobs:
        jobs = _prompt_list("Overnight jobs to queue")

    return {
        "summary": summary,
        "wins": wins,
        "blockers": blockers,
        "tomorrow": tomorrow,
        "notes": notes,
        "jobs": jobs,
        "phd_progress": phd_progress,
        "papers_read": papers_read,
    }


def _build_phd_aware_evening_markdown(
    now: datetime,
    data: dict[str, Any],
    job_ids: list[str],
    active_goals: list[str],
    goal_scope: str,
    phd_context: dict[str, Any],
) -> str:
    """Build evening briefing markdown with PhD awareness."""
    date_label = now.strftime("%Y-%m-%d (%A)")
    lines = [
        f"# Evening Briefing - {date_label}",
        "",
        f"Captured at: {now.strftime('%I:%M %p')}",
        "",
        "=" * 70,
        ""
    ]

    # Day Summary
    if data.get("summary"):
        lines.extend(["## 📝 Day Summary", data["summary"].strip(), ""])

    # PhD Research Progress Section
    lines.append("## 🎓 PhD Research Progress")
    if data.get("phd_progress"):
        for item in data["phd_progress"]:
            lines.append(f"- {item}")
    elif phd_context.get("progress"):
        for item in phd_context["progress"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No explicit PhD progress recorded")
    lines.append("")

    # Papers Read
    if data.get("papers_read"):
        lines.append("## 📄 Papers Read/Skimmed")
        for paper in data["papers_read"]:
            lines.append(f"- {paper}")
        lines.append("")

    # General Wins
    wins = [w for w in data.get("wins", []) if w]
    if wins:
        lines.append("## ✓ Wins")
        lines.extend([f"- {item}" for item in wins])
        lines.append("")

    # Blockers
    all_blockers = list(data.get("blockers", []))
    if phd_context.get("blockers"):
        all_blockers.extend(phd_context["blockers"])
    all_blockers = [b for b in all_blockers if b]

    if all_blockers:
        lines.append("## ⚠️ Blockers")
        for item in all_blockers:
            lines.append(f"- {item}")
        lines.append("")

    # Tomorrow Priorities
    tomorrow = [t for t in data.get("tomorrow", []) if t]
    if tomorrow:
        lines.append("## 📅 Tomorrow Priorities")
        lines.extend([f"- {item}" for item in tomorrow])
        lines.append("")

    # Notes/Decisions
    notes = [n for n in data.get("notes", []) if n]
    if notes:
        lines.append("## 💭 Notes / Decisions")
        lines.extend([f"- {item}" for item in notes])
        lines.append("")

    # Active Goals
    lines.append("## 🎯 Active Goals")
    if active_goals:
        lines.extend([f"- {goal}" for goal in active_goals])
        lines.append(f"- Scope: {goal_scope}")
    else:
        lines.append("- No active goals")
    if phd_context.get("current_year"):
        lines.append(f"- PhD: {phd_context['current_year']}")
    lines.append("")

    # Overnight Jobs
    lines.append("## 🌙 Overnight Jobs")
    if job_ids:
        for job_id, job_text in zip(job_ids, data.get("jobs", [])):
            lines.append(f"- {job_id}: {job_text}")
    elif data.get("jobs"):
        for job_text in data.get("jobs", []):
            lines.append(f"- {job_text}")
    else:
        lines.append("- None queued")
    lines.append("")

    # Reflection prompt
    lines.append("## 🤔 Reflection")
    lines.append("- Did today's work move PhD goals forward?")
    lines.append("- What's the next smallest step for current project?")
    lines.append("- Any papers/techniques to explore tomorrow?")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def _store_phd_aware_summary(
    now: datetime,
    data: dict[str, Any],
    output_path: Path,
    state_dir: Path
) -> None:
    """Store evening summary with PhD progress in memory."""
    summary_parts: list[str] = []

    if data.get("summary"):
        summary_parts.append(f"Summary: {data['summary']}")
    if data.get("phd_progress"):
        summary_parts.append("PhD: " + "; ".join(data["phd_progress"][:2]))
    if data.get("papers_read"):
        summary_parts.append(f"Papers: {len(data['papers_read'])}")
    if data.get("tomorrow"):
        summary_parts.append("Tomorrow: " + "; ".join(data["tomorrow"][:2]))
    if data.get("wins"):
        summary_parts.append("Wins: " + "; ".join(data["wins"][:2]))
    if data.get("blockers"):
        summary_parts.append("Blockers: " + "; ".join(data["blockers"][:2]))

    content = " | ".join(summary_parts).strip()
    if not content:
        return

    item = MemoryItem(
        agent="system",
        type="result",
        content=content,
        tags=["briefing", "evening", "phd-aware", f"date:{now.strftime('%Y-%m-%d')}"],
        importance=0.5,
        source=str(output_path),
        evidence=[str(output_path)],
    )
    try:
        add_memory(item, repo_root=state_dir)
    except Exception:
        pass


def generate_phd_aware_evening_briefing(
    *,
    now: Optional[datetime] = None,
    state_dir: Optional[Path] = None,
    inputs: Optional[dict[str, Any]] = None,
) -> Path:
    """Generate evening briefing with PhD research awareness."""
    timestamp = _now_utc(now)
    base = _state_dir(state_dir)
    data = inputs or {
        "summary": "",
        "wins": [],
        "blockers": [],
        "tomorrow": [],
        "notes": [],
        "jobs": [],
        "phd_progress": [],
        "papers_read": [],
    }

    # Queue overnight jobs
    job_ids: list[str] = []
    for job_text in data.get("jobs", []) or []:
        job_id = queue_api.enqueue_job(
            "cortex_task",
            {"task": job_text},
            priority="medium",
            base_dir=base,
            now=timestamp,
        )
        job_ids.append(job_id)

    # Get active goals
    active_goals = _summarize_goals(list_goals("daily", base_dir=base))
    goal_scope = "daily"
    if not active_goals:
        active_goals = _summarize_goals(list_goals("weekly", base_dir=base))
        goal_scope = "weekly"

    # Get PhD context
    phd_context = _get_phd_reflection_context()

    # Build and save markdown
    output_dir = base / "inbox" / "evening"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y-%m-%d')}_phd_aware.md"
    output_path = output_dir / filename

    output_path.write_text(
        _build_phd_aware_evening_markdown(
            timestamp,
            data,
            job_ids,
            active_goals,
            goal_scope,
            phd_context
        ),
        encoding="utf-8",
    )

    # Store summary in memory
    _store_phd_aware_summary(timestamp, data, output_path, base)

    return output_path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate PhD-aware evening briefing and queue overnight jobs."
    )
    parser.add_argument("--summary", help="Day summary text")
    parser.add_argument("--wins", action="append", default=[], help="Wins (repeatable, comma-separated)")
    parser.add_argument("--phd-progress", action="append", default=[], help="PhD progress (repeatable)")
    parser.add_argument("--papers-read", action="append", default=[], help="Papers read (repeatable)")
    parser.add_argument("--blockers", action="append", default=[], help="Blockers (repeatable, comma-separated)")
    parser.add_argument("--tomorrow", action="append", default=[], help="Tomorrow priorities (repeatable)")
    parser.add_argument("--notes", action="append", default=[], help="Notes or decisions (repeatable)")
    parser.add_argument("--jobs", action="append", default=[], help="Overnight jobs (repeatable)")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD)")
    parser.add_argument("--state-dir", help="Override base state directory")
    parser.add_argument("--use-stdin", action="store_true", help="Read JSON payload from stdin")
    parser.add_argument("--non-interactive", action="store_true", help="Skip prompts for missing fields")

    args = parser.parse_args()

    now = None
    if args.date:
        try:
            now = datetime.fromisoformat(args.date)
        except ValueError:
            print("Invalid --date format; expected YYYY-MM-DD", file=sys.stderr)
            return 2

    data = _collect_phd_aware_inputs(args)
    output_path = generate_phd_aware_evening_briefing(
        now=now,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        inputs=data,
    )
    print(f"PhD-aware evening briefing written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
