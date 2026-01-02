#!/usr/bin/env python3
"""
Daily research discovery via systemd timer
Part of Milton Phase 2 automation
"""
import sys
from pathlib import Path
from datetime import datetime
import logging

from dotenv import load_dotenv
from milton_orchestrator.state_paths import resolve_state_dir

# Setup paths
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

STATE_DIR = resolve_state_dir()
log_dir = STATE_DIR / "logs" / "frontier"
log_dir.mkdir(parents=True, exist_ok=True)

# Configure logging
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'morning_{timestamp}.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("="*60)
        logger.info("Starting FRONTIER daily research discovery")
        logger.info(f"Timestamp: {timestamp}")
        logger.info("="*60)

        from agents.frontier import FRONTIER

        logger.info("Initializing FRONTIER agent...")
        frontier = FRONTIER()

        logger.info("Running daily discovery...")
        papers = frontier.daily_discovery()

        paper_count = len(papers.get('papers', []))
        logger.info(f"✓ Discovered {paper_count} papers")

        if paper_count > 0:
            for i, paper in enumerate(papers.get('papers', [])[:3], 1):
                logger.info(f"  {i}. {paper.get('title', 'Unknown')[:80]}")

        logger.info("="*60)
        logger.info("Daily research discovery completed successfully")
        logger.info("="*60)

        return 0

    except Exception as e:
        logger.error("="*60)
        logger.error(f"Research discovery FAILED: {e}", exc_info=True)
        logger.error("="*60)
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
