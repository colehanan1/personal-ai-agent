"""Main orchestrator loop"""

import datetime
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Optional, Set

import requests

from .config import Config
from .ntfy_client import NtfyClient, subscribe_topics_with_reconnect
from .ntfy_summarizer import truncate_text
from .input_normalizer import normalize_incoming_input
from .output_publisher import publish_response
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
from .state_paths import resolve_reminders_db_path
from .self_upgrade_entry import process_self_upgrade_request

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
        
        # Initialize idempotency tracker for duplicate prevention
        from .idempotency import IdempotencyTracker
        idempotency_db = config.state_dir / "idempotency.sqlite3"
        self.idempotency = IdempotencyTracker(idempotency_db)

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
            output_dir=config.output_dir,
        )
        self.reminder_store = None
        self.reminder_scheduler = None
        if config.enable_reminders:
            self.reminder_store = ReminderStore(resolve_reminders_db_path())
            logger.info(f"Reminder store initialized at: {resolve_reminders_db_path()}")

            def reminder_publish_fn(message: str, title: str, reminder_id: int) -> bool:
                """Publish reminder via ntfy."""
                return self.ntfy_client.publish(
                    self.config.answer_topic,
                    truncate_text(message, max_chars=self.config.ntfy_max_chars),
                    title=title,
                    priority=4,
                )

            self.reminder_scheduler = ReminderScheduler(
                store=self.reminder_store,
                publish_fn=reminder_publish_fn,
                interval_seconds=5,
            )
            self.reminder_scheduler.start()

        # Initialize prompting pipeline if available
        self._prompting_pipeline = None
        try:
            from prompting import PromptingConfig, PromptingPipeline
            prompting_config = PromptingConfig.from_env()
            self._prompting_pipeline = PromptingPipeline(
                config=prompting_config,
                repo_root=config.target_repo,
            )
            logger.info("Prompting pipeline initialized for orchestrator")
        except ImportError:
            logger.debug("Prompting module not available")
        except Exception as e:
            logger.warning(f"Failed to initialize prompting pipeline: {e}")

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
        message = truncate_text(message, max_chars=self.config.ntfy_max_chars)
        logger.info(f"Publishing status: {title or message[:50]}")
        self.ntfy_client.publish(
            self.config.answer_topic,
            message,
            title=title,
        )

    def _memory_enabled(self) -> bool:
        raw = os.getenv("MILTON_MEMORY_ENABLED")
        if raw is None:
            return True
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _record_request_memory(
        self,
        request_id: str,
        content: str,
        mode_tag: Optional[str],
        topic: str,
        *,
        input_type: str = "text",
        structured_fields: Optional[dict[str, list[str]]] = None,
    ) -> list[str]:
        if not self._memory_enabled():
            return []
        if not content.strip():
            return []

        tags = ["source:ntfy", f"input:{input_type}"]
        if mode_tag:
            tags.append(mode_tag)
        if structured_fields:
            if structured_fields.get("goals"):
                tags.append("goal")
            if structured_fields.get("summaries"):
                tags.append("summary")

        try:
            MemoryItem, add_memory = _get_memory_modules()
        except Exception as exc:
            logger.warning("Failed to load memory modules: %s", exc)
            return []

        chunks = _chunk_text(content.strip(), max_chars=self.config.max_output_size)
        total_chunks = len(chunks)
        memory_ids: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            chunk_tags = list(tags)
            if total_chunks > 1:
                chunk_tags.append(f"chunk:{idx}/{total_chunks}")
            memory_item = MemoryItem(
                agent="orchestrator",
                type="request",
                content=chunk,
                tags=chunk_tags,
                importance=0.35,
                source="ntfy",
                request_id=request_id,
                evidence=[f"topic:{topic}"],
            )

            try:
                memory_id = add_memory(memory_item, repo_root=self.config.target_repo)
                if memory_id:
                    memory_ids.append(memory_id)
            except Exception as exc:
                logger.warning("Failed to record request memory: %s", exc)

        if memory_ids:
            logger.info(
                "Recorded request memory: request_id=%s mode=%s topic=%s ids=%s",
                request_id,
                mode_tag or "unknown",
                topic,
                memory_ids,
            )
        return memory_ids

    def _persist_attachments(self, request_id: str, attachments) -> list[Path]:
        if not attachments:
            return []

        base_dir = self.config.state_dir / "attachments" / request_id
        base_dir.mkdir(parents=True, exist_ok=True)
        stored_paths: list[Path] = []

        for idx, attachment in enumerate(attachments, start=1):
            name = getattr(attachment, "name", None) or f"attachment_{idx:02d}"
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(name)).strip("._")
            if not safe_name:
                safe_name = f"attachment_{idx:02d}"
            path = base_dir / f"{idx:02d}_{safe_name}.json"
            payload = {
                "name": getattr(attachment, "name", None),
                "content_type": getattr(attachment, "content_type", None),
                "size": getattr(attachment, "size", None),
                "url": getattr(attachment, "url", None),
                "parse_error": getattr(attachment, "parse_error", None),
                "raw": getattr(attachment, "raw", None),
                "text": getattr(attachment, "text", None),
            }
            try:
                path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                stored_paths.append(path)
            except OSError as exc:
                logger.warning("Failed to persist attachment %s: %s", name, exc)

        return stored_paths

    def process_code_request(self, request_id: str, content: str):
        """Process a legacy CODE request (unused in new routing)."""
        logger.warning("Legacy CODE request handler invoked; defaulting to Claude pipeline")
        self.process_claude_code_request(request_id, content)

    def process_claude_code_request(
        self,
        request_id: str,
        content: str,
        *,
        mode_tag: Optional[str] = None,
    ):
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

            # Run prompting pipeline for agent prompt generation (quality checks + CoVe)
            verified_badge = None
            if self._prompting_pipeline is not None:
                try:
                    pipeline_result = self._prompting_pipeline.run(
                        content,
                        request_id=request_id,
                        mode="generate_agent_prompt",
                    )
                    content = pipeline_result.response  # Use verified/revised prompt
                    verified_badge = pipeline_result.verified_badge
                    logger.debug(
                        f"Prompt verified for {request_id}: badge={verified_badge}"
                    )
                    # Store artifacts (best-effort)
                    if pipeline_result.artifacts:
                        logger.debug(f"Pipeline artifacts stored for {request_id}")
                except Exception as e:
                    logger.warning(f"Prompting pipeline failed for {request_id}: {e}")

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
                timeout=self.config.claude_timeout,
                dry_run=self.dry_run,
            )

            # Step 5: Save full output
            output_file = self.claude_runner.save_output(
                result,
                self.config.output_dir,
            )

            if result.success:
                self._publish_final_output(
                    request_id=request_id,
                    tool_name="Claude Code",
                    result=result,
                    output_file=output_file,
                    mode_tag=mode_tag,
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

            self._publish_final_output(
                request_id=request_id,
                tool_name="Claude Code",
                result=result,
                output_file=output_file,
                mode_tag=mode_tag,
            )

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
            self.publish_status(
                f"❌ [{request_id}] Error: {e}",
                title="Processing Error",
            )

    def process_codex_code_request(
        self,
        request_id: str,
        content: str,
        *,
        mode_tag: Optional[str] = None,
    ):
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

            note = None
            if plan_output and not execute_output:
                note = "Execute output: (not run)"

            self._publish_final_output(
                request_id=request_id,
                tool_name="Codex",
                result=result,
                output_file=execute_output or plan_output,
                note=note,
                mode_tag=mode_tag,
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

        note = None
        if plan_output and not execute_output:
            note = "Execute output: (not run)"

        self._publish_final_output(
            request_id=request_id,
            tool_name="Codex (fallback)",
            result=result,
            output_file=execute_output or plan_output,
            note=note,
            mode_tag="codex",
        )

    def process_chat_request(self, request_id: str, content: str):
        """Process a CHAT request (no Perplexity, no code execution)."""
        logger.info(f"Processing CHAT request {request_id}")
        
        # Idempotency check: prevent duplicate LLM calls for same request
        llm_dedupe_key = f"{request_id}_llm_gen"
        if self.request_tracker.is_processed(llm_dedupe_key):
            logger.info(f"Skipping duplicate CHAT request: {request_id}")
            self.publish_status(
                f"[{request_id}] Already processed (duplicate)",
                title="Duplicate Request"
            )
            return
        
        self.publish_status(
            f"[{request_id}] Chatting...", title="Chat Request"
        )

        if self.dry_run:
            response_text = f"[{request_id}] (dry run) {content}"
        else:
            try:
                response_text = self._run_chat_llm(content)
                
                # Validation: detect runaway generation
                if len(response_text) > 20000:
                    logger.warning(
                        f"CHAT request {request_id} generated excessive output: "
                        f"{len(response_text)} chars (possible runaway)"
                    )
                    response_text = (
                        response_text[:20000] + 
                        "\n\n[Output truncated: exceeded safe limit. "
                        "Possible runaway generation detected.]"
                    )
                
                # Validation: detect token repetition loops
                if self._detect_token_loop(response_text):
                    logger.error(
                        f"CHAT request {request_id} contains repetition loop"
                    )
                    response_text = (
                        "[Error: Repetition loop detected in response. "
                        "This may indicate a model configuration issue.]\n\n" +
                        response_text[:1000]
                    )
                    
            except Exception as exc:
                logger.error(
                    "Chat LLM failed for request %s: %s",
                    request_id,
                    exc,
                    exc_info=True,
                )
                self.publish_status(
                    f"❌ [{request_id}] Chat failed: {exc}",
                    title="Chat Error",
                )
                return

        # Mark as processed before publishing (idempotency)
        self.request_tracker.mark_processed(llm_dedupe_key)

        title = self._output_title(request_id, "Chat", success=True)
        publish_response(
            self.ntfy_client,
            self.config.answer_topic,
            title,
            response_text,
            request_id,
            self.config,
            force_file=True,
            mode_tag="chat",
        )

    @staticmethod
    def _detect_token_loop(text: str, threshold: int = 10) -> bool:
        """
        Detect if text contains excessive token repetition (runaway loop).
        
        Args:
            text: Text to check
            threshold: Max allowed consecutive occurrences of same token
            
        Returns:
            True if loop detected, False otherwise
        """
        # Check for "assistant" token repetition
        if text.count("assistant") > threshold:
            return True
        
        # Check for short repeating patterns
        words = text.lower().split()
        if len(words) < 20:
            return False
            
        # Look for same word repeated >threshold times consecutively
        prev_word = None
        count = 1
        for word in words:
            if word == prev_word:
                count += 1
                if count > threshold:  # Changed from >= to >
                    return True
            else:
                count = 1
                prev_word = word
        
        return False


    @staticmethod
    def _run_chat_llm(content: str) -> str:
        base_url = os.getenv("LLM_API_URL", "http://localhost:8000").rstrip("/")
        model = (
            os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "llama31-8b-instruct"
        )
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        max_tokens = int(os.getenv("MILTON_CHAT_MAX_TOKENS", "4000"))
        
        # CRITICAL: Add stop sequences to prevent runaway token generation
        # These stop sequences prevent the model from repeating "assistant" token
        # or continuing past natural end-of-turn markers
        stop_sequences = [
            "assistant",  # Prevent "assistant" token repetition
            "</s>",       # Standard EOS token
            "<|eot_id|>", # Llama 3.1 end-of-turn
            "\n\nassistant",  # Double newline + assistant
        ]
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stop": stop_sequences,  # ← FIX: Add stop sequences
        }
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        
        # Check response status and raise with body on error
        if not response.ok:
            raise RuntimeError(
                f"LLM API error: {response.status_code} {response.reason} - {response.text}"
            )
        
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

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

    def process_self_upgrade_request(self, request_id: str, content: str):
        """Process SELF_UPGRADE requests."""
        logger.info(f"Processing SELF_UPGRADE request {request_id}")
        
        self.publish_status(
            f"[{request_id}] Self-upgrade request received. Analyzing...",
            title="Self-Upgrade Request",
        )
        
        try:
            summary = process_self_upgrade_request(
                request_id,
                content,
                repo_root=self.config.target_repo,
            )
            
            title = self._output_title(request_id, "Self-Upgrade", success=True)
            publish_response(
                self.ntfy_client,
                self.config.answer_topic,
                title,
                summary,
                request_id,
                self.config,
                mode_tag="self_upgrade",
            )
        
        except Exception as exc:
            logger.error(
                "Error processing self-upgrade request %s: %s",
                request_id,
                exc,
                exc_info=True,
            )
            self.publish_status(
                f"❌ [{request_id}] Self-upgrade failed: {exc}",
                title="Self-Upgrade Error",
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

    def _publish_final_output(
        self,
        request_id: str,
        tool_name: str,
        result,
        output_file: Optional[Path] = None,
        note: Optional[str] = None,
        mode_tag: Optional[str] = None,
    ) -> None:
        full_text = self._load_output_text(output_file, result)
        if note:
            full_text = f"{note}\n\n{full_text}" if full_text else note
        title = self._output_title(request_id, tool_name, result.success)
        publish_response(
            self.ntfy_client,
            self.config.answer_topic,
            title,
            full_text,
            request_id,
            self.config,
            output_path=output_file,
            mode_tag=mode_tag,
        )

    @staticmethod
    def _load_output_text(output_file: Optional[Path], result) -> str:
        if output_file:
            try:
                return output_file.read_text()
            except OSError as exc:
                logger.warning(f"Failed to read output file {output_file}: {exc}")

        stdout = getattr(result, "stdout", "")
        stderr = getattr(result, "stderr", "")
        return "\n".join(part for part in (stdout, stderr) if part).strip()

    @staticmethod
    def _output_title(request_id: str, tool_name: str, success: bool) -> str:
        status = "ready" if success else "failed"
        return f"{tool_name} output {status} ({request_id})"

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
                if kind == "SELF_UPGRADE":
                    return "SELF_UPGRADE", payload, None

        return "CHAT", text.strip(), None

    def process_incoming_message(
        self,
        message_id: str,
        topic: str,
        message: str,
        raw_data: Optional[dict[str, object]] = None,
    ):
        # Idempotency check: prevent duplicate processing of same ntfy message
        dedupe_key = self.idempotency.make_dedupe_key(
            message_id=message_id,
            topic=topic,
            message=message,
            timestamp=raw_data.get("time") if raw_data else None,
        )
        
        if self.idempotency.has_processed(dedupe_key):
            logger.info(
                f"Skipping duplicate message: message_id={message_id}, "
                f"dedupe_key={dedupe_key}"
            )
            # Still send ack to ntfy, but don't reprocess
            self.publish_status(
                f"Message already processed (duplicate delivery)",
                title="Duplicate Message"
            )
            return
        
        normalized = normalize_incoming_input(message, raw_data=raw_data)
        request_id = self.generate_request_id(message_id, normalized.semantic_input)
        mode, payload, reminder_kind = self.route_message(topic, normalized.semantic_input)
        mode_tag = _mode_tag(mode, reminder_kind)

        attachment_paths = self._persist_attachments(request_id, normalized.attachments)
        if attachment_paths:
            logger.info(
                "Stored %d attachment(s) for request_id=%s",
                len(attachment_paths),
                request_id,
            )

        memory_ids = self._record_request_memory(
            request_id,
            normalized.semantic_input,
            mode_tag,
            topic,
            input_type=normalized.input_type,
            structured_fields=normalized.structured_fields,
        )

        logger.info(
            "Normalized input: type=%s length=%d attachments=%d",
            normalized.input_type,
            normalized.normalized_length,
            len(normalized.attachments),
        )
        logger.info(
            "Routing decision: mode=%s input_type=%s length=%d dedupe_key=%s",
            mode,
            normalized.input_type,
            normalized.normalized_length,
            dedupe_key,
        )
        logger.info(
            "Memory capture: ran=%s ids=%s",
            bool(memory_ids),
            memory_ids or "none",
        )

        memory_note = ""
        if memory_ids:
            if len(memory_ids) == 1:
                memory_note = f" | Memory: {memory_ids[0]}"
            else:
                memory_note = (
                    f" | Memory: {memory_ids[0]} (+{len(memory_ids) - 1} more)"
                )

        self.publish_status(
            f"[{request_id}] Mode: {mode}{memory_note}",
            title="Request Acknowledged",
        )
        
        # Mark message as processed BEFORE executing (prevents race conditions)
        self.idempotency.mark_processed(
            dedupe_key=dedupe_key,
            message_id=message_id,
            topic=topic,
            request_id=request_id,
            message=message,
        )

        if mode == "CLAUDE_CODE":
            self.process_claude_code_request(request_id, payload, mode_tag=mode_tag)
        elif mode == "CODEX_CODE":
            self.process_codex_code_request(request_id, payload, mode_tag=mode_tag)
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
            full_text = self._format_research_response(request_id, research_notes)
            title = self._output_title(request_id, "Research", success=True)
            publish_response(
                self.ntfy_client,
                self.config.answer_topic,
                title,
                full_text,
                request_id,
                self.config,
                mode_tag=mode_tag,
            )
        elif mode == "REMINDER":
            if not reminder_kind:
                reminder_kind = "REMIND"
            self.process_reminder_request(request_id, payload, reminder_kind)
        elif mode == "SELF_UPGRADE":
            self.process_self_upgrade_request(request_id, payload)
        else:
            self.process_chat_request(request_id, payload)

    def process_research_request(self, request_id: str, content: str):
        """Process a RESEARCH request (no Claude execution)"""
        logger.info(f"Processing RESEARCH request {request_id}")
        mode_tag = "research"

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
            title = self._output_title(request_id, "Research", success=True)
            publish_response(
                self.ntfy_client,
                self.config.answer_topic,
                title,
                formatted,
                request_id,
                self.config,
                mode_tag=mode_tag,
            )
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

                self.process_incoming_message(msg.id, msg.topic, msg.message, raw_data=msg.raw)

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
    for kind in ("CLAUDE", "CODEX", "RESEARCH", "REMIND", "ALARM", "SELF_UPGRADE"):
        payload = _strip_prefix_with_optional_brackets(text, kind)
        if payload != text:
            return kind, payload.strip()
    return None


def _strip_prefix_with_optional_brackets(text: str, prefix: str) -> str:
    pattern = re.compile(
        rf"^\s*\[?\s*{re.escape(prefix)}\s*:\s*(.*)$",
        re.IGNORECASE | re.DOTALL,
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


def _chunk_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return []
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    return [text[idx : idx + max_chars] for idx in range(0, len(text), max_chars)]


_MEMORY_CACHE = None


def _get_memory_modules():
    global _MEMORY_CACHE
    if _MEMORY_CACHE is not None:
        return _MEMORY_CACHE
    try:
        from memory.schema import MemoryItem
        from memory.store import add_memory
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[1]
        repo_str = str(repo_root)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)
        from memory.schema import MemoryItem
        from memory.store import add_memory
    _MEMORY_CACHE = (MemoryItem, add_memory)
    return _MEMORY_CACHE


def _mode_tag(mode: str, reminder_kind: Optional[str]) -> Optional[str]:
    if mode == "CLAUDE_CODE":
        return "claude"
    if mode == "CODEX_CODE":
        return "codex"
    if mode == "RESEARCH":
        return "research"
    if mode == "REMINDER":
        return (reminder_kind or "remind").lower()
    if mode == "CHAT":
        return "chat"
    return None


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
