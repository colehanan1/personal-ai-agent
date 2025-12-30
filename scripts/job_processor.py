#!/usr/bin/env python3
"""
Process overnight job queue via systemd timer
Part of Milton Phase 2 automation
"""
import sys
import os
from pathlib import Path
from datetime import datetime
import logging
import json

# Setup paths
sys.path.insert(0, '/home/cole-hanan/milton')
log_dir = Path('/home/cole-hanan/milton/logs/cortex')
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

        # Check for jobs in tonight/
        job_dir = Path('/home/cole-hanan/milton/job_queue/tonight')
        jobs = list(job_dir.glob('*.json'))

        if not jobs:
            logger.info("No jobs in queue")
            logger.info("="*60)
            return 0

        logger.info(f"Found {len(jobs)} job(s) in queue")

        cortex = CORTEX()

        for job_file in jobs:
            logger.info("-"*60)
            logger.info(f"Processing job: {job_file.name}")

            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)

                task = job_data.get('task', 'Unknown task')
                logger.info(f"Task: {task[:100]}")

                logger.info("Executing with CORTEX...")
                result = cortex.execute(task)

                logger.info(f"Status: {result.get('status', 'unknown')}")

                # Archive completed job
                archive_dir = Path('/home/cole-hanan/milton/job_queue/archive')
                archive_dir.mkdir(parents=True, exist_ok=True)
                archive_path = archive_dir / job_file.name

                job_file.rename(archive_path)
                logger.info(f"✓ Job archived to: {archive_path}")

            except Exception as e:
                logger.error(f"Job processing error: {e}", exc_info=True)
                logger.error(f"Skipping job: {job_file.name}")
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
