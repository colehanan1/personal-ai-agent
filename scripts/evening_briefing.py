#!/usr/bin/env python3
"""Generate an evening briefing, queue overnight jobs, and store summary memory."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import argparse
import json
import sys

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

from goals.api import list_goals
from memory.schema import MemoryItem
from memory.store import add_memory
import milton_queue as queue_api
from milton_orchestrator.state_paths import resolve_state_dir


def _state_dir(base_dir: Optional[Path] = None) -> Path:
    return resolve_state_dir(base_dir)


def _now_utc(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _split_items(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        for part in parts:
            if part:
                items.append(part)
    return items


def _prompt_list(prompt: str) -> list[str]:
    print(f"{prompt} (one per line, blank to finish)")
    entries: list[str] = []
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            break
        entries.append(line)
    return entries


def _read_stdin_payload() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    data = sys.stdin.read().strip()
    if not data:
        return {}
    if data.startswith("{"):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {"summary": data}
    return {"summary": data}


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _summarize_goals(goals: list[dict[str, Any]], limit: int = 5) -> list[str]:
    items: list[str] = []
    for goal in goals:
        text = str(goal.get("text", "")).strip()
        if not text:
            continue
        items.append(text)
    return items[:limit]


def _collect_inputs(args: argparse.Namespace) -> dict[str, Any]:
    stdin_payload = _read_stdin_payload() if args.use_stdin or not sys.stdin.isatty() else {}

    summary = args.summary or stdin_payload.get("summary", "")
    wins = _split_items(args.wins or []) + _coerce_list(stdin_payload.get("wins"))
    blockers = _split_items(args.blockers or []) + _coerce_list(stdin_payload.get("blockers"))
    tomorrow = _split_items(args.tomorrow or []) + _coerce_list(stdin_payload.get("tomorrow"))
    notes = _split_items(args.notes or []) + _coerce_list(stdin_payload.get("notes"))
    jobs = _split_items(args.jobs or []) + _coerce_list(stdin_payload.get("jobs"))

    if args.non_interactive:
        return {
            "summary": summary,
            "wins": wins,
            "blockers": blockers,
            "tomorrow": tomorrow,
            "notes": notes,
            "jobs": jobs,
        }

    if not summary:
        summary = input("Day summary: ").strip()
    if not wins:
        wins = _prompt_list("Wins")
    if not blockers:
        blockers = _prompt_list("Blockers")
    if not tomorrow:
        tomorrow = _prompt_list("Tomorrow priorities")
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
    }


def _build_markdown(
    now: datetime,
    data: dict[str, Any],
    job_ids: list[str],
    active_goals: list[str],
    goal_scope: str,
) -> str:
    date_label = now.strftime("%Y-%m-%d")
    lines = [f"# Evening Briefing - {date_label}", "", f"Captured at: {now.isoformat()}", ""]

    if data.get("summary"):
        lines.extend(["## Day Summary", data["summary"].strip(), ""])

    for section, key in (
        ("Wins", "wins"),
        ("Blockers", "blockers"),
        ("Tomorrow Priorities", "tomorrow"),
        ("Notes / Decisions", "notes"),
    ):
        items = [item for item in data.get(key, []) if item]
        if not items:
            continue
        lines.append(f"## {section}")
        lines.extend([f"- {item}" for item in items])
        lines.append("")

    lines.append("## Active Goals")
    if active_goals:
        lines.extend([f"- {goal}" for goal in active_goals])
        lines.append(f"- Scope: {goal_scope}")
    else:
        lines.append("- No active goals")
    lines.append("")

    lines.append("## Overnight Jobs")
    if job_ids:
        for job_id, job_text in zip(job_ids, data.get("jobs", [])):
            lines.append(f"- {job_id}: {job_text}")
    elif data.get("jobs"):
        for job_text in data.get("jobs", []):
            lines.append(f"- {job_text}")
    else:
        lines.append("- None queued")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def _store_summary(now: datetime, data: dict[str, Any], output_path: Path, state_dir: Path) -> None:
    summary_parts: list[str] = []
    if data.get("summary"):
        summary_parts.append(f"Summary: {data['summary']}")
    if data.get("tomorrow"):
        summary_parts.append("Tomorrow: " + "; ".join(data["tomorrow"]))
    if data.get("wins"):
        summary_parts.append("Wins: " + "; ".join(data["wins"]))
    if data.get("blockers"):
        summary_parts.append("Blockers: " + "; ".join(data["blockers"]))

    content = " | ".join(summary_parts).strip()
    if not content:
        return

    item = MemoryItem(
        agent="system",
        type="result",
        content=content,
        tags=["briefing", "evening", f"date:{now.strftime('%Y-%m-%d')}"],
        importance=0.4,
        source=str(output_path),
        evidence=[str(output_path)],
    )
    try:
        add_memory(item, repo_root=state_dir)
    except Exception:
        pass


def generate_evening_briefing(
    *,
    now: Optional[datetime] = None,
    state_dir: Optional[Path] = None,
    inputs: Optional[dict[str, Any]] = None,
) -> Path:
    timestamp = _now_utc(now)
    base = _state_dir(state_dir)
    data = inputs or {"summary": "", "wins": [], "blockers": [], "tomorrow": [], "notes": [], "jobs": []}

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

    active_goals = _summarize_goals(list_goals("daily", base_dir=base))
    goal_scope = "daily"
    if not active_goals:
        active_goals = _summarize_goals(list_goals("weekly", base_dir=base))
        goal_scope = "weekly"

    output_dir = base / "inbox" / "evening"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y-%m-%d')}.md"
    output_path = output_dir / filename

    output_path.write_text(
        _build_markdown(timestamp, data, job_ids, active_goals, goal_scope),
        encoding="utf-8",
    )
    _store_summary(timestamp, data, output_path, base)

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate evening briefing and queue overnight jobs.")
    parser.add_argument("--summary", help="Day summary text")
    parser.add_argument("--wins", action="append", default=[], help="Wins (repeatable, comma-separated)")
    parser.add_argument("--blockers", action="append", default=[], help="Blockers (repeatable, comma-separated)")
    parser.add_argument("--tomorrow", action="append", default=[], help="Tomorrow priorities (repeatable, comma-separated)")
    parser.add_argument("--notes", action="append", default=[], help="Notes or decisions (repeatable, comma-separated)")
    parser.add_argument("--jobs", action="append", default=[], help="Overnight jobs to queue (repeatable, comma-separated)")
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

    data = _collect_inputs(args)
    output_path = generate_evening_briefing(
        now=now,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        inputs=data,
    )
    print(f"Evening briefing written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
