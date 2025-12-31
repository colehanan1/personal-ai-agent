"""CLI entrypoint for Milton Orchestrator"""

import argparse
import sys
import logging

from .config import Config
from .orchestrator import Orchestrator, setup_logging

logger = logging.getLogger(__name__)


def main():
    """Main CLI entrypoint"""
    parser = argparse.ArgumentParser(
        description="Milton Orchestrator - Voice-to-Code System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run normally
  milton-orchestrator

  # Run in dry-run mode (no actual Claude execution)
  milton-orchestrator --dry-run

  # Run with verbose logging
  milton-orchestrator -v

Environment Variables:
  PERPLEXITY_API_KEY     Perplexity API key (required)
  TARGET_REPO            Path to target repository (required)
  NTFY_BASE_URL          ntfy server URL (default: https://ntfy.sh)
  ASK_TOPIC              Topic for incoming requests (default: milton-briefing-code-ask)
  ANSWER_TOPIC           Topic for responses (default: milton-briefing-code)
  PERPLEXITY_MODEL       Perplexity model (default: sonar-pro)
  CLAUDE_BIN             Claude Code binary path (default: claude)
  CODEX_BIN              Codex CLI binary path (default: codex)
  CODEX_MODEL            Codex model override (default: gpt-5.2-codex)
  CODEX_TIMEOUT          Codex timeout seconds (default: REQUEST_TIMEOUT)
  ENABLE_CODEX_FALLBACK  Enable Claude-to-Codex fallback (default: true)
  CLAUDE_FALLBACK_ON_LIMIT  Fallback only on usage/rate limits (default: true)
  CODEX_EXTRA_ARGS       Extra Codex CLI flags (quoted string)

Message Formats:
  CODE: <request>        Run full pipeline with Claude Code execution
  RESEARCH: <request>    Run Perplexity research only, no code changes
  <request>              Default to CODE mode
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't execute Claude, just simulate",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = Config.from_env()
        config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nPlease check your environment variables.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging
    setup_logging(config.log_dir, verbose=args.verbose)

    logger.info("=" * 60)
    logger.info("Milton Orchestrator Starting")
    logger.info("=" * 60)
    logger.info(f"Target Repository: {config.target_repo}")
    logger.info(f"Ask Topic: {config.ask_topic}")
    logger.info(f"Answer Topic: {config.answer_topic}")
    logger.info(f"Claude Binary: {config.claude_bin}")
    logger.info(f"Codex Binary: {config.codex_bin}")
    logger.info(f"Codex Model: {config.codex_model}")
    logger.info(
        f"Codex Fallback: enabled={config.enable_codex_fallback}, "
        f"any_failure={config.codex_fallback_on_any_failure}, "
        f"on_limit={config.claude_fallback_on_limit}"
    )
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info("=" * 60)

    # Create and run orchestrator
    try:
        orchestrator = Orchestrator(config, dry_run=args.dry_run)
        orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
