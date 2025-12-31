"""Main orchestrator loop"""

import datetime
import hashlib
import logging
import time
from collections import deque
from pathlib import Path
from typing import Optional, Set

from .config import Config
from .ntfy_client import NtfyClient, subscribe_with_reconnect
from .perplexity_client import PerplexityClient, fallback_prompt_optimizer
from .prompt_builder import ClaudePromptBuilder, extract_command_type
from .claude_runner import ClaudeRunner, is_usage_limit_error
from .codex_runner import CodexRunner

logger = logging.getLogger(__name__)


class RequestTracker:
    """Track processed requests to prevent duplicates"""

    def __init__(self, max_size: int = 1000):
        self.processed_ids: Set[str] = set()
        self.recent_queue: deque = deque(maxlen=max_size)

    def is_processed(self, message_id: str) -> bool:
        """Check if a message has been processed"""
        return message_id in self.processed_ids

    def mark_processed(self, message_id: str):
        """Mark a message as processed"""
        self.processed_ids.add(message_id)
        self.recent_queue.append(message_id)

        # Keep set size bounded
        if len(self.processed_ids) > self.recent_queue.maxlen:
            # Remove oldest entries
            to_remove = len(self.processed_ids) - self.recent_queue.maxlen
            for old_id in list(self.processed_ids)[:to_remove]:
                if old_id not in self.recent_queue:
                    self.processed_ids.discard(old_id)


