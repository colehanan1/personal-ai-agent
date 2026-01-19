#!/usr/bin/env python3
"""
Milton Configuration Diagnostics

Displays the effective configuration resolved from environment variables.
This ensures all Milton entrypoints use the same "brain" (state directory,
endpoints, memory backend).

Usage:
    python -m scripts.milton_config --print-effective
    python -m scripts.milton_config --json
"""
from __future__ import annotations

import argparse
import json
import sys

from milton_orchestrator.effective_config import (
    get_effective_config,
    print_effective_config,
)


def main() -> int:
    """Run configuration diagnostics."""
    parser = argparse.ArgumentParser(
        description="Display Milton's effective configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.milton_config --print-effective   # Human-readable format
  python -m scripts.milton_config --json              # JSON format
        """,
    )

    parser.add_argument(
        "--print-effective",
        action="store_true",
        help="Print effective configuration in human-readable format",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print effective configuration as JSON",
    )

    args = parser.parse_args()

    # Default to --print-effective if no args
    if not args.print_effective and not args.json:
        args.print_effective = True

    # Get effective configuration
    config = get_effective_config()

    # Print in requested format
    if args.json:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        print_effective_config(config)

    # Return non-zero if there are warnings
    return 1 if config.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
