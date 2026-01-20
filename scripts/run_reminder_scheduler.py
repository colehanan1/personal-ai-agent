#!/usr/bin/env python3
"""
Example: Running Milton with multi-channel reminder scheduler.

This demonstrates how to integrate the notification router with the reminder
scheduler in a running Milton instance.
"""

import time
import logging
from pathlib import Path

from milton_orchestrator.reminders import ReminderStore, ReminderScheduler
from milton_orchestrator.notifications import create_default_router
from milton_orchestrator.state_paths import resolve_state_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("milton.scheduler_example")


def main():
    """Run reminder scheduler with multi-channel support."""
    
    # Initialize store
    state_dir = resolve_state_dir()
    store = ReminderStore(state_dir / "reminders.db")
    logger.info(f"Reminder store initialized at {state_dir / 'reminders.db'}")
    
    # Create notification router with default providers
    # This will read NTFY_TOPIC, MILTON_PUBLIC_BASE_URL, MILTON_ACTION_TOKEN from env
    router = create_default_router()
    logger.info("Notification router created with providers: " + 
                ", ".join(router.providers.keys()))
    
    # Create and start scheduler
    scheduler = ReminderScheduler(
        store=store,
        notification_router=router,
        interval_seconds=5,  # Poll every 5 seconds
    )
    
    logger.info("Starting reminder scheduler...")
    scheduler.start()  # Runs in background thread
    
    # Check health
    health = store.get_health_stats()
    logger.info(f"Scheduler health: {health}")
    
    # Keep running
    logger.info("Scheduler is running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
            # Periodic health check
            health = store.get_health_stats()
            if health["scheduled_count"] > 0:
                logger.info(f"Pending reminders: {health['scheduled_count']}, "
                          f"next due in {health.get('next_due_in_sec', 'N/A')}s")
    except KeyboardInterrupt:
        logger.info("Stopping scheduler...")
        scheduler.stop()
        store.close()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
