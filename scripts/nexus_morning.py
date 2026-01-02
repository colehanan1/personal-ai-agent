#!/usr/bin/env python3
"""
Generate morning briefing via systemd timer
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
log_dir = STATE_DIR / "logs" / "nexus"
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
        briefing = nexus.generate_morning_briefing()

        output_dir = STATE_DIR / "inbox" / "morning"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"nexus_{datetime.now().strftime('%Y-%m-%d')}.txt"
        output_path.write_text(briefing, encoding="utf-8")
        logger.info(f"✓ Briefing saved to: {output_path}")

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
