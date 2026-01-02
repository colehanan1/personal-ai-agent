#!/usr/bin/env python3
"""
Process overnight job queue via systemd timer
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
    try:
        logger.info("="*60)
        logger.info("Starting CORTEX overnight job queue processing")
        logger.info(f"Timestamp: {timestamp}")
        logger.info("="*60)

        from agents.cortex import CORTEX
        import milton_queue as queue_api

        # Check for ready jobs in tonight/
        jobs = queue_api.dequeue_ready_jobs(now=datetime.now(timezone.utc), base_dir=STATE_DIR)

        if not jobs:
            logger.info("No jobs in queue")
            logger.info("="*60)
            return 0

        logger.info(f"Found {len(jobs)} job(s) ready to process")

        cortex = CORTEX()

        for job in jobs:
            logger.info("-"*60)
            logger.info(f"Processing job: {job.get('job_id', 'unknown')}")

            try:
                payload = job.get('payload', {}) if isinstance(job.get('payload'), dict) else {}
                task = job.get('task') or payload.get('task') or 'Unknown task'
                logger.info(f"Task: {task[:100]}")

                logger.info("Executing with CORTEX...")
                result = cortex.process_overnight_job({
                    'id': job.get('job_id'),
                    'task': task,
                })

                logger.info("Status: completed")
                queue_api.mark_done(
                    job.get('job_id'),
                    artifact_paths=[],
                    result=result,
                    base_dir=STATE_DIR,
                )
                logger.info("✓ Job archived")

            except Exception as e:
                logger.error(f"Job processing error: {e}", exc_info=True)
                try:
                    job_id = job.get('job_id')
                    if job_id:
                        queue_api.mark_failed(
                            job_id,
                            error=e,
                            base_dir=STATE_DIR,
                            now=datetime.now(timezone.utc),
                        )
                except Exception:
                    pass
                logger.error(f"Skipping job: {job.get('job_id', 'unknown')}")
                continue

        logger.info("="*60)
        logger.info("Job queue processing completed")
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
