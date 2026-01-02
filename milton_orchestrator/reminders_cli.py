"""Standalone CLI for Milton reminders system."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .reminders import (
    ReminderScheduler,
    ReminderStore,
    format_timestamp_local,
    parse_time_expression,
)
from .ntfy_client import NtfyClient
from .config import Config
from .state_paths import resolve_state_dir

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    """Get the database path from config or default."""
    return resolve_state_dir() / "reminders.sqlite3"


def get_ntfy_config() -> tuple[str, str, Optional[str]]:
    """Get ntfy configuration from environment."""
    base_url = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
    topic = os.getenv("NTFY_TOPIC")
    token = os.getenv("NTFY_TOKEN")

    if not topic:
        print("Error: NTFY_TOPIC environment variable is required", file=sys.stderr)
        print("Set it with: export NTFY_TOPIC=your-topic-name", file=sys.stderr)
        sys.exit(1)

    return base_url, topic, token


def cmd_add(args: argparse.Namespace) -> None:
    """Add a new reminder."""
    db_path = get_db_path()
    store = ReminderStore(db_path)

    # Parse the time
    timezone = args.timezone or os.getenv("TZ", "America/New_York")
    due_ts = parse_time_expression(args.when, timezone=timezone)

    if due_ts is None:
        print(f"Error: Could not parse time expression: {args.when}", file=sys.stderr)
        print("\nSupported formats:", file=sys.stderr)
        print("  - Relative: 'in 10m', 'in 2 hours', 'in 3 days'", file=sys.stderr)
        print("  - Time: 'at 14:30', 'at 9:00'", file=sys.stderr)
        print("  - Natural: 'tomorrow at 9am', 'next monday 3pm'", file=sys.stderr)
        print("  - Absolute: '2026-01-15 14:30'", file=sys.stderr)
        sys.exit(1)

    # Create the reminder
    kind = args.kind.upper()
    reminder_id = store.add_reminder(
        kind=kind,
        due_at=due_ts,
        message=args.message,
        timezone=timezone,
        delivery_target=args.target,
    )

    due_formatted = format_timestamp_local(due_ts, timezone)

    if args.json:
        print(json.dumps({
            "id": reminder_id,
            "kind": kind,
            "message": args.message,
            "due_at": due_ts,
            "due_formatted": due_formatted,
            "timezone": timezone,
        }))
    else:
        print(f"✓ Reminder created (ID: {reminder_id})")
        print(f"  Message: {args.message}")
        print(f"  Due: {due_formatted}")
        print(f"  Kind: {kind}")

    store.close()


def cmd_list(args: argparse.Namespace) -> None:
    """List reminders."""
    db_path = get_db_path()
    store = ReminderStore(db_path)

    reminders = store.list_reminders(
        include_sent=args.all,
        include_canceled=args.all,
    )

    if args.json:
        print(json.dumps([{
            "id": r.id,
            "kind": r.kind,
            "message": r.message,
            "due_at": r.due_at,
            "due_formatted": format_timestamp_local(r.due_at, r.timezone),
            "timezone": r.timezone,
            "created_at": r.created_at,
            "sent_at": r.sent_at,
            "canceled_at": r.canceled_at,
            "last_error": r.last_error,
        } for r in reminders], indent=2))
    else:
        if not reminders:
            print("No reminders found.")
        else:
            print(f"{'ID':<6} {'Due':<20} {'Kind':<8} {'Message':<50} {'Status':<10}")
            print("=" * 100)
            for r in reminders:
                status = "PENDING"
                if r.sent_at:
                    status = "SENT"
                if r.canceled_at:
                    status = "CANCELED"
                if r.last_error:
                    status = f"ERROR"

                due_str = format_timestamp_local(r.due_at, r.timezone)
                message = r.message[:47] + "..." if len(r.message) > 50 else r.message
                print(f"{r.id:<6} {due_str:<20} {r.kind:<8} {message:<50} {status:<10}")

                if args.verbose and r.last_error:
                    print(f"       Error: {r.last_error}")

    store.close()


def cmd_cancel(args: argparse.Namespace) -> None:
    """Cancel a reminder."""
    db_path = get_db_path()
    store = ReminderStore(db_path)

    # Check if reminder exists
    reminder = store.get_reminder(args.id)
    if not reminder:
        print(f"Error: Reminder {args.id} not found", file=sys.stderr)
        store.close()
        sys.exit(1)

    if reminder.sent_at:
        print(f"Error: Reminder {args.id} already sent", file=sys.stderr)
        store.close()
        sys.exit(1)

    if reminder.canceled_at:
        print(f"Error: Reminder {args.id} already canceled", file=sys.stderr)
        store.close()
        sys.exit(1)

    # Cancel it
    success = store.cancel_reminder(args.id)

    if success:
        if args.json:
            print(json.dumps({"id": args.id, "status": "canceled"}))
        else:
            print(f"✓ Reminder {args.id} canceled")
    else:
        print(f"Error: Failed to cancel reminder {args.id}", file=sys.stderr)
        sys.exit(1)

    store.close()


def cmd_run(args: argparse.Namespace) -> None:
    """Run the reminder scheduler daemon."""
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    db_path = get_db_path()
    base_url, topic, token = get_ntfy_config()

    logger.info("=" * 60)
    logger.info("Milton Reminders Scheduler")
    logger.info("=" * 60)
    logger.info(f"Database: {db_path}")
    logger.info(f"ntfy URL: {base_url}")
    logger.info(f"ntfy Topic: {topic}")
    logger.info(f"Timezone: {os.getenv('TZ', 'America/New_York')}")
    logger.info("=" * 60)

    # Create store and client
    store = ReminderStore(db_path)
    ntfy_client = NtfyClient(base_url)

    # Create publish function
    def publish_fn(message: str, title: str, reminder_id: int) -> bool:
        """Publish a reminder via ntfy."""
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            success = ntfy_client.publish(
                topic=topic,
                message=message,
                title=title,
                priority=4,  # High priority for reminders
            )
            return success
        except Exception as exc:
            logger.error(f"Failed to publish reminder {reminder_id}: {exc}")
            return False

    # Create and start scheduler
    scheduler = ReminderScheduler(
        store=store,
        publish_fn=publish_fn,
        interval_seconds=args.interval,
        max_retries=args.max_retries,
        retry_backoff=args.retry_backoff,
    )
    scheduler.start()

    logger.info("Scheduler started. Press Ctrl+C to stop.")

    try:
        # Keep main thread alive
        scheduler.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.stop()
        scheduler.join(timeout=5)
        store.close()
        logger.info("Stopped.")


def main():
    """Main CLI entrypoint for milton reminders."""
    parser = argparse.ArgumentParser(
        description="Milton Reminders - Persistent notification scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a reminder
  milton reminders add "Buy milk" --when "in 2 hours"
  milton reminders add "Team meeting" --when "tomorrow at 9am"
  milton reminders add "Dentist appointment" --when "2026-01-15 14:30"

  # List reminders
  milton reminders list
  milton reminders list --all  # Include sent/canceled

  # Cancel a reminder
  milton reminders cancel 42

  # Run the scheduler daemon
  milton reminders run
  milton reminders run --verbose

Environment Variables:
  NTFY_BASE_URL     ntfy server URL (default: https://ntfy.sh)
  NTFY_TOPIC        ntfy topic for notifications (REQUIRED)
  NTFY_TOKEN        ntfy authentication token (optional)
  STATE_DIR         Directory for database (default: ~/.local/state/milton)
  TZ                Timezone (default: America/New_York)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new reminder")
    add_parser.add_argument("message", help="Reminder message")
    add_parser.add_argument("--when", "-w", required=True, help="When to remind (e.g., 'in 2h', 'tomorrow at 9am')")
    add_parser.add_argument("--kind", "-k", default="REMIND", help="Reminder kind (default: REMIND)")
    add_parser.add_argument("--target", "-t", help="Delivery target (optional)")
    add_parser.add_argument("--timezone", "-z", help="Timezone (default: from TZ env or America/New_York)")
    add_parser.add_argument("--json", action="store_true", help="Output JSON")
    add_parser.set_defaults(func=cmd_add)

    # List command
    list_parser = subparsers.add_parser("list", help="List reminders")
    list_parser.add_argument("--all", "-a", action="store_true", help="Include sent and canceled reminders")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="Show error details")
    list_parser.add_argument("--json", action="store_true", help="Output JSON")
    list_parser.set_defaults(func=cmd_list)

    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a reminder")
    cancel_parser.add_argument("id", type=int, help="Reminder ID to cancel")
    cancel_parser.add_argument("--json", action="store_true", help="Output JSON")
    cancel_parser.set_defaults(func=cmd_cancel)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the reminder scheduler daemon")
    run_parser.add_argument("--interval", "-i", type=int, default=5, help="Check interval in seconds (default: 5)")
    run_parser.add_argument("--max-retries", type=int, default=3, help="Max retry attempts (default: 3)")
    run_parser.add_argument("--retry-backoff", type=int, default=60, help="Retry backoff in seconds (default: 60)")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
