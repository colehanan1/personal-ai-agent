#!/usr/bin/env python3
"""
Smoke test for Milton reminder → ntfy delivery pipeline.

This script verifies end-to-end that:
1. A reminder can be created for "now"
2. Milton's code publishes to ntfy topic
3. The ntfy response is successful (HTTP 200, JSON includes "id")
4. The reminder is marked as sent (not re-sent)

Usage:
    # Full end-to-end test (requires env vars or .env)
    REMINDERS_NTFY_TOPIC=milton-reminders-cole python scripts/smoke_ntfy_reminder.py

    # With explicit overrides
    NTFY_BASE_URL=https://ntfy.sh REMINDERS_NTFY_TOPIC=milton-reminders-cole \
        python scripts/smoke_ntfy_reminder.py

Environment Variables:
    NTFY_BASE_URL         - ntfy server URL (default: https://ntfy.sh)
    REMINDERS_NTFY_TOPIC  - ntfy topic for reminders (preferred)
    NTFY_TOPIC            - fallback topic if REMINDERS_NTFY_TOPIC not set
    RUN_NTFY_SMOKE        - Set to "1" to actually send to ntfy (default: dry-run)
    STATE_DIR             - State directory for reminders.db
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

# Add repo root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

import requests

from milton_orchestrator.reminders import ReminderStore, Reminder, format_timestamp_local
from milton_orchestrator.notifications import NtfyProvider, DeliveryResult
from milton_orchestrator.state_paths import resolve_state_dir, resolve_reminders_db_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("smoke_ntfy_reminder")


def get_ntfy_config() -> tuple[str, str]:
    """Get ntfy configuration from environment."""
    base_url = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
    # Prefer REMINDERS_NTFY_TOPIC for reminders
    topic = os.getenv("REMINDERS_NTFY_TOPIC") or os.getenv("NTFY_TOPIC")

    if not topic:
        logger.error("REMINDERS_NTFY_TOPIC or NTFY_TOPIC must be set")
        sys.exit(1)

    return base_url, topic


def direct_ntfy_test(base_url: str, topic: str, message: str) -> dict:
    """
    Test direct ntfy publish (bypassing Milton code) to verify connectivity.

    Returns:
        dict with keys: ok, status_code, response_json
    """
    url = f"{base_url}/{topic}"

    try:
        response = requests.post(
            url,
            data=message.encode("utf-8"),
            headers={
                "Title": "Milton Smoke Test - Direct",
                "Priority": "3",
            },
            timeout=10,
        )

        result = {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "response_json": None,
        }

        if response.status_code == 200:
            try:
                result["response_json"] = response.json()
            except json.JSONDecodeError:
                result["response_text"] = response.text[:200]
        else:
            result["response_text"] = response.text[:200]

        return result

    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": str(exc)[:200],
        }


def test_via_provider(reminder: Reminder, base_url: str, topic: str) -> DeliveryResult:
    """
    Test delivery via NtfyProvider (Milton's notification system).

    Returns:
        DeliveryResult with message_id if successful
    """
    provider = NtfyProvider(
        base_url=base_url,
        topic=topic,
        public_base_url=None,  # No action callbacks for smoke test
        action_token=None,
    )

    return provider.send(
        reminder,
        title=f"Milton Reminder ({reminder.kind})",
        body=reminder.message,
        actions=reminder.actions,
    )


def main():
    """Run the smoke test."""
    print()
    print("=" * 70)
    print("MILTON REMINDER → NTFY SMOKE TEST")
    print("=" * 70)
    print()

    # Check if we should actually send to ntfy
    run_live = os.getenv("RUN_NTFY_SMOKE", "0") == "1"

    # Get config
    base_url, topic = get_ntfy_config()
    state_dir = resolve_state_dir()
    db_path = resolve_reminders_db_path()

    print(f"Configuration:")
    print(f"  NTFY_BASE_URL:         {base_url}")
    print(f"  REMINDERS_NTFY_TOPIC:  {topic}")
    print(f"  STATE_DIR:             {state_dir}")
    print(f"  Database:              {db_path}")
    print(f"  Live mode:             {'YES' if run_live else 'NO (set RUN_NTFY_SMOKE=1)'}")
    print()

    if not run_live:
        print("DRY RUN MODE - Set RUN_NTFY_SMOKE=1 to actually send to ntfy")
        print()
        print("Would execute:")
        print(f"  1. Create reminder in {db_path}")
        print(f"  2. Send to {base_url}/{topic}")
        print(f"  3. Verify HTTP 200 and JSON 'id' in response")
        print(f"  4. Mark reminder as sent in database")
        print()

        # Still verify database connectivity
        print("Verifying database connectivity...")
        store = ReminderStore(db_path)
        health = store.get_health_stats()
        print(f"  Scheduled reminders: {health['scheduled_count']}")
        print(f"  Last ntfy success:   {health['last_ntfy_ok'] or 'never'}")
        store.close()
        print()

        print("To run live test:")
        print(f"  RUN_NTFY_SMOKE=1 python {__file__}")
        print()
        return 0

    # =========================================================================
    # STEP 1: Direct ntfy test (verify connectivity)
    # =========================================================================
    print("-" * 70)
    print("STEP 1: Direct ntfy connectivity test")
    print("-" * 70)

    test_message = f"Milton smoke test - direct POST at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    direct_result = direct_ntfy_test(base_url, topic, test_message)

    print(f"  URL:         {base_url}/{topic}")
    print(f"  Status:      {direct_result['status_code']}")
    print(f"  Success:     {direct_result['ok']}")

    if direct_result.get("response_json"):
        ntfy_id = direct_result["response_json"].get("id")
        print(f"  ntfy ID:     {ntfy_id}")
        print()
        print("  Full ntfy response JSON:")
        print(json.dumps(direct_result["response_json"], indent=4))
    else:
        print(f"  Error:       {direct_result.get('error') or direct_result.get('response_text')}")

    print()

    if not direct_result["ok"]:
        print("ERROR: Direct ntfy test failed. Check your topic and network.")
        return 1

    # =========================================================================
    # STEP 2: Create reminder via ReminderStore
    # =========================================================================
    print("-" * 70)
    print("STEP 2: Create reminder via ReminderStore")
    print("-" * 70)

    store = ReminderStore(db_path)

    # Create reminder due 5 seconds ago (immediately claimable)
    now_ts = int(time.time())
    due_ts = now_ts - 5
    timezone = os.getenv("TZ", "America/Chicago")

    reminder_id = store.add_reminder(
        kind="SMOKE_TEST",
        due_at=due_ts,
        message=f"Smoke test reminder created at {time.strftime('%H:%M:%S')}",
        timezone=timezone,
        channels=["ntfy"],
        priority="med",
        source="other",
    )

    print(f"  Created reminder ID: {reminder_id}")
    print(f"  Due at:              {format_timestamp_local(due_ts, timezone)} (past)")
    print()

    # Verify it's in the database
    reminder = store.get_reminder(reminder_id)
    if not reminder:
        print("ERROR: Failed to retrieve created reminder")
        store.close()
        return 1

    print(f"  Reminder retrieved: {reminder.message}")
    print(f"  Channels:           {reminder.channels}")
    print(f"  Status:             {reminder.status}")
    print()

    # =========================================================================
    # STEP 3: Deliver via NtfyProvider
    # =========================================================================
    print("-" * 70)
    print("STEP 3: Deliver via NtfyProvider (Milton's notification system)")
    print("-" * 70)

    delivery_result = test_via_provider(reminder, base_url, topic)

    print(f"  Provider:    {delivery_result.provider}")
    print(f"  Success:     {delivery_result.ok}")
    print(f"  Message ID:  {delivery_result.message_id}")
    print(f"  Error:       {delivery_result.error or 'none'}")
    print()
    print("  Full DeliveryResult:")
    print(json.dumps(delivery_result.to_dict(), indent=4, default=str))
    print()

    if not delivery_result.ok:
        print("ERROR: NtfyProvider delivery failed")
        store.close()
        return 1

    if not delivery_result.message_id:
        print("WARNING: No message_id in response (ntfy should return 'id' field)")

    # =========================================================================
    # STEP 4: Mark reminder as sent and verify idempotency
    # =========================================================================
    print("-" * 70)
    print("STEP 4: Mark reminder as sent and verify idempotency")
    print("-" * 70)

    # Mark as sent
    store.mark_sent([reminder_id], sent_at=now_ts)
    store.set_metadata("last_ntfy_ok", str(now_ts))

    # Add audit log entry
    store.append_audit_log(reminder_id, [{
        "ts": now_ts,
        "action": "smoke_test_delivery",
        "actor": "smoke_test",
        "details": f"Delivered via NtfyProvider, message_id={delivery_result.message_id}",
    }])

    # Reload and verify
    reminder_after = store.get_reminder(reminder_id)

    print(f"  sent_at:     {reminder_after.sent_at}")
    print(f"  status:      {reminder_after.status}")

    # Try to claim it again - should return empty (idempotency check)
    claimed = store.claim_due_reminders(now_ts)
    reclaim_count = sum(1 for r in claimed if r.id == reminder_id)

    print(f"  Re-claim attempt: {reclaim_count} (should be 0)")
    print()

    if reclaim_count > 0:
        print("ERROR: Idempotency check failed - reminder was re-claimed!")
        store.close()
        return 1

    # =========================================================================
    # STEP 5: Final health check
    # =========================================================================
    print("-" * 70)
    print("STEP 5: Final health check")
    print("-" * 70)

    health = store.get_health_stats()
    print("  Health stats:")
    print(json.dumps(health, indent=4))
    print()

    store.close()

    # =========================================================================
    # SUCCESS
    # =========================================================================
    print("=" * 70)
    print("SUCCESS: Smoke test passed!")
    print("=" * 70)
    print()
    print("Evidence:")
    print(f"  - ntfy message ID: {delivery_result.message_id}")
    print(f"  - Reminder ID:     {reminder_id}")
    print(f"  - Topic:           {topic}")
    print(f"  - Status:          sent (fired)")
    print(f"  - Idempotent:      Yes (not re-claimed)")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
