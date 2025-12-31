"""Main orchestrator loop"""

import datetime
import hashlib
import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from typing import Optional, Set

from .config import Config
from .ntfy_client import NtfyClient, subscribe_topics_with_reconnect
from .perplexity_client import PerplexityClient, fallback_prompt_optimizer
from .prompt_builder import ClaudePromptBuilder
from .claude_runner import ClaudeRunner, is_usage_limit_error
from .codex_runner import CodexRunner
from .reminders import (
    ReminderScheduler,
    ReminderStore,
    format_timestamp_local,
    parse_reminder_command,
)

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
        self.reminder_store = None
        self.reminder_scheduler = None
        if config.enable_reminders:
            self.reminder_store = ReminderStore(config.state_dir / "reminders.sqlite3")
            self.reminder_scheduler = ReminderScheduler(
                store=self.reminder_store,
                publish_fn=lambda msg: self.ntfy_client.publish(
                    self.config.answer_topic, msg, title="Reminder"
                ),
                interval_seconds=5,
            )
            self.reminder_scheduler.start()

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
        """Process a legacy CODE request (unused in new routing)."""
        logger.warning("Legacy CODE request handler invoked; defaulting to Claude pipeline")
        self.process_claude_code_request(request_id, content)

    def process_claude_code_request(self, request_id: str, content: str):
        """Process a CLAUDE_CODE request"""
        if not self.config.enable_claude_pipeline:
            self.publish_status(
                f"❌ [{request_id}] Claude pipeline disabled",
                title="Pipeline Disabled",
            )
            return

        logger.info(f"Processing CLAUDE_CODE request {request_id}")

        try:
            research_notes = None
            if self.config.perplexity_in_claude_mode:
                self.publish_status(
                    f"[{request_id}] Researching and optimizing prompt...",
                    title="Research Phase",
                )
                research_notes = self._run_perplexity(content)

            if research_notes is not None:
                self.publish_status(
                    f"[{request_id}] Research complete. Building agent prompts...",
                    title="Research Complete",
                )
            else:
                self.publish_status(
                    f"[{request_id}] Building agent prompts...",
                    title="Prompt Build",
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

    def process_codex_code_request(self, request_id: str, content: str):
        """Process a CODEX_CODE request"""
        if not self.config.enable_codex_pipeline:
            self.publish_status(
                f"❌ [{request_id}] Codex pipeline disabled",
                title="Pipeline Disabled",
            )
            return

        logger.info(f"Processing CODEX_CODE request {request_id}")

        try:
            research_notes = None
            if self.config.perplexity_in_codex_mode:
                self.publish_status(
                    f"[{request_id}] Researching and optimizing prompt...",
                    title="Research Phase",
                )
                research_notes = self._run_perplexity(content)

            if research_notes is not None:
                self.publish_status(
                    f"[{request_id}] Research complete. Building agent prompts...",
                    title="Research Complete",
                )
            else:
                self.publish_status(
                    f"[{request_id}] Building agent prompts...",
                    title="Prompt Build",
                )

            agent_prompt = self.prompt_builder.build_agent_prompt(
                user_request=content,
                research_notes=research_notes,
            )

            if not self.codex_runner.check_available():
                self.publish_status(
                    f"❌ [{request_id}] Codex CLI binary not found: {self.config.codex_bin}",
                    title="Codex Unavailable",
                )
                return

            self.publish_status(
                f"[{request_id}] Executing Codex...\nThis may take several minutes.",
                title="Codex Executing",
            )

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

        except Exception as e:
            logger.error(f"Error processing CODEX request {request_id}: {e}", exc_info=True)
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

    def process_chat_request(self, request_id: str, content: str):
        """Process a CHAT request (no Perplexity, no code execution)."""
        logger.info(f"Processing CHAT request {request_id}")
        message = f"[{request_id}] CHAT mode received.\n\n{content}"
        self.publish_status(message, title="Chat Request")

    def process_reminder_request(self, request_id: str, content: str, kind: str):
        """Process REMIND/ALARM requests."""
        if not self.config.enable_reminders or not self.reminder_store:
            self.publish_status(
                f"❌ [{request_id}] Reminders are disabled",
                title="Reminders Disabled",
            )
            return

        try:
            command = parse_reminder_command(content, kind=kind)
        except ValueError as exc:
            self.publish_status(
                f"❌ [{request_id}] Invalid reminder command: {exc}",
                title="Reminder Error",
            )
            return

        if command.action == "list":
            reminders = self.reminder_store.list_reminders()
            if not reminders:
                message = f"[{request_id}] No pending reminders."
            else:
                lines = [f"[{request_id}] Pending reminders:"]
                for reminder in reminders:
                    due = format_timestamp_local(reminder.due_at)
                    lines.append(f"- {reminder.id} | {reminder.kind} | {due} | {reminder.message}")
                message = "\n".join(lines)
            self.publish_status(message, title="Reminder List")
            return

        if command.action == "cancel":
            success = self.reminder_store.cancel_reminder(command.reminder_id)
            status = "Canceled" if success else "Not Found"
            self.publish_status(
                f"[{request_id}] {status}: {command.reminder_id}",
                title="Reminder Cancel",
            )
            return

        reminder_id = self.reminder_store.add_reminder(
            kind=command.kind,
            due_at=command.due_at,
            message=command.message or "Reminder",
        )
        due_str = format_timestamp_local(command.due_at)
        self.publish_status(
            f"[{request_id}] Scheduled {command.kind} {reminder_id} at {due_str}: {command.message}",
            title="Reminder Scheduled",
        )

    def _run_perplexity(self, content: str) -> Optional[str]:
        research_notes = self.perplexity_client.research_and_optimize(
            content,
            str(self.config.target_repo),
        )
        if not research_notes:
            logger.warning("Perplexity failed, using fallback optimizer")
            research_notes = fallback_prompt_optimizer(content, str(self.config.target_repo))
        return research_notes

    def _format_research_response(self, request_id: str, research_notes: str) -> str:
        sources = []
        for line in research_notes.splitlines():
            if "http://" in line or "https://" in line:
                sources.append(line.strip())
        lines = [f"✅ [{request_id}] Research complete", "", "SUMMARY:", research_notes]
        if sources:
            lines.extend(["", "SOURCES:", *sources])
        return "\n".join(lines)

    def route_message(self, topic: str, message: str) -> tuple[str, str, Optional[str]]:
        text = message.lstrip()

        if self.config.claude_topic and topic == self.config.claude_topic:
            payload = _strip_prefix(text, "CLAUDE")
            return "CLAUDE_CODE", payload, None

        if self.config.codex_topic and topic == self.config.codex_topic:
            payload = _strip_prefix(text, "CODEX")
            return "CODEX_CODE", payload, None

        if self.config.enable_prefix_routing:
            prefix = _match_prefix(text)
            if prefix:
                kind, payload = prefix
                if kind == "CLAUDE":
                    return "CLAUDE_CODE", payload, None
                if kind == "CODEX":
                    return "CODEX_CODE", payload, None
                if kind == "RESEARCH":
                    return "RESEARCH", payload, None
                if kind == "REMIND":
                    return "REMINDER", payload, "REMIND"
                if kind == "ALARM":
                    return "REMINDER", payload, "ALARM"

        return "CHAT", text.strip(), None

    def process_incoming_message(self, message_id: str, topic: str, message: str):
        normalized_message = _normalize_message_text(message)
        request_id = self.generate_request_id(message_id, normalized_message)
        mode, payload, reminder_kind = self.route_message(topic, normalized_message)

        self.publish_status(
            f"[{request_id}] Mode: {mode}",
            title="Request Acknowledged",
        )

        if mode == "CLAUDE_CODE":
            self.process_claude_code_request(request_id, payload)
        elif mode == "CODEX_CODE":
            self.process_codex_code_request(request_id, payload)
        elif mode == "RESEARCH":
            if not self.config.enable_research_mode:
                self.publish_status(
                    f"❌ [{request_id}] Research mode disabled",
                    title="Research Disabled",
                )
                return
            if not self.config.perplexity_in_research_mode:
                self.publish_status(
                    f"❌ [{request_id}] Perplexity disabled for research mode",
                    title="Research Disabled",
                )
                return
            research_notes = self._run_perplexity(payload)
            if not research_notes:
                self.publish_status(
                    f"❌ [{request_id}] Research failed",
                    title="Research Error",
                )
                return
            message = self._format_research_response(request_id, research_notes)
            if len(message) > self.config.max_output_size:
                output_dir = self.config.state_dir / "outputs"
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = output_dir / f"research_{timestamp}.txt"
                output_file.write_text(message)
                message = (
                    f"✅ [{request_id}] Research complete\n\n"
                    f"{message[:self.config.max_output_size]}\n\n"
                    f"... (truncated)\n\n"
                    f"Full results: {output_file}"
                )
            self.publish_status(message, title="Research Complete")
        elif mode == "REMINDER":
            if not reminder_kind:
                reminder_kind = "REMIND"
            self.process_reminder_request(request_id, payload, reminder_kind)
        else:
            self.process_chat_request(request_id, payload)

    def process_research_request(self, request_id: str, content: str):
        """Process a RESEARCH request (no Claude execution)"""
        logger.info(f"Processing RESEARCH request {request_id}")

        try:
            # Acknowledge
            self.publish_status(
                f"Research request received: {request_id}\n\n{content[:200]}...",
                title="Research Request",
            )

            if not self.config.enable_research_mode:
                self.publish_status(
                    f"❌ [{request_id}] Research mode disabled",
                    title="Research Disabled",
                )
                return

            if not self.config.perplexity_in_research_mode:
                self.publish_status(
                    f"❌ [{request_id}] Perplexity disabled for research mode",
                    title="Research Disabled",
                )
                return

            # Research with Perplexity
            self.publish_status(
                f"[{request_id}] Researching...",
                title="Researching",
            )

            research_notes = self._run_perplexity(content)
            if not research_notes:
                self.publish_status(
                    f"❌ [{request_id}] Research failed",
                    title="Research Error",
                )
                return

            # Publish research results
            formatted = self._format_research_response(request_id, research_notes)
            if len(formatted) > self.config.max_output_size:
                # Save to file
                output_dir = self.config.state_dir / "outputs"
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = output_dir / f"research_{timestamp}.txt"
                output_file.write_text(formatted)

                message = (
                    f"{formatted[:self.config.max_output_size]}\n\n"
                    f"... (truncated)\n\n"
                    f"Full results: {output_file}"
                )
            else:
                message = formatted

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
            topics = [
                self.config.ask_topic,
                self.config.claude_topic,
                self.config.codex_topic,
            ]

            for msg in subscribe_topics_with_reconnect(
                self.ntfy_client,
                topics,
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

                logger.info(f"New message received: {msg.id}")
                logger.info(f"Content preview: {msg.message[:100]}...")

                self.process_incoming_message(msg.id, msg.topic, msg.message)

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
        if self.reminder_scheduler:
            self.reminder_scheduler.stop()
        if self.reminder_store:
            self.reminder_store.close()
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


def _strip_prefix(text: str, prefix: str) -> str:
    payload = _strip_prefix_with_optional_brackets(text, prefix)
    return payload.strip()


def _match_prefix(text: str) -> Optional[tuple[str, str]]:
    for kind in ("CLAUDE", "CODEX", "RESEARCH", "REMIND", "ALARM"):
        payload = _strip_prefix_with_optional_brackets(text, kind)
        if payload != text:
            return kind, payload.strip()
    return None


def _strip_prefix_with_optional_brackets(text: str, prefix: str) -> str:
    pattern = re.compile(
        rf"^\s*\[?\s*{re.escape(prefix)}\s*:\s*(.*)$",
        re.IGNORECASE,
    )
    match = pattern.match(text)
    if not match:
        return text
    payload = match.group(1).strip()
    if text.strip().startswith("[") and payload.endswith("]"):
        payload = payload[:-1].strip()
    return payload


def _normalize_message_text(message: str) -> str:
    text = message.strip()
    if not text:
        return ""

    text = text.lstrip("\ufeff")
    if text.startswith(("\"", "'")):
        try:
            unwrapped = json.loads(text)
        except json.JSONDecodeError:
            unwrapped = None
        if isinstance(unwrapped, str):
            text = unwrapped.strip()

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None

        if isinstance(data, dict):
            normalized_keys = {
                re.sub(r"[^a-z0-9]+", "", key.lower()): key for key in data.keys()
            }
            for candidate in ("providedinput", "input", "message", "text", "prompt"):
                if candidate in normalized_keys:
                    value = data.get(normalized_keys[candidate])
                    if value is not None:
                        text = str(value).strip()
                        break
        else:
            extracted = _extract_provided_input_from_raw(text)
            if extracted:
                text = extracted
    else:
        extracted = _extract_provided_input_from_raw(text)
        if extracted:
            text = extracted

    text = re.sub(r"^provided input\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[[^\]]+\]\s*[:\-]\s*", "", text)
    return text.strip()


def _extract_provided_input_from_raw(text: str) -> Optional[str]:
    if "provided" not in text.lower():
        return None

    match = re.search(
        r"provided\s*input[^:]*:\s*(.+)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    value = match.group(1).strip()
    if not value:
        return None

    quote_chars = ('"', "'", "“", "”", "‘", "’")
    if value[0] in quote_chars:
        quote = value[0]
        remainder = value[1:]
        if quote in ('"', "'"):
            closing = re.search(rf"(?<!\\\\){re.escape(quote)}", remainder)
        else:
            closing = re.search(re.escape(quote), remainder)
        if closing:
            value = remainder[: closing.start()]
        else:
            value = remainder
    else:
        for sep in ('","', '"}', '",', "\n", "\r"):
            idx = value.find(sep)
            if idx != -1:
                value = value[:idx]
                break
        if "}" in value:
            value = value.split("}")[0]

    return value.strip(" \t\"'“”")
