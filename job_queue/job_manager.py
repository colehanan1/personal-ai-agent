"""
Job Queue Manager
Handles scheduling and execution of overnight jobs using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime, time as dt_time
from typing import Callable, Dict, Any, Optional, List
import os
import logging

logger = logging.getLogger(__name__)


class JobManager:
    """
    Manages job scheduling and execution.

    Uses APScheduler with SQLite storage for persistence.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize job manager.

        Args:
            db_path: Path to SQLite database (defaults to ~/milton/queue/jobs.db)
        """
        if db_path is None:
            db_path = os.path.expanduser("~/milton/queue/jobs.db")

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Configure job stores
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
        }

        # Configure executors
        executors = {
            "default": ThreadPoolExecutor(max_workers=4),
        }

        # Job defaults
        job_defaults = {
            "coalesce": False,
            "max_instances": 1,
            "misfire_grace_time": 300,  # 5 minutes
        }

        # Create scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )

        logger.info(f"JobManager initialized with database: {db_path}")

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job scheduler started")

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Job scheduler shut down")

    def add_job(
        self,
        job_id: str,
        task_func: Callable,
        run_time: datetime,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a one-time job.

        Args:
            job_id: Unique job identifier
            task_func: Function to execute
            run_time: When to run the job
            args: Positional arguments for task_func
            kwargs: Keyword arguments for task_func

        Returns:
            Job ID

        Example:
            >>> from datetime import datetime, timedelta
            >>> manager = JobManager()
            >>> manager.start()
            >>>
            >>> def my_task(message):
            ...     print(f"Task executed: {message}")
            >>>
            >>> run_time = datetime.now() + timedelta(hours=1)
            >>> manager.add_job("test_job", my_task, run_time, args=("Hello!",))
        """
        job = self.scheduler.add_job(
            task_func,
            "date",
            run_date=run_time,
            args=args or (),
            kwargs=kwargs or {},
            id=job_id,
            replace_existing=True,
        )

        logger.info(f"Added job '{job_id}' scheduled for {run_time}")

        return job.id

    def add_overnight_job(
        self,
        job_id: str,
        task_func: Callable,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add job to run during overnight window (22:00-06:00).

        Defaults to 22:30 (10:30 PM) if called before that time today,
        otherwise schedules for 22:30 tomorrow.

        Args:
            job_id: Unique job identifier
            task_func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Job ID
        """
        now = datetime.now()

        # Default overnight time: 22:30 (10:30 PM)
        target_time = dt_time(22, 30)

        # Create datetime for today at target time
        run_time = datetime.combine(now.date(), target_time)

        # If already past that time, schedule for tomorrow
        if now >= run_time:
            from datetime import timedelta
            run_time += timedelta(days=1)

        return self.add_job(job_id, task_func, run_time, args, kwargs)

    def add_recurring_job(
        self,
        job_id: str,
        task_func: Callable,
        trigger_type: str = "cron",
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        **trigger_args,
    ) -> str:
        """
        Add recurring job with custom trigger.

        Args:
            job_id: Unique job identifier
            task_func: Function to execute
            trigger_type: Trigger type ("cron", "interval")
            args: Positional arguments
            kwargs: Keyword arguments
            **trigger_args: Trigger-specific arguments

        Returns:
            Job ID

        Example:
            >>> # Daily at 7:30 AM
            >>> manager.add_recurring_job(
            ...     "morning_brief",
            ...     generate_briefing,
            ...     trigger_type="cron",
            ...     hour=7,
            ...     minute=30
            ... )
        """
        job = self.scheduler.add_job(
            task_func,
            trigger_type,
            args=args or (),
            kwargs=kwargs or {},
            id=job_id,
            replace_existing=True,
            **trigger_args,
        )

        logger.info(f"Added recurring job '{job_id}' with {trigger_type} trigger")

        return job.id

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job.

        Args:
            job_id: Job identifier

        Returns:
            True if removed, False if not found
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job '{job_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job '{job_id}': {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all scheduled jobs.

        Returns:
            List of job information dictionaries
        """
        jobs = []

        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

        return jobs

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific job.

        Args:
            job_id: Job identifier

        Returns:
            Job information or None if not found
        """
        job = self.scheduler.get_job(job_id)

        if job:
            return {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
                "args": job.args,
                "kwargs": job.kwargs,
            }

        return None


# Convenience function for global job manager
_global_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """
    Get global job manager instance.

    Returns:
        JobManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = JobManager()
        _global_manager.start()

    return _global_manager


if __name__ == "__main__":
    # Simple test
    import time

    def test_job():
        print("Test job executed!")

    manager = JobManager()
    manager.start()

    print("Job manager started")
    print("Scheduling test job in 5 seconds...")

    from datetime import timedelta
    run_time = datetime.now() + timedelta(seconds=5)

    manager.add_job("test", test_job, run_time)

    print("Waiting for job execution...")
    time.sleep(6)

    manager.shutdown()
    print("Done")
