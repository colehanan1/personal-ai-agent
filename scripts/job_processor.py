#!/usr/bin/env python3
"""
CORTEX Overnight Job Queue Processor

Processes jobs from the file-based queue with exactly-once semantics.

Job Lifecycle:
  queued -> in_progress -> completed (archived) | failed (archived)

Guarantees:
  - Exactly-once processing via file locking (fcntl)
  - Idempotent: reruns skip already completed jobs
  - Atomic state transitions
  - Failed jobs are archived with error details

Part of Milton Phase 2 automation
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
import logging

from dotenv import load_dotenv

# Setup paths
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
from milton_orchestrator.state_paths import resolve_state_dir

load_dotenv()

STATE_DIR = resolve_state_dir()
log_dir = STATE_DIR / 'logs' / 'cortex'
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'processor_{timestamp}.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """
    Main job processor loop.

    Fetches ready jobs, executes them with CORTEX, and archives results.
    Ensures exactly-once processing via file locks.
    """
    try:
        logger.info("="*60)
        logger.info("Starting CORTEX overnight job queue processing")
        logger.info(f"Timestamp: {timestamp}")
        logger.info(f"State directory: {STATE_DIR}")
        logger.info("="*60)

        from agents.cortex import CORTEX
        from agents.contracts import TaskResult, TaskStatus
        import milton_queue as queue_api

        # Check for ready jobs in tonight/
        # This atomically claims jobs and marks them as in_progress
        jobs = queue_api.dequeue_ready_jobs(now=datetime.now(timezone.utc), base_dir=STATE_DIR)

        if not jobs:
            logger.info("No jobs in queue")
            logger.info("="*60)
            return 0

        logger.info(f"Found {len(jobs)} job(s) ready to process")

        # Initialize CORTEX once for all jobs
        cortex = CORTEX()

        processed_count = 0
        failed_count = 0

        for job in jobs:
            job_id = job.get('job_id', 'unknown')
            logger.info("-"*60)
            logger.info(f"Processing job: {job_id}")

            try:
                # Extract task from payload
                payload = job.get('payload', {}) if isinstance(job.get('payload'), dict) else {}
                task = job.get('task') or payload.get('task') or 'Unknown task'
                logger.info(f"Task: {task[:100]}...")

                # Execute with CORTEX (returns TaskResult)
                logger.info("Executing with CORTEX...")
                result = cortex.process_overnight_job({
                    'id': job_id,
                    'task': task,
                })

                # Verify result is a TaskResult
                if not isinstance(result, TaskResult):
                    logger.warning(f"Expected TaskResult, got {type(result)}")
                    # Convert to dict if needed for compatibility
                    result_dict = result if isinstance(result, dict) else {}
                else:
                    result_dict = result.to_dict()

                # Check status
                if isinstance(result, TaskResult):
                    if result.status == TaskStatus.FAILED:
                        logger.error(f"CORTEX execution failed: {result.error_message}")
                        queue_api.mark_failed(
                            job_id,
                            error=result.error_message,
                            base_dir=STATE_DIR,
                            now=datetime.now(timezone.utc),
                        )
                        failed_count += 1
                        logger.error(f"✗ Job marked as failed and archived")
                        continue

                # Extract artifact paths from TaskResult
                artifact_paths = []
                if isinstance(result, TaskResult):
                    artifact_paths = result.output_paths
                    logger.info(f"Output paths: {artifact_paths}")
                    logger.info(f"Evidence refs: {result.evidence_refs}")

                # Mark job as completed and archive
                logger.info(f"Status: {result.status.value if isinstance(result, TaskResult) else 'completed'}")
                queue_api.mark_done(
                    job_id,
                    artifact_paths=artifact_paths,
                    result=result_dict,
                    base_dir=STATE_DIR,
                )

                processed_count += 1
                logger.info("✓ Job completed and archived")

            except Exception as e:
                logger.error(f"Job processing error: {e}", exc_info=True)

                # Mark as failed and archive
                try:
                    queue_api.mark_failed(
                        job_id,
                        error=e,
                        base_dir=STATE_DIR,
                        now=datetime.now(timezone.utc),
                    )
                    failed_count += 1
                    logger.error(f"✗ Job marked as failed and archived")
                except Exception as archive_error:
                    logger.error(f"Failed to archive error: {archive_error}")

                # Continue processing remaining jobs
                continue

        logger.info("="*60)
        logger.info(f"Job queue processing completed")
        logger.info(f"  Processed: {processed_count}")
        logger.info(f"  Failed: {failed_count}")
        logger.info(f"  Total: {len(jobs)}")
        logger.info("="*60)

        return 0

    except Exception as e:
        logger.error("="*60)
        logger.error(f"Job processor FAILED: {e}", exc_info=True)
        logger.error("="*60)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
