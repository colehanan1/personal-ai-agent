#!/usr/bin/env python3
"""
PhD-aware morning briefing (backward compatibility wrapper).

This script now calls the unified enhanced_morning_briefing.py with --phd-aware flag.
The enhanced script auto-detects PhD mode, but this wrapper forces it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
import argparse
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv()

from scripts.enhanced_morning_briefing import generate_morning_briefing


def generate_phd_aware_morning_briefing(
    *,
    now: Optional[datetime] = None,
    state_dir: Optional[Path] = None,
    max_papers: int = 3,
    overnight_hours: int = 12,
) -> Path:
    """
    Generate morning briefing with PhD research awareness.

    This is a compatibility wrapper that calls the unified enhanced_morning_briefing
    with phd_aware=True.
    """
    return generate_morning_briefing(
        now=now,
        state_dir=state_dir,
        max_papers=max_papers,
        overnight_hours=overnight_hours,
        phd_aware=True,  # Force PhD mode
    )


def main() -> int:
    """Main entry point (backward compatibility)."""
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
