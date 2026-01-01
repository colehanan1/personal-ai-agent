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
  NTFY_MAX_CHARS         Max chars for short status messages (default: 160)
  NTFY_MAX_INLINE_CHARS  Max chars before switching to file output (default: 3000)
  OUTPUT_DIR             Directory for saved outputs (default: ~/.local/state/milton_orchestrator/outputs)
  OUTPUT_BASE_URL        Base URL for Click-to-open output (optional)
  OUTPUT_SHARE_URL       SMB share URL for output files (e.g. smb://host/share)
  OUTPUT_SHARE_HOST      SMB share host (used with OUTPUT_SHARE_NAME)
  OUTPUT_SHARE_NAME      SMB share name (used with OUTPUT_SHARE_HOST)
  OUTPUT_FILENAME_TEMPLATE  Output filename template (default: milton_{request_id}.txt)
  ALWAYS_FILE_ATTACHMENTS  Always save to file + Click URL (default: false)
  ASK_TOPIC              Topic for incoming requests (default: milton-briefing-code-ask)
  ANSWER_TOPIC           Topic for responses (default: milton-briefing-code)
  CLAUDE_TOPIC           Topic for Claude code requests (default: empty)
  CODEX_TOPIC            Topic for Codex code requests (default: empty)
  ENABLE_PREFIX_ROUTING  Enable prefix-based routing (default: true)
  ENABLE_CLAUDE_PIPELINE Enable Claude coding pipeline (default: true)
  ENABLE_CODEX_PIPELINE  Enable Codex coding pipeline (default: true)
  ENABLE_RESEARCH_MODE   Enable research mode (default: true)
  ENABLE_REMINDERS       Enable reminders (default: true)
  PERPLEXITY_IN_CLAUDE_MODE  Use Perplexity in CLAUDE mode (default: true)
  PERPLEXITY_IN_CODEX_MODE   Use Perplexity in CODEX mode (default: true)
  PERPLEXITY_IN_RESEARCH_MODE Use Perplexity in RESEARCH mode (default: true)
  PERPLEXITY_MODEL       Perplexity model (default: sonar-pro)
  CLAUDE_BIN             Claude Code binary path (default: claude)
  CLAUDE_TIMEOUT         Claude timeout seconds (0 = no timeout, default: 0)
  CODEX_BIN              Codex CLI binary path (default: codex)
  CODEX_MODEL            Codex model override (default: gpt-5.2-codex)
  CODEX_TIMEOUT          Codex timeout seconds (0 = no timeout, default: 0)
  ENABLE_CODEX_FALLBACK  Enable Claude-to-Codex fallback (default: true)
  CLAUDE_FALLBACK_ON_LIMIT  Fallback only on usage/rate limits (default: true)
  CODEX_EXTRA_ARGS       Extra Codex CLI flags (quoted string)

Message Formats:
  CLAUDE: <request>      Run Claude pipeline (may fall back to Codex on limits)
  CODEX: <request>       Run Codex pipeline directly
  RESEARCH: <request>    Run Perplexity research only, no code changes
  REMIND: <spec>         Schedule a reminder (e.g. "in 10m | Stretch")
  ALARM: <spec>          Schedule an alarm (same syntax as REMIND)
  <request>              Default to chat mode (no coding pipeline)
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
    logger.info(f"Claude Topic: {config.claude_topic or '(none)'}")
    logger.info(f"Codex Topic: {config.codex_topic or '(none)'}")
    logger.info(f"Claude Binary: {config.claude_bin}")
    logger.info(f"Codex Binary: {config.codex_bin}")
    logger.info(f"Codex Model: {config.codex_model}")
    logger.info(f"Output Dir: {config.output_dir}")
    logger.info(f"Output Base URL: {config.output_base_url or '(not set)'}")
    share_hint = "(not set)"
    if config.output_share_url:
        share_hint = config.output_share_url
    elif config.output_share_host and config.output_share_name:
        share_hint = f"smb://{config.output_share_host}/{config.output_share_name}"
    logger.info(f"Output SMB Share: {share_hint}")
    logger.info(f"NTFY Max Inline Chars: {config.ntfy_max_inline_chars}")
    logger.info(
        f"Codex Fallback: enabled={config.enable_codex_fallback}, "
        f"any_failure={config.codex_fallback_on_any_failure}, "
        f"on_limit={config.claude_fallback_on_limit}"
    )
    logger.info(
        "Routing: prefix=%s claude=%s codex=%s research=%s reminders=%s",
        config.enable_prefix_routing,
        config.enable_claude_pipeline,
        config.enable_codex_pipeline,
        config.enable_research_mode,
        config.enable_reminders,
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