class Orchestrator:
    """Main orchestration engine"""

    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.request_tracker = RequestTracker()

        # Initialize clients
        self.ntfy_client = NtfyClient(config.ntfy_base_url)
        self.perplexity_client = PerplexityClient(
            api_key=config.perplexity_api_key,
            model=config.perplexity_model,
            timeout=config.perplexity_timeout,
            max_retries=config.perplexity_max_retries,
        )
        self.prompt_builder = ClaudePromptBuilder(config.target_repo)
        self.claude_runner = ClaudeRunner(
            claude_bin=config.claude_bin,
            target_repo=config.target_repo,
        )
        self.codex_runner = CodexRunner(
            codex_bin=config.codex_bin,
            target_repo=config.target_repo,
            model=config.codex_model,
            extra_args=config.codex_extra_args,
            state_dir=config.state_dir,
        )

        logger.info(f"Orchestrator initialized (dry_run={dry_run})")
        logger.info(f"Target repo: {config.target_repo}")
        logger.info(f"Listening on: {config.ask_topic}")
        logger.info(f"Publishing to: {config.answer_topic}")

    def generate_request_id(self, message_id: str, message: str) -> str:
        """Generate a unique request ID"""
        if message_id:
            return f"req_{message_id}"

        # Fallback: hash of message + timestamp
        timestamp = int(time.time())
        content = f"{message}_{timestamp}"
        hash_suffix = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"req_{timestamp}_{hash_suffix}"

    def publish_status(self, message: str, title: Optional[str] = None):
        """Publish status update to answer topic"""
        logger.info(f"Publishing status: {title or message[:50]}")
        self.ntfy_client.publish(
            self.config.answer_topic,
            message,
            title=title,
        )

    def process_code_request(self, request_id: str, content: str):
        """Process a CODE request"""
        logger.info(f"Processing CODE request {request_id}")

        try:
            # Step 1: Acknowledge
            self.publish_status(
                f"Request received: {request_id}\n\n{content[:200]}...",
                title="Processing Code Request",
            )

            # Step 2: Research with Perplexity
            self.publish_status(
                f"[{request_id}] Researching and optimizing prompt...",
                title="Research Phase",
            )

            research_notes = self.perplexity_client.research_and_optimize(
                content,
                str(self.config.target_repo),
            )

            if not research_notes:
                logger.warning("Perplexity failed, using fallback optimizer")
                research_notes = fallback_prompt_optimizer(content, str(self.config.target_repo))

            self.publish_status(
                f"[{request_id}] Research complete. Building agent prompts...",
                title="Research Complete",
            )

            # Step 3: Build prompts
            agent_prompt = self.prompt_builder.build_agent_prompt(
                user_request=content,
                research_notes=research_notes,
            )
            claude_prompt = self.prompt_builder.build_job_prompt(
                user_request=content,
                research_notes=research_notes,
            )

            # Step 4: Execute Claude Code (primary)
            if not self.claude_runner.check_available():
                if self.config.enable_codex_fallback:
                    self._run_codex_fallback(
                        request_id=request_id,
                        agent_prompt=agent_prompt,
                        reason="Claude unavailable/limited",
                    )
                    return

                self.publish_status(
                    f"❌ [{request_id}] Claude Code binary not found: {self.config.claude_bin}",
                    title="Claude Unavailable",
                )
                return

            self.publish_status(
                f"[{request_id}] Executing Claude Code...\nThis may take several minutes.",
                title="Claude Executing",
            )

            result = self.claude_runner.run(
                prompt=claude_prompt,
                timeout=self.config.request_timeout,
                dry_run=self.dry_run,
            )

            # Step 5: Save full output
            output_file = self.claude_runner.save_output(
                result,
                self.config.state_dir / "outputs",
            )

            if result.success:
                status_emoji = "✅"
                summary = result.get_summary(self.config.max_output_size)
                final_message = (
                    f"{status_emoji} [{request_id}] Claude Code finished\n\n"
                    f"{summary}\n\n"
                    f"Full output: {output_file}"
                )
                self.publish_status(
                    final_message,
                    title=f"Success: {request_id}",
                )
                logger.info(f"Request {request_id} completed successfully")
                return

            # Claude failed
            fallback_reason = self._codex_fallback_reason(result)
            if fallback_reason:
                self._run_codex_fallback(
                    request_id=request_id,
                    agent_prompt=agent_prompt,
                    reason=fallback_reason,
                    claude_output_file=output_file,
                )
                return

            status_emoji = "❌"
            summary = result.get_summary(self.config.max_output_size)
            final_message = (
                f"{status_emoji} [{request_id}] Claude Code failed\n\n"
                f"{summary}\n\n"
                f"Full output: {output_file}"
            )
            self.publish_status(
                final_message,
                title=f"Failed: {request_id}",
            )

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
            self.publish_status(
                f"❌ [{request_id}] Error: {e}",
                title="Processing Error",
            )

    def _codex_fallback_reason(self, claude_result) -> Optional[str]:
        if not self.config.enable_codex_fallback:
            return None
        if self.config.codex_fallback_on_any_failure:
            return "Claude failed"
        if not self.config.claude_fallback_on_limit:
            return None
        text = f"{claude_result.stdout}\n{claude_result.stderr}"
        if is_usage_limit_error(text):
            return "Claude unavailable/limited"
        return None

    def _run_codex_fallback(
        self,
        request_id: str,
        agent_prompt: str,
        reason: str,
        claude_output_file: Optional[Path] = None,
    ):
        self.publish_status(
            f"[{request_id}] {reason} → falling back to Codex",
            title="Codex Fallback",
        )

        if not self.codex_runner.check_available():
            self.publish_status(
                f"❌ [{request_id}] Codex CLI binary not found: {self.config.codex_bin}",
                title="Codex Unavailable",
            )
            return

        result = self.codex_runner.run(
            prompt=agent_prompt,
            timeout=self.config.codex_timeout,
            dry_run=self.dry_run,
        )

        plan_output = self.codex_runner.last_plan_output_file
        execute_output = self.codex_runner.last_execute_output_file

        status_emoji = "✅" if result.success else "❌"
        summary = result.get_summary(self.config.max_output_size)

        lines = [
            f"{status_emoji} [{request_id}] Codex finished",
            "",
            summary,
        ]

        if claude_output_file:
            lines.extend(["", f"Claude output: {claude_output_file}"])
        if plan_output:
            lines.extend(["", f"Plan output: {plan_output}"])
        if execute_output:
            lines.extend(["", f"Execute output: {execute_output}"])
        elif plan_output and not execute_output:
            lines.extend(["", "Execute output: (not run)"])

        self.publish_status(
            "\n".join(lines),
            title=f"{'Success' if result.success else 'Failed'}: {request_id}",
        )

    def process_research_request(self, request_id: str, content: str):
        """Process a RESEARCH request (no Claude execution)"""
        logger.info(f"Processing RESEARCH request {request_id}")

        try:
            # Acknowledge
            self.publish_status(
                f"Research request received: {request_id}\n\n{content[:200]}...",
                title="Research Request",
            )

            # Research with Perplexity
            self.publish_status(
                f"[{request_id}] Researching...",
                title="Researching",
            )

            research_notes = self.perplexity_client.research_and_optimize(
                content,
                str(self.config.target_repo),
            )

            if not research_notes:
                logger.warning("Perplexity failed, using fallback")
                research_notes = fallback_prompt_optimizer(content, str(self.config.target_repo))

            # Publish research results
            if len(research_notes) > self.config.max_output_size:
                # Save to file
                output_dir = self.config.state_dir / "outputs"
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = output_dir / f"research_{timestamp}.txt"
                output_file.write_text(research_notes)

                message = (
                    f"✅ [{request_id}] Research complete\n\n"
                    f"{research_notes[:self.config.max_output_size]}\n\n"
                    f"... (truncated)\n\n"
                    f"Full results: {output_file}"
                )
            else:
                message = f"✅ [{request_id}] Research complete\n\n{research_notes}"

            self.publish_status(message, title="Research Complete")
            logger.info(f"Research request {request_id} completed")

        except Exception as e:
            logger.error(f"Error processing research request {request_id}: {e}", exc_info=True)
            self.publish_status(
                f"❌ [{request_id}] Error: {e}",
                title="Research Error",
            )

    def run(self):
        """Main orchestrator loop"""
        logger.info("Starting orchestrator main loop")

        if self.dry_run:
            logger.warning("Running in DRY RUN mode - no actual Claude execution")

        try:
            for msg in subscribe_with_reconnect(
                self.ntfy_client,
                self.config.ask_topic,
                max_backoff=self.config.ntfy_reconnect_backoff_max,
            ):
                # Only process message events
                if not msg.is_message_event():
                    continue

                # Skip if already processed
                if self.request_tracker.is_processed(msg.id):
                    logger.info(f"Skipping already processed message: {msg.id}")
                    continue

                # Mark as processed immediately
                self.request_tracker.mark_processed(msg.id)

                # Extract command type and content
                cmd_type, content = extract_command_type(msg.message)

                # Generate request ID
                request_id = self.generate_request_id(msg.id, msg.message)

                logger.info(f"New {cmd_type} request: {request_id}")
                logger.info(f"Content preview: {content[:100]}...")

                # Route to appropriate handler
                if cmd_type == "RESEARCH":
                    self.process_research_request(request_id, content)
                else:  # CODE
                    self.process_code_request(request_id, content)

        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
        except Exception as e:
            logger.error(f"Fatal error in orchestrator: {e}", exc_info=True)
            raise
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up orchestrator resources")
        self.ntfy_client.close()
        self.perplexity_client.close()


def setup_logging(log_dir: Path, verbose: bool = False):
    """Set up logging configuration"""
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file with date
    log_file = log_dir / f"{datetime.date.today()}.log"

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO

    # Format for file and console
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)

    # Console handler (stdout for journald)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info(f"Logging initialized: {log_file}")
