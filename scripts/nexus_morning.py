#!/usr/bin/env python3
"""
Generate morning briefing via systemd timer
Part of Milton Phase 2 automation
"""
import sys
import os
from pathlib import Path
from datetime import datetime
import logging

# Setup paths
sys.path.insert(0, '/home/cole-hanan/milton')
log_dir = Path('/home/cole-hanan/milton/logs/nexus')
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'morning_{timestamp}.log'),
        logging.StreamHandler()  # Also to systemd journal
    ]
)

logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("="*60)
        logger.info("Starting NEXUS morning briefing generation")
        logger.info(f"Timestamp: {timestamp}")
        logger.info("="*60)

        from agents.nexus import NEXUS

        logger.info("Initializing NEXUS agent...")
        nexus = NEXUS()

        logger.info("Generating morning briefing...")
        result = nexus.morning_briefing()

        # Extract path from result
        artifacts = result.get('brief', {}).get('artifacts', [])
        if artifacts:
            output_path = artifacts[0].get('path', 'unknown')
            logger.info(f"✓ Briefing saved to: {output_path}")
        else:
            logger.warning("No artifacts in result - briefing may not have been saved")

        logger.info("="*60)
        logger.info("Morning briefing generation completed successfully")
        logger.info("="*60)

        return 0

    except Exception as e:
        logger.error("="*60)
        logger.error(f"Morning briefing FAILED: {e}", exc_info=True)
        logger.error("="*60)
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
