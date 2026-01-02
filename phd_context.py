"""
PhD Context Module - System-wide PhD research awareness.

This module provides PhD research context to all components of Milton:
- Memory retrieval prioritizes PhD-related content
- Goals are aligned with PhD timeline
- Agent responses include PhD awareness
- Briefings track PhD progress

Usage:
    from phd_context import get_phd_context, get_current_projects, is_phd_related
"""
from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

from memory.retrieve import query_relevant
from memory.store import get_user_profile


# PhD Research Timeline Configuration
PHD_START_DATE = datetime(2025, 9, 1, tzinfo=timezone.utc)  # Adjust to your actual start date
PHD_DURATION_MONTHS = 54  # 4.5 years


def get_months_into_phd(now: Optional[datetime] = None) -> int:
    """Calculate how many months into the PhD program."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = current - PHD_START_DATE
    return max(0, int(delta.days / 30))


def get_current_year() -> int:
    """Get current PhD year (1-4)."""
    months = get_months_into_phd()
    return min(4, (months // 12) + 1)


def get_current_projects() -> list[str]:
    """Get projects for current year based on timeline."""
    year = get_current_year()

    project_timeline = {
        1: ["1.1", "1.2", "1.3"],  # Year 1
        2: ["2.1", "2.2", "2.3"],  # Year 2
        3: ["3.1", "3.2", "3.3"],  # Year 3
        4: ["4.1", "4.2", "4.3"],  # Year 4
    }

    return project_timeline.get(year, ["1.1", "1.2", "1.3"])


def get_phd_context(query: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
    """
    Get comprehensive PhD context from long-term memory.

    Args:
        query: Optional specific query, otherwise gets general PhD context
        limit: Maximum number of memory items to retrieve

    Returns:
        Dictionary with PhD context including:
        - overall_goal: Main PhD objective
        - current_year: Current year (1-4)
        - current_projects: Active projects for current year
        - immediate_steps: Next steps to take
        - recent_progress: Recent PhD-related work
        - papers_read: Recently read papers
        - blockers: Current blockers
    """
    # Build query based on current context
    year = get_current_year()
    months = get_months_into_phd()

    if query is None:
        query = f"PhD olfactory BCI year {year} current projects progress"

    # Retrieve PhD-related memories with lower recency bias (long-term goals matter)
    memories = query_relevant(
        query,
        limit=limit,
        recency_bias=0.2  # Emphasize relevance over recency
    )

    # Get user profile for stable facts
    profile = get_user_profile()
    phd_facts = [f for f in profile.stable_facts if "phd" in f.lower() or "research" in f.lower()]

    # Categorize memories
    overall_goal = None
    current_year_projects = []
    immediate_steps = []
    recent_progress = []
    papers_read = []
    blockers = []

    for mem in memories:
        tags = set(mem.tags)
        content = mem.content

        # Overall goal
        if "long-term-goal" in tags and not overall_goal:
            overall_goal = content

        # Current year projects
        if f"year-{year}" in tags and "project-" in " ".join(tags):
            current_year_projects.append(content)

        # Immediate steps
        if "immediate-action" in tags or "next-step" in tags:
            immediate_steps.append(content)

        # Recent progress
        if "phd-aware" in tags and "result" in mem.type:
            recent_progress.append(content)

        # Papers
        if "papers" in content.lower() and "read" in content.lower():
            papers_read.append(content)

        # Blockers
        if "blocker" in content.lower() or "stuck" in content.lower():
            blockers.append(content)

    return {
        "overall_goal": overall_goal,
        "current_year": year,
        "months_into_phd": months,
        "current_projects": current_year_projects[:3],
        "immediate_steps": immediate_steps[:5],
        "recent_progress": recent_progress[:5],
        "papers_read": papers_read[:5],
        "blockers": blockers[:3],
        "phd_facts": phd_facts,
        "project_ids": get_current_projects(),
    }


def is_phd_related(text: str) -> bool:
    """Check if text is related to PhD research."""
    phd_keywords = {
        "phd", "dissertation", "thesis", "research",
        "olfactory", "bci", "brain-computer interface",
        "drosophila", "fruit fly", "calcium imaging",
        "connectome", "flywire", "decoding", "encoding",
        "orns", "pns", "kcs", "glomeruli", "antennal lobe",
        "mushroom body", "odor", "odorant", "olfaction",
        "2-photon", "gcamp", "imaging", "electrophysiology",
        "paper", "publication", "patent", "experiment",
        "protocol", "advisor", "lab", "flies"
    }

    text_lower = text.lower()
    return any(keyword in text_lower for keyword in phd_keywords)


def get_phd_tags(include_year: bool = True) -> list[str]:
    """Get standard tags for PhD-related memories."""
    tags = ["phd", "research", "olfactory-bci"]
    if include_year:
        tags.append(f"year-{get_current_year()}")
    return tags


def format_phd_reminder() -> str:
    """Format a brief PhD reminder for agent context."""
    year = get_current_year()
    months = get_months_into_phd()
    projects = get_current_projects()

    return (
        f"PhD Context: Year {year} (Month {months}), "
        f"Active Projects: {', '.join(projects)}, "
        f"Focus: Olfactory BCI (decode + encode)"
    )


def should_include_phd_context(message: str) -> bool:
    """
    Determine if PhD context should be included in response.

    Always includes PhD context if:
    - Message is PhD-related
    - It's a planning/goal-setting request
    - It's a research question
    - User asks about progress/status
    """
    if is_phd_related(message):
        return True

    planning_keywords = {"plan", "goal", "progress", "status", "timeline", "next"}
    research_keywords = {"research", "paper", "study", "experiment", "analyze"}

    msg_lower = message.lower()

    if any(keyword in msg_lower for keyword in planning_keywords):
        return True

    if any(keyword in msg_lower for keyword in research_keywords):
        return True

    return False


def get_phd_summary_for_agent() -> str:
    """
    Get a concise PhD summary to include in agent system prompts.

    This should be added to the system prompt of all agents so they're
    always aware of the user's PhD research context.
    """
    context = get_phd_context()
    year = context["current_year"]
    projects = ", ".join(context["project_ids"])

    summary = [
        "USER CONTEXT - PhD Research:",
        f"- PhD student in Year {year} of neuroscience program",
        f"- Focus: Olfactory brain-computer interface (BCI) in Drosophila",
        f"- Current projects: {projects}",
        "- Goal: 6-8 high-impact publications + 2-3 patents → startup",
    ]

    if context.get("immediate_steps"):
        summary.append("- Immediate priorities:")
        for step in context["immediate_steps"][:3]:
            step_text = step.split(":", 1)[-1].strip()
            summary.append(f"  • {step_text[:80]}")

    return "\n".join(summary)


# Export main functions
__all__ = [
    "get_phd_context",
    "get_current_year",
    "get_current_projects",
    "is_phd_related",
    "get_phd_tags",
    "format_phd_reminder",
    "should_include_phd_context",
    "get_phd_summary_for_agent",
    "get_months_into_phd",
]
