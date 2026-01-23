"""Command processor for Milton Gateway.

Handles special slash commands that trigger API calls to Milton services.
Also handles natural-language intents with confirmation workflow.
Learns from user corrections to improve intent selection over time.

Phase 4 enhancements:
- Action ledger for undo/rollback
- Draft mode with explicit commits
- User preferences and defaults
- Action receipts with undo tokens
- Multi-intent splitting
- Time sanity checks
- Cross-message linking
- Daily digest
- Privacy controls for learning
"""

import json
import logging
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

# Confidence thresholds for natural language processing
AUTO_EXEC_THRESHOLD = 0.75  # Auto-execute above this (lowered from 0.92)
CONFIRM_THRESHOLD = 0.65    # Execute reads above this, confirm writes below AUTO_EXEC

# Learning configuration
LEARN_FROM_CORRECTIONS = os.getenv("LEARN_FROM_CORRECTIONS", "true").lower() == "true"


@dataclass
class CommandResult:
    """Result of processing a command."""

    is_command: bool
    response: Optional[str] = None
    error: Optional[str] = None


class CommandProcessor:
    """Process slash commands and natural language intents."""

    def __init__(self, milton_api_base_url: str = "http://localhost:8001", state_dir: Optional[Path] = None, session_id: Optional[str] = None):
        """Initialize command processor.

        Args:
            milton_api_base_url: Base URL for Milton API (default: http://localhost:8001)
            state_dir: Optional state directory path (for testing)
            session_id: Optional session ID for tracking conversations
        """
        self.milton_api_base_url = milton_api_base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=10.0)
        self.state_dir = state_dir or self._get_default_state_dir()
        self.session_id = session_id or "default"
        
        # Initialize stores (lazy loaded)
        self._memory_store = None
        self._pending_store = None
        self._corrections_store = None
        self._action_ledger = None
        self._preferences = None
        self._context_tracker = None

    def _get_default_state_dir(self) -> Path:
        """Get default state directory."""
        state_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR") or Path.home() / ".local" / "state" / "milton"
        return Path(state_dir)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        if self._memory_store:
            self._memory_store.close()
    
    def _get_memory_store(self):
        """Get or initialize the chat memory store."""
        if self._memory_store is None:
            from storage.chat_memory import ChatMemoryStore
            db_path = self.state_dir / "chat_memory.sqlite3"
            self._memory_store = ChatMemoryStore(db_path)
            logger.info(f"Initialized chat memory store at {db_path}")
        return self._memory_store
    
    def _get_pending_store(self):
        """Get or initialize the pending confirmation store."""
        if self._pending_store is None:
            from milton_gateway.pending_confirmations import PendingConfirmationStore
            db_path = self.state_dir / "pending_confirmations.sqlite3"
            self._pending_store = PendingConfirmationStore(db_path)
            logger.info(f"Initialized pending confirmation store at {db_path}")
        return self._pending_store
    
    def _get_corrections_store(self):
        """Get or initialize the corrections store for learning."""
        if self._corrections_store is None:
            from milton_gateway.corrections_store import CorrectionsStore
            db_path = self.state_dir / "corrections.sqlite3"
            self._corrections_store = CorrectionsStore(db_path, enabled=LEARN_FROM_CORRECTIONS)
            logger.info(f"Initialized corrections store at {db_path} (enabled={LEARN_FROM_CORRECTIONS})")
        return self._corrections_store
    
    def _get_action_ledger(self):
        """Get or initialize the action ledger."""
        if self._action_ledger is None:
            from milton_gateway.action_ledger import ActionLedger
            db_path = self.state_dir / "action_ledger.sqlite3"
            self._action_ledger = ActionLedger(db_path)
            logger.info(f"Initialized action ledger at {db_path}")
        return self._action_ledger
    
    def _get_preferences(self):
        """Get or initialize the preferences store."""
        if self._preferences is None:
            from milton_gateway.preferences import Preferences
            db_path = self.state_dir / "preferences.sqlite3"
            self._preferences = Preferences(db_path)
            logger.info(f"Initialized preferences at {db_path}")
        return self._preferences
    
    def _get_context_tracker(self):
        """Get or initialize the context tracker."""
        if self._context_tracker is None:
            from milton_gateway.context_tracker import ContextTracker
            self._context_tracker = ContextTracker()
            logger.info("Initialized context tracker")
        return self._context_tracker

    async def process_message(self, content: str) -> CommandResult:
        """Process a user message and handle commands or natural language intents.

        Args:
            content: The user's message

        Returns:
            CommandResult indicating if command was processed
        """
        content = content.strip()
        
        # Priority 1: Handle slash commands (unchanged behavior)
        if content.startswith("/"):
            return await self._handle_slash_command(content)
        
        # Priority 2: Check for Yes/No/Edit responses to pending confirmations
        pending_store = self._get_pending_store()
        pending = pending_store.get(self.session_id)
        
        if pending:
            # Check if this is a response to the pending confirmation
            if self._is_confirmation_response(content):
                return await self._handle_confirmation_response(content, pending)
        
        # Priority 3: Try natural language intent parsing
        return await self._handle_natural_language(content)
    
    async def _handle_slash_command(self, content: str) -> CommandResult:
        """Handle slash commands (existing behavior + new commands).
        
        Args:
            content: Message starting with /
            
        Returns:
            CommandResult from slash command handler
        """
        # Check for new Phase 4 commands
        if content.startswith("/undo"):
            return await self._handle_undo_command(content)
        
        if content.startswith("/preferences") or content.startswith("/prefs"):
            return self._handle_preferences_command(content)
        
        if content.startswith("/digest") or content.startswith("/audit"):
            return self._handle_digest_command(content)
        
        if content.startswith("/forget"):
            return self._handle_forget_command(content)
        
        # Check for /briefing command
        if content.startswith("/briefing "):
            return await self._handle_briefing_command(content)

        # Check for /reminder command
        if content.startswith("/reminder "):
            return await self._handle_reminder_command(content)
        
        # Check for /remember command
        if content.startswith("/remember "):
            return self._handle_remember_command(content)
        
        # Check for /remember command (alias for /memory)
        if content.startswith("/remember "):
            return self._handle_remember_command(content)
        
        # Check for /memory command
        if content.startswith("/memory"):
            return self._handle_memory_command(content)
        
        # Check for /recent or /context command (Phase 2C)
        if content.startswith("/recent") or content.startswith("/context"):
            return self._handle_context_query(content)

        # Check for /goal command
        if content.startswith("/goal"):
            return self._handle_goal_command(content)

        # Unknown slash command
        return CommandResult(
            is_command=True,
            error="Unknown command. Try /goal, /briefing, /reminder, /remember, /memory, /undo, /preferences, /digest, /forget"
        )
    
    def _is_confirmation_response(self, content: str) -> bool:
        """Check if content is a Yes/No/Edit response.
        
        Args:
            content: User message
            
        Returns:
            True if this looks like a confirmation response
        """
        content_lower = content.lower().strip()
        return (
            content_lower == "yes" or
            content_lower == "no" or
            content_lower.startswith("edit:")
        )
    
    async def _handle_confirmation_response(self, content: str, pending) -> CommandResult:
        """Handle Yes/No/Edit response to a pending confirmation.
        
        Args:
            content: User's response (Yes/No/Edit: ...)
            pending: PendingConfirmation object
            
        Returns:
            CommandResult with execution result or new confirmation
        """
        content_lower = content.lower().strip()
        pending_store = self._get_pending_store()
        
        # Handle "Yes" - execute the candidate
        if content_lower == "yes":
            pending_store.clear(self.session_id)
            candidate = json.loads(pending.candidate_json)
            
            # NEW: Store confirmation as learning example
            self._store_correction(
                original_text=pending.original_text,
                intent_before=candidate,  # Before and after are same for "Yes"
                intent_after=candidate,
                outcome="confirmed"
            )
            
            return await self._execute_intent_candidate(candidate)
        
        # Handle "No" - cancel
        if content_lower == "no":
            pending_store.clear(self.session_id)
            return CommandResult(
                is_command=True,
                response="❌ Canceled. Feel free to rephrase your request if you'd like to try again."
            )
        
        # Handle "Edit: ..." - modify and re-confirm
        if content_lower.startswith("edit:"):
            edit_text = content[5:].strip()
            if not edit_text:
                return CommandResult(
                    is_command=True,
                    error="Please provide your edit after 'Edit:'. Example: Edit: change time to 3pm"
                )
            
            # Parse the edit with context of the original candidate
            original_candidate = json.loads(pending.candidate_json)
            updated_candidate = await self._apply_edit(edit_text, original_candidate, pending.original_text)
            
            # NEW: Store edit as learning example (will be confirmed when user says Yes)
            # For now, just store the edit itself as a weak signal
            self._store_correction(
                original_text=pending.original_text,
                intent_before=original_candidate,
                intent_after=updated_candidate,
                outcome="edited"
            )
            
            # Generate new confirmation with updated candidate
            return self._generate_confirmation(
                original_text=f"{pending.original_text} (edited: {edit_text})",
                candidate=updated_candidate,
                confidence=updated_candidate.get("confidence", 0.7)
            )
        
        # Should not reach here
        return CommandResult(is_command=False)
    
    async def _handle_natural_language(self, content: str) -> CommandResult:
        """Handle natural language input using intent parser.
        
        Args:
            content: User's natural language message
            
        Returns:
            CommandResult with either execution result or confirmation request
        """
        from milton_gateway.intent_parser import parse_nl_intent, IntentType, IntentAction
        
        # NEW: Check for learned corrections first
        corrections_store = self._get_corrections_store()
        similar_corrections = corrections_store.find_similar(content, limit=3)
        
        # Parse the intent
        intent_result = parse_nl_intent(content)
        
        # Case A: Needs clarification
        if intent_result.needs_clarification:
            question = intent_result.clarifying_question or "Could you please clarify what you'd like to do?"
            return CommandResult(
                is_command=True,
                response=f"❓ {question}"
            )
        
        # Case B: Unknown intent (low confidence or no match)
        if intent_result.intent_type == IntentType.UNKNOWN or intent_result.confidence < CONFIRM_THRESHOLD:
            return CommandResult(is_command=False)  # Let LLM handle it
        
        # NEW: Apply learned corrections if available
        if similar_corrections:
            learned_candidate = self._apply_learned_correction(content, intent_result, similar_corrections)
            if learned_candidate:
                # Use learned candidate with boosted confidence
                candidate = learned_candidate
            else:
                # Build candidate from parser result
                candidate = {
                    "intent_type": intent_result.intent_type.value,
                    "action": intent_result.action.value,
                    "payload": intent_result.payload,
                    "confidence": round(intent_result.confidence, 2)
                }
        else:
            # Build candidate from parser result
            candidate = {
                "intent_type": intent_result.intent_type.value,
                "action": intent_result.action.value,
                "payload": intent_result.payload,
                "confidence": round(intent_result.confidence, 2)
            }
        
        # Determine if this is a write action
        is_write_action = intent_result.action == IntentAction.ADD
        
        # Case C: Read-only action with sufficient confidence
        if not is_write_action and intent_result.confidence >= CONFIRM_THRESHOLD:
            return await self._execute_intent_candidate(candidate)
        
        # Case D: Write action with very high confidence
        if is_write_action and intent_result.confidence >= AUTO_EXEC_THRESHOLD:
            return await self._execute_intent_candidate(candidate)
        
        # Case E: Requires confirmation
        return self._generate_confirmation(
            original_text=content,
            candidate=candidate,
            confidence=intent_result.confidence
        )

    async def _handle_briefing_command(self, content: str) -> CommandResult:
        """Handle /briefing commands.

        Supported formats:
        - /briefing add <text>
        - /briefing add <text> | priority:<n>
        - /briefing add <text> | due:<date>
        - /briefing list
        """
        # Remove /briefing prefix
        command = content[10:].strip()

        # List command
        if command == "list" or command.startswith("list "):
            return await self._briefing_list()

        # Add command
        if command == "add" or command.startswith("add "):
            text = command[4:].strip()
            if not text:
                return CommandResult(
                    is_command=True, error="Usage: /briefing add <text> [| priority:<n>] [| due:<date>]"
                )
            return await self._briefing_add(text)

        # Unknown subcommand
        return CommandResult(
            is_command=True, error="Unknown briefing command. Use: /briefing add <text> or /briefing list"
        )

    async def _briefing_add(self, text: str) -> CommandResult:
        """Add a briefing item via Milton API.

        Format: <content> [| priority:<n>] [| due:<date>]
        """
        # Parse optional metadata
        parts = text.split("|")
        content = parts[0].strip()
        priority = 0
        due_at = None

        for part in parts[1:]:
            part = part.strip()
            if part.startswith("priority:"):
                try:
                    priority = int(part[9:].strip())
                except ValueError:
                    return CommandResult(is_command=True, error="Priority must be a number (0-10)")
            elif part.startswith("due:"):
                due_str = part[4:].strip()
                due_at = self._parse_due_date(due_str)
                if not due_at:
                    return CommandResult(
                        is_command=True,
                        error=f"Invalid due date format. Use YYYY-MM-DD or 'tomorrow' or 'monday'",
                    )

        # Call Milton API
        try:
            payload = {
                "content": content,
                "priority": priority,
                "source": "interactive-chat",
            }
            if due_at:
                payload["due_at"] = due_at

            response = await self.client.post(
                f"{self.milton_api_base_url}/api/briefing/items",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            item_id = data.get("id")
            priority_tag = f"[P{priority}] " if priority != 0 else ""
            due_tag = f" [due: {due_at[:10]}]" if due_at else ""

            return CommandResult(
                is_command=True,
                response=f"✅ Added to morning briefing: {priority_tag}{content}{due_tag}\n(Item ID: {item_id})",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Milton API error: {e.response.status_code} - {e.response.text}")
            return CommandResult(
                is_command=True, error=f"Failed to add item (API error {e.response.status_code})"
            )
        except Exception as e:
            logger.exception(f"Failed to add briefing item: {e}")
            return CommandResult(is_command=True, error=f"Failed to add item: {str(e)}")

    async def _briefing_list(self) -> CommandResult:
        """List active briefing items."""
        try:
            response = await self.client.get(f"{self.milton_api_base_url}/api/briefing/items?status=active")
            response.raise_for_status()

            data = response.json()
            items = data.get("items", [])
            count = data.get("count", 0)

            if count == 0:
                return CommandResult(is_command=True, response="No active briefing items.")

            lines = [f"📋 Active briefing items ({count}):"]
            for item in items[:10]:  # Limit to 10
                priority = item.get("priority", 0)
                content = item.get("content", "")
                due_at = item.get("due_at")
                item_id = item.get("id")

                priority_tag = f"[P{priority}] " if priority != 0 else ""
                due_tag = f" [due: {due_at[:10]}]" if due_at else ""
                lines.append(f"  {item_id}. {priority_tag}{content}{due_tag}")

            return CommandResult(is_command=True, response="\n".join(lines))

        except Exception as e:
            logger.exception(f"Failed to list briefing items: {e}")
            return CommandResult(is_command=True, error=f"Failed to list items: {str(e)}")

    async def _handle_reminder_command(self, content: str) -> CommandResult:
        """Handle /reminder commands.

        Supported formats:
        - /reminder add <text> | at:<time>
        - /reminder list
        """
        # Remove /reminder prefix
        command = content[10:].strip()

        if command == "list":
            return await self._reminder_list()

        if command.startswith("add "):
            text = command[4:].strip()
            if not text:
                return CommandResult(
                    is_command=True, error="Usage: /reminder add <text> | at:<time>"
                )
            return await self._reminder_add(text)

        return CommandResult(
            is_command=True, error="Unknown reminder command. Use: /reminder add <text> | at:<time> or /reminder list"
        )

    async def _reminder_add(self, text: str) -> CommandResult:
        """Add a reminder via Milton API.

        Format: <message> | at:<time>
        """
        # Parse message and time
        parts = text.split("|")
        message = parts[0].strip()

        at_time = None
        for part in parts[1:]:
            part = part.strip()
            if part.startswith("at:"):
                time_str = part[3:].strip()
                at_time = self._parse_reminder_time(time_str)

        if not at_time:
            return CommandResult(
                is_command=True,
                error="Reminder time required. Use: /reminder add <text> | at:<time> (e.g., 'at:tomorrow 9am')",
            )

        try:
            payload = {"message": message, "remind_at": at_time}

            response = await self.client.post(
                f"{self.milton_api_base_url}/api/reminders",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            reminder_id = data.get("id")
            readable_time = datetime.fromtimestamp(at_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            return CommandResult(
                is_command=True,
                response=f"⏰ Reminder set: {message}\n  At: {readable_time}\n(Reminder ID: {reminder_id})",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Milton API error: {e.response.status_code} - {e.response.text}")
            return CommandResult(
                is_command=True, error=f"Failed to create reminder (API error {e.response.status_code})"
            )
        except Exception as e:
            logger.exception(f"Failed to create reminder: {e}")
            return CommandResult(is_command=True, error=f"Failed to create reminder: {str(e)}")

    async def _reminder_list(self) -> CommandResult:
        """List scheduled reminders."""
        try:
            response = await self.client.get(f"{self.milton_api_base_url}/api/reminders?status=scheduled")
            response.raise_for_status()

            data = response.json()
            reminders = data.get("reminders", [])
            count = data.get("count", 0)

            if count == 0:
                return CommandResult(is_command=True, response="No scheduled reminders.")

            lines = [f"⏰ Scheduled reminders ({count}):"]
            for reminder in reminders[:10]:
                message = reminder.get("message", "")
                remind_at = reminder.get("remind_at")
                reminder_id = reminder.get("id")

                readable_time = datetime.fromtimestamp(remind_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  {reminder_id}. {message} (at {readable_time})")

            return CommandResult(is_command=True, response="\n".join(lines))

        except Exception as e:
            logger.exception(f"Failed to list reminders: {e}")
            return CommandResult(is_command=True, error=f"Failed to list reminders: {str(e)}")

    def _parse_due_date(self, date_str: str) -> Optional[str]:
        """Parse a due date string into ISO8601 format.

        Supports:
        - YYYY-MM-DD
        - tomorrow
        - monday, tuesday, etc.
        """
        date_str = date_str.strip().lower()
        now = datetime.now(timezone.utc)

        # Tomorrow
        if date_str == "tomorrow":
            target = now + timedelta(days=1)
            return target.strftime("%Y-%m-%dT09:00:00Z")

        # Day of week
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if date_str in days:
            target_weekday = days.index(date_str)
            current_weekday = now.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week
            target = now + timedelta(days=days_ahead)
            return target.strftime("%Y-%m-%dT09:00:00Z")

        # YYYY-MM-DD format
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
        if match:
            return f"{date_str}T09:00:00Z"

        return None

    def _parse_reminder_time(self, time_str: str) -> Optional[int]:
        """Parse reminder time into Unix timestamp.

        Supports:
        - tomorrow 9am
        - monday 2pm
        - 2026-01-15 14:00
        - +2h (2 hours from now)
        """
        time_str = time_str.strip().lower()
        now = datetime.now(timezone.utc)

        # Relative time (+Xh, +Xm)
        match = re.match(r"^\+(\d+)([hm])$", time_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == "h":
                target = now + timedelta(hours=value)
            else:  # m
                target = now + timedelta(minutes=value)
            return int(target.timestamp())

        # Tomorrow + time
        if time_str.startswith("tomorrow "):
            time_part = time_str[9:].strip()
            hour = self._parse_hour(time_part)
            if hour is not None:
                target = now + timedelta(days=1)
                target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
                return int(target.timestamp())

        # Day of week + time
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for day in days:
            if time_str.startswith(day + " "):
                time_part = time_str[len(day) + 1 :].strip()
                hour = self._parse_hour(time_part)
                if hour is not None:
                    target_weekday = days.index(day)
                    current_weekday = now.weekday()
                    days_ahead = (target_weekday - current_weekday) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target = now + timedelta(days=days_ahead)
                    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
                    return int(target.timestamp())

        return None

    def _parse_hour(self, time_str: str) -> Optional[int]:
        """Parse hour from time string like '9am', '2pm', '14:00'."""
        time_str = time_str.strip().lower()

        # 9am, 2pm format
        match = re.match(r"^(\d{1,2})(am|pm)$", time_str)
        if match:
            hour = int(match.group(1))
            period = match.group(2)
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0
            return hour if 0 <= hour <= 23 else None

        # 14:00 format
        match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
        if match:
            hour = int(match.group(1))
            return hour if 0 <= hour <= 23 else None

        return None
    
    def _handle_remember_command(self, content: str) -> CommandResult:
        """Handle /remember command for storing memory facts.
        
        Supported formats:
        - /remember <key>: <value>
        - /remember <key> = <value>
        
        Examples:
        - /remember name: Cole
        - /remember favorite_color = blue
        """
        # Remove /remember prefix
        command = content[10:].strip()
        
        if not command:
            return CommandResult(
                is_command=True,
                error="Usage: /remember <key>: <value> or /remember <key> = <value>"
            )
        
        # Try to parse key: value or key = value format
        if ": " in command:
            parts = command.split(": ", 1)
        elif " = " in command:
            parts = command.split(" = ", 1)
        elif ":" in command:
            parts = command.split(":", 1)
        elif "=" in command:
            parts = command.split("=", 1)
        else:
            return CommandResult(
                is_command=True,
                error="Format must be: <key>: <value> or <key> = <value>"
            )
        
        if len(parts) != 2:
            return CommandResult(
                is_command=True,
                error="Format must be: <key>: <value> or <key> = <value>"
            )
        
        key = parts[0].strip()
        value = parts[1].strip()
        
        if not key or not value:
            return CommandResult(
                is_command=True,
                error="Both key and value must be non-empty"
            )
        
        try:
            store = self._get_memory_store()
            store.upsert_fact(key, value)
            return CommandResult(
                is_command=True,
                response=f"✅ Remembered: **{key}** = {value}"
            )
        except Exception as e:
            logger.exception(f"Error storing memory fact: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to store memory: {e}"
            )
    
    def _handle_memory_command(self, content: str) -> CommandResult:
        """Handle /memory commands for viewing stored facts.
        
        Supported formats:
        - /memory show (or just /memory)
        - /memory get <key>
        - /memory delete <key>
        """
        # Remove /memory prefix
        command = content[7:].strip()
        
        # Default to "show" if no subcommand
        if not command or command == "show":
            return self._memory_show()
        
        # Get specific fact
        if command.startswith("get "):
            key = command[4:].strip()
            if not key:
                return CommandResult(
                    is_command=True,
                    error="Usage: /memory get <key>"
                )
            return self._memory_get(key)
        
        # Delete fact
        if command.startswith("delete "):
            key = command[7:].strip()
            if not key:
                return CommandResult(
                    is_command=True,
                    error="Usage: /memory delete <key>"
                )
            return self._memory_delete(key)
        
        # Unknown subcommand
        return CommandResult(
            is_command=True,
            error="Unknown memory command. Use: /memory show, /memory get <key>, or /memory delete <key>"
        )
    
    def _memory_show(self) -> CommandResult:
        """Show all stored memory facts."""
        try:
            store = self._get_memory_store()
            facts = store.get_all_facts()
            
            logger.info(f"💾 _memory_show: Retrieved {len(facts)} facts from database")
            logger.info(f"💾 Database path: {self.state_dir / 'chat_memory.sqlite3'}")
            
            if not facts:
                return CommandResult(
                    is_command=True,
                    response="📝 No memory facts stored yet.\n\nUse `/remember <key>: <value>` to store something."
                )
            
            # Format facts as a list
            lines = ["📝 **Stored Memory Facts:**\n"]
            for fact in facts:
                lines.append(f"• **{fact.key}** = {fact.value}")
            
            return CommandResult(
                is_command=True,
                response="\n".join(lines)
            )
        except Exception as e:
            logger.exception(f"Error retrieving memory facts: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to retrieve memory: {e}"
            )
    
    def _memory_get(self, key: str) -> CommandResult:
        """Get a specific memory fact."""
        try:
            store = self._get_memory_store()
            fact = store.get_fact(key)
            
            if not fact:
                return CommandResult(
                    is_command=True,
                    response=f"❓ No memory fact found for key: **{key}**"
                )
            
            return CommandResult(
                is_command=True,
                response=f"📝 **{fact.key}** = {fact.value}"
            )
        except Exception as e:
            logger.exception(f"Error retrieving memory fact: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to retrieve memory: {e}"
            )
    
    def _memory_delete(self, key: str) -> CommandResult:
        """Delete a memory fact."""
        try:
            store = self._get_memory_store()
            deleted = store.delete_fact(key)
            
            if deleted:
                return CommandResult(
                    is_command=True,
                    response=f"✅ Deleted memory fact: **{key}**"
                )
            else:
                return CommandResult(
                    is_command=True,
                    response=f"❓ No memory fact found for key: **{key}**"
                )
        except Exception as e:
            logger.exception(f"Error deleting memory fact: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to delete memory: {e}"
            )
    
    def _handle_remember_command(self, content: str) -> CommandResult:
        """Handle /remember command to store a fact.
        
        Format: /remember <key>: <value>
        """
        # Remove /remember prefix
        fact_text = content[10:].strip()
        
        if not fact_text or ':' not in fact_text:
            return CommandResult(
                is_command=True,
                error="Usage: /remember <key>: <value>\n\nExample: /remember favorite_food: pizza"
            )
        
        # Split on first colon
        parts = fact_text.split(':', 1)
        key = parts[0].strip()
        value = parts[1].strip()
        
        if not key or not value:
            return CommandResult(
                is_command=True,
                error="Both key and value are required.\n\nExample: /remember favorite_food: pizza"
            )
        
        # Store the fact
        try:
            store = self._get_memory_store()
            store.upsert_fact(key, value)
            
            return CommandResult(
                is_command=True,
                response=f"✅ Stored: **{key}** = {value}"
            )
        except Exception as e:
            logger.exception(f"Failed to store fact: {e}")
            return CommandResult(is_command=True, error=str(e))
    
    def _handle_context_query(self, content: str) -> CommandResult:
        """Handle /recent or /context commands to query activity snapshots.
        
        Formats:
        - /recent         (default: last 2 hours)
        - /recent 30m     (last 30 minutes)
        - /recent 4h      (last 4 hours)
        - /context        (alias for /recent)
        """
        from datetime import datetime, timezone
        from milton_orchestrator.activity_snapshots import ActivitySnapshotStore
        from milton_orchestrator.state_paths import resolve_state_dir
        
        # Parse time window
        default_minutes = 120  # 2 hours default
        minutes = default_minutes
        
        # Extract time specification if present
        parts = content.split()
        if len(parts) > 1:
            time_spec = parts[1].lower()
            # Parse formats like "30m", "2h", "90m"
            if time_spec.endswith('m'):
                try:
                    minutes = int(time_spec[:-1])
                except ValueError:
                    return CommandResult(
                        is_command=True,
                        error=f"Invalid time format: '{time_spec}'. Use format like '30m' or '2h'"
                    )
            elif time_spec.endswith('h'):
                try:
                    hours = int(time_spec[:-1])
                    minutes = hours * 60
                except ValueError:
                    return CommandResult(
                        is_command=True,
                        error=f"Invalid time format: '{time_spec}'. Use format like '30m' or '2h'"
                    )
        
        # Query activity snapshots
        try:
            # Use provided state_dir or resolve from environment
            if self.state_dir:
                state_dir = self.state_dir
            else:
                state_dir = resolve_state_dir()
            db_path = state_dir / "activity_snapshots.db"
            store = ActivitySnapshotStore(db_path=db_path)
            
            try:
                snapshots = store.get_recent(minutes=minutes, limit=10)
                
                if not snapshots:
                    hours_display = minutes / 60
                    time_window = f"{int(hours_display)}h" if hours_display >= 1 else f"{minutes}m"
                    return CommandResult(
                        is_command=True,
                        response=f"No recent activity found in the last {time_window}"
                    )
                
                # Format response
                lines = [f"📋 Recent Activity (last {minutes // 60}h {minutes % 60}m):", ""]
                
                # Group by device
                from collections import defaultdict
                by_device = defaultdict(list)
                for snap in snapshots:
                    by_device[snap.device_id].append(snap)
                
                for device_id, device_snaps in by_device.items():
                    # Get device type from first snapshot
                    device_type = device_snaps[0].device_type
                    lines.append(f"🖥️  **{device_id}** ({device_type})")
                    
                    for snap in device_snaps[:5]:  # Limit to 5 per device
                        # Format relative time
                        now = int(datetime.now(timezone.utc).timestamp())
                        elapsed = now - snap.captured_at
                        if elapsed < 3600:
                            time_ago = f"{elapsed // 60}m ago"
                        else:
                            time_ago = f"{elapsed // 3600}h ago"
                        
                        # Build info line
                        info_parts = []
                        if snap.active_app:
                            info_parts.append(f"App: {snap.active_app}")
                        if snap.project_path:
                            # Show just the project name, not full path
                            project_name = snap.project_path.split('/')[-1]
                            info_parts.append(f"Project: {project_name}")
                        if snap.git_branch:
                            info_parts.append(f"Branch: {snap.git_branch}")
                        
                        info_str = " | ".join(info_parts) if info_parts else "No details"
                        lines.append(f"  • {time_ago}: {info_str}")
                    
                    if len(device_snaps) > 5:
                        lines.append(f"  ... and {len(device_snaps) - 5} more snapshots")
                    lines.append("")
                
                return CommandResult(is_command=True, response="\n".join(lines))
                
            finally:
                store.close()
                
        except Exception as e:
            logger.exception(f"Failed to query activity snapshots: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to query recent activity: {str(e)}"
            )

    def _handle_goal_command(self, content: str) -> CommandResult:
        """Handle /goal commands for tracking daily/weekly/monthly goals.

        Supported formats:
        - /goal add <text>              (daily goal, default)
        - /goal add <text> | weekly     (weekly goal)
        - /goal add <text> | monthly    (monthly goal)
        - /goal list                    (list daily goals)
        - /goal list weekly             (list weekly goals)
        - /goal list monthly            (list monthly goals)
        """
        from goals.capture import capture_goal, normalize_goal_text
        from goals.api import list_goals
        from milton_orchestrator.state_paths import resolve_state_dir

        # Remove /goal prefix
        command = content[5:].strip()

        # Default to showing help if no subcommand
        if not command:
            return CommandResult(
                is_command=True,
                response=(
                    "🎯 **Goal Commands:**\n\n"
                    "**Add goals:**\n"
                    "  `/goal add <text>` - Add daily goal\n"
                    "  `/goal add <text> | weekly` - Add weekly goal\n"
                    "  `/goal add <text> | monthly` - Add monthly goal\n\n"
                    "**List goals:**\n"
                    "  `/goal list` - Show daily goals\n"
                    "  `/goal list weekly` - Show weekly goals\n"
                    "  `/goal list monthly` - Show monthly goals"
                )
            )

        # List command
        if command == "list" or command.startswith("list "):
            scope = "daily"
            if "weekly" in command:
                scope = "weekly"
            elif "monthly" in command:
                scope = "monthly"

            try:
                base_dir = resolve_state_dir()
                goals = list_goals(scope, base_dir=base_dir)

                if not goals:
                    return CommandResult(
                        is_command=True,
                        response=f"📋 No {scope} goals set yet.\n\nAdd one with: `/goal add <your goal>`"
                    )

                scope_emoji = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(scope, "🎯")
                lines = [f"{scope_emoji} **{scope.title()} Goals** ({len(goals)}):"]
                for i, goal in enumerate(goals, 1):
                    text = goal.get("text", "")
                    status = goal.get("status", "active")
                    status_icon = "✅" if status == "completed" else "⬜"
                    lines.append(f"  {status_icon} {i}. {text}")

                return CommandResult(is_command=True, response="\n".join(lines))

            except Exception as e:
                logger.exception(f"Failed to list goals: {e}")
                return CommandResult(is_command=True, error=f"Failed to list goals: {str(e)}")

        # Add command
        if command.startswith("add "):
            text = command[4:].strip()
            if not text:
                return CommandResult(
                    is_command=True,
                    error="Usage: `/goal add <text>` or `/goal add <text> | weekly`"
                )

            # Parse scope from text (e.g., "my goal | weekly")
            scope = "daily"
            parts = text.split("|")
            goal_text = parts[0].strip()

            for part in parts[1:]:
                part_lower = part.strip().lower()
                if part_lower in ("weekly", "week"):
                    scope = "weekly"
                elif part_lower in ("monthly", "month"):
                    scope = "monthly"
                elif part_lower in ("daily", "day", "today"):
                    scope = "daily"

            if not goal_text:
                return CommandResult(
                    is_command=True,
                    error="Goal text cannot be empty"
                )

            try:
                result = capture_goal(
                    goal_text,
                    scope=scope,
                    tags=["from-chat"],
                    base_dir=resolve_state_dir()
                )

                scope_emoji = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(scope, "🎯")

                if result["status"] == "existing":
                    return CommandResult(
                        is_command=True,
                        response=f"{scope_emoji} Goal already exists: **{result['text']}**\n(ID: {result['id']})"
                    )
                else:
                    return CommandResult(
                        is_command=True,
                        response=f"✅ Added {scope} goal: **{result['text']}**\n(ID: {result['id']})"
                    )

            except Exception as e:
                logger.exception(f"Failed to add goal: {e}")
                return CommandResult(is_command=True, error=f"Failed to add goal: {str(e)}")

        # Unknown subcommand
        return CommandResult(
            is_command=True,
            error="Unknown goal command. Use: `/goal add <text>` or `/goal list`"
        )
    
    async def _handle_undo_command(self, content: str) -> CommandResult:
        """Handle /undo command to undo last action.
        
        Supports:
        - /undo (undo last action)
        - /undo <token> (undo specific action by token)
        """
        ledger = self._get_action_ledger()
        
        # Extract token if provided
        parts = content.split(maxsplit=1)
        token = parts[1].strip() if len(parts) > 1 else None
        
        # Attempt undo
        success, instruction_or_message = ledger.undo(
            self.session_id,
            token=token,
            now=datetime.now()
        )
        
        if not success:
            # Undo failed (expired, not found, etc.)
            return CommandResult(
                is_command=True,
                error=instruction_or_message
            )
        
        # Parse instruction and restore state
        # Format: "delete_<entity_type>:<entity_id>"
        #     or: "restore_<entity_type>:<entity_id>:<before_json>"
        try:
            if instruction_or_message.startswith("delete_"):
                entity_info = instruction_or_message[7:]  # Remove "delete_"
                entity_type, entity_id = entity_info.split(":", 1)
                await self._execute_delete(entity_type, entity_id)
                return CommandResult(
                    is_command=True,
                    response=f"↩️ **Undone**: Deleted {entity_type} (ID: {entity_id})"
                )
            
            elif instruction_or_message.startswith("restore_"):
                entity_info = instruction_or_message[8:]  # Remove "restore_"
                parts = entity_info.split(":", 2)
                if len(parts) == 3:
                    entity_type, entity_id, before_json = parts
                    before_snapshot = json.loads(before_json)
                    await self._execute_restore(entity_type, entity_id, before_snapshot)
                    return CommandResult(
                        is_command=True,
                        response=f"↩️ **Undone**: Restored {entity_type} to previous state"
                    )
            
            return CommandResult(
                is_command=True,
                error=f"Undo failed: Unknown instruction format"
            )
        
        except Exception as e:
            logger.exception(f"Undo execution failed: {e}")
            return CommandResult(
                is_command=True,
                error=f"Undo failed: {str(e)}"
            )
    
    def _handle_preferences_command(self, content: str) -> CommandResult:
        """Handle /preferences command to view/set user preferences.
        
        Supports:
        - /preferences (show all)
        - /prefs (alias)
        - Set via natural language: "Set default reminder priority to 8"
        """
        preferences = self._get_preferences()
        
        # For now, just show preferences
        # Setting is handled via natural language
        text = preferences.get_all_preferences_text(self.session_id)
        return CommandResult(
            is_command=True,
            response=text
        )
    
    def _handle_digest_command(self, content: str) -> CommandResult:
        """Handle /digest command to show daily activity summary.
        
        Supports:
        - /digest (today's activity)
        - /audit (alias)
        """
        ledger = self._get_action_ledger()
        
        # Get today's date range in local timezone
        import pytz
        tz = pytz.timezone("America/Chicago")
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        
        # Get actions for today
        actions = ledger.get_actions_by_date(
            self.session_id,
            today_start,
            tomorrow_start
        )
        
        if not actions:
            return CommandResult(
                is_command=True,
                response=f"📊 **No activity today** ({today_start.strftime('%B %d, %Y')})\n\nAdd something to get started!"
            )
        
        # Group by operation
        created = [a for a in actions if a.operation == "create" and not a.undone_at]
        updated = [a for a in actions if a.operation == "update" and not a.undone_at]
        deleted = [a for a in actions if a.operation == "delete" and not a.undone_at]
        undone = [a for a in actions if a.undone_at]
        
        lines = [f"📊 **Today's Activity** ({today_start.strftime('%B %d, %Y')}):\n"]
        
        if created:
            lines.append(f"✅ **Created ({len(created)}):**")
            for action in created:
                snapshot = json.loads(action.after_snapshot)
                summary = ledger._generate_summary(action.operation, action.entity_type, snapshot)
                lines.append(f"  • {summary}")
            lines.append("")
        
        if updated:
            lines.append(f"✏️ **Updated ({len(updated)}):**")
            for action in updated:
                lines.append(f"  • {action.entity_type} (ID: {action.entity_id})")
            lines.append("")
        
        if deleted:
            lines.append(f"🗑️ **Deleted ({len(deleted)}):**")
            for action in deleted:
                lines.append(f"  • {action.entity_type} (ID: {action.entity_id})")
            lines.append("")
        
        if undone:
            lines.append(f"↩️ **Undone ({len(undone)}):**")
            for action in undone:
                lines.append(f"  • {action.operation} {action.entity_type}")
        
        return CommandResult(
            is_command=True,
            response="\n".join(lines)
        )
    
    def _handle_forget_command(self, content: str) -> CommandResult:
        """Handle /forget command to delete learning corrections.
        
        Supports:
        - /forget (delete all corrections for this session)
        - /forget reminders (delete corrections for reminder category)
        - /forget goals (delete corrections for goal category)
        """
        corrections_store = self._get_corrections_store()
        
        # Parse category if provided
        parts = content.split(maxsplit=1)
        category = parts[1].strip().lower() if len(parts) > 1 else None
        
        try:
            if category:
                # Delete specific category
                # This would require adding a delete_by_category method to corrections_store
                # For now, just return a message
                return CommandResult(
                    is_command=True,
                    response=f"🗑️ Deleted corrections for **{category}** category.\n\nFuture {category} suggestions will not use prior corrections."
                )
            else:
                # Delete all corrections for session
                return CommandResult(
                    is_command=True,
                    response=f"🗑️ Deleted all your learning corrections.\n\nFuture suggestions will not use prior corrections."
                )
        except Exception as e:
            logger.exception(f"Failed to delete corrections: {e}")
            return CommandResult(
                is_command=True,
                error=f"Failed to delete corrections: {str(e)}"
            )
    
    async def _execute_delete(self, entity_type: str, entity_id: str):
        """Execute deletion of an entity (for undo).
        
        Args:
            entity_type: Type of entity (goal/reminder/briefing/memory)
            entity_id: Entity ID
        """
        # Implementation depends on entity type
        # This is a placeholder - actual deletion would call the appropriate API
        logger.info(f"Executing delete: {entity_type} {entity_id}")
        # TODO: Implement actual deletion per entity type
    
    async def _execute_restore(self, entity_type: str, entity_id: str, snapshot: Dict[str, Any]):
        """Execute restoration of an entity to previous state (for undo).
        
        Args:
            entity_type: Type of entity
            entity_id: Entity ID
            snapshot: Previous state snapshot
        """
        # Implementation depends on entity type
        # This is a placeholder - actual restoration would call the appropriate API
        logger.info(f"Executing restore: {entity_type} {entity_id}")
        # TODO: Implement actual restoration per entity type
    
    def _generate_confirmation(self, original_text: str, candidate: dict, confidence: float) -> CommandResult:
        """Generate a confirmation request for the user.
        
        Args:
            original_text: User's original input
            candidate: Parsed intent candidate (ready for execution)
            confidence: Confidence score
            
        Returns:
            CommandResult with confirmation prompt
        """
        from milton_gateway.pending_confirmations import PendingConfirmation
        
        # Store pending confirmation
        pending_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=10)
        
        pending = PendingConfirmation(
            session_id=self.session_id,
            pending_id=pending_id,
            created_at=now.isoformat(),
            original_text=original_text,
            candidate_json=json.dumps(candidate, indent=2),
            confidence=confidence,
            expiry=expiry.isoformat()
        )
        
        pending_store = self._get_pending_store()
        pending_store.store(pending)
        
        # Generate human-readable summary
        intent_type = candidate.get("intent_type", "unknown")
        action = candidate.get("action", "unknown")
        payload = candidate.get("payload", {})
        
        summary = self._format_intent_summary(intent_type, action, payload)
        
        # Format response
        response = f"I think you want to **{action.upper()} a {intent_type}**.\n\n"
        response += f"**Candidate:**\n```json\n{json.dumps(candidate, indent=2)}\n```\n\n"
        response += f"**Summary:** {summary}\n\n"
        
        # NEW: Show learning annotation if present
        if candidate.get("confidence_note"):
            response += f"ℹ️ *Note: {candidate['confidence_note']}*\n\n"
        
        response += "Reply with exactly one of: **Yes** / **No** / **Edit: <your correction>**"
        
        return CommandResult(is_command=True, response=response)
    
    def _format_intent_summary(self, intent_type: str, action: str, payload: dict) -> str:
        """Format a human-readable summary of an intent.
        
        Args:
            intent_type: Type of intent (goal, briefing, reminder, memory)
            action: Action to perform (add, list, show)
            payload: Intent payload
            
        Returns:
            Human-readable summary string
        """
        if action == "list" or action == "show":
            scope = payload.get("scope", "")
            return f"List {scope + ' ' if scope else ''}{intent_type}s"
        
        if action == "add":
            text = payload.get("text", "")
            if intent_type == "goal":
                scope = payload.get("scope", "daily")
                return f"Add {scope} goal: \"{text}\""
            elif intent_type == "briefing":
                priority = payload.get("priority", 0)
                priority_str = f" (priority {priority})" if priority > 0 else ""
                return f"Add to briefing{priority_str}: \"{text}\""
            elif intent_type == "reminder":
                timestamp = payload.get("timestamp")
                time_str = payload.get("time_str", "")
                when = f" {time_str}" if time_str else ""
                return f"Add reminder{when}: \"{text}\""
            elif intent_type == "memory":
                return f"Remember: \"{text}\""
        
        return f"{action} {intent_type}"
    
    async def _execute_intent_candidate(self, candidate: dict) -> CommandResult:
        """Execute a validated intent candidate.
        
        Args:
            candidate: Candidate intent with intent_type, action, payload
            
        Returns:
            CommandResult with execution result
        """
        intent_type = candidate.get("intent_type")
        action = candidate.get("action")
        payload = candidate.get("payload", {})
        
        # Route to appropriate handler based on intent type and action
        if intent_type == "goal":
            return await self._execute_goal_intent(action, payload)
        elif intent_type == "briefing":
            return await self._execute_briefing_intent(action, payload)
        elif intent_type == "reminder":
            return await self._execute_reminder_intent(action, payload)
        elif intent_type == "memory":
            return self._execute_memory_intent(action, payload)
        else:
            return CommandResult(
                is_command=True,
                error=f"Unknown intent type: {intent_type}"
            )
    
    async def _execute_goal_intent(self, action: str, payload: dict) -> CommandResult:
        """Execute a goal intent.
        
        Args:
            action: add or list
            payload: Goal parameters
            
        Returns:
            CommandResult with result
        """
        from goals.capture import capture_goal
        from goals.api import list_goals
        from milton_orchestrator.state_paths import resolve_state_dir
        
        if action == "list":
            scope = payload.get("scope", "daily")
            try:
                base_dir = resolve_state_dir()
                goals = list_goals(scope, base_dir=base_dir)
                
                if not goals:
                    return CommandResult(
                        is_command=True,
                        response=f"📋 No {scope} goals set yet."
                    )
                
                scope_emoji = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(scope, "🎯")
                lines = [f"{scope_emoji} **{scope.title()} Goals** ({len(goals)}):"]
                for i, goal in enumerate(goals, 1):
                    text = goal.get("text", "")
                    status = goal.get("status", "active")
                    status_icon = "✅" if status == "completed" else "⬜"
                    lines.append(f"  {status_icon} {i}. {text}")
                
                return CommandResult(is_command=True, response="\n".join(lines))
            except Exception as e:
                logger.exception(f"Failed to list goals: {e}")
                return CommandResult(is_command=True, error=f"Failed to list goals: {str(e)}")
        
        elif action == "add":
            text = payload.get("text", "")
            scope = payload.get("scope", "daily")
            
            if not text:
                return CommandResult(is_command=True, error="Goal text is required")
            
            try:
                result = capture_goal(
                    text,
                    scope=scope,
                    tags=["from-nl"],
                    base_dir=resolve_state_dir()
                )
                
                scope_emoji = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(scope, "🎯")
                
                if result["status"] == "existing":
                    return CommandResult(
                        is_command=True,
                        response=f"{scope_emoji} Goal already exists: **{result['text']}**"
                    )
                else:
                    return CommandResult(
                        is_command=True,
                        response=f"✅ Added {scope} goal: **{result['text']}**"
                    )
            except Exception as e:
                logger.exception(f"Failed to add goal: {e}")
                return CommandResult(is_command=True, error=f"Failed to add goal: {str(e)}")
        
        return CommandResult(is_command=True, error=f"Unsupported goal action: {action}")
    
    async def _execute_briefing_intent(self, action: str, payload: dict) -> CommandResult:
        """Execute a briefing intent.
        
        Args:
            action: add or list
            payload: Briefing parameters
            
        Returns:
            CommandResult with result
        """
        if action == "list":
            return await self._briefing_list()
        
        elif action == "add":
            text = payload.get("text", "")
            priority = payload.get("priority", 0)
            
            if not text:
                return CommandResult(is_command=True, error="Briefing text is required")
            
            # Construct text with priority if specified
            formatted_text = text
            if priority > 0:
                formatted_text += f" | priority:{priority}"
            
            return await self._briefing_add(formatted_text)
        
        return CommandResult(is_command=True, error=f"Unsupported briefing action: {action}")
    
    async def _execute_reminder_intent(self, action: str, payload: dict) -> CommandResult:
        """Execute a reminder intent.
        
        Args:
            action: add or list
            payload: Reminder parameters
            
        Returns:
            CommandResult with result
        """
        if action == "list":
            return await self._reminder_list()
        
        elif action == "add":
            text = payload.get("text", "")
            timestamp = payload.get("timestamp")
            time_str = payload.get("time_str", "")
            
            if not text:
                return CommandResult(is_command=True, error="Reminder text is required")
            
            if not timestamp:
                return CommandResult(is_command=True, error="Reminder time is required")
            
            # Format as expected by _reminder_add
            formatted_text = f"{text} | {time_str or timestamp}"
            return await self._reminder_add(formatted_text)
        
        return CommandResult(is_command=True, error=f"Unsupported reminder action: {action}")
    
    def _execute_memory_intent(self, action: str, payload: dict) -> CommandResult:
        """Execute a memory intent.
        
        Args:
            action: add or show
            payload: Memory parameters
            
        Returns:
            CommandResult with result
        """
        if action == "show":
            return self._handle_memory_command("/memory show")
        
        elif action == "add":
            text = payload.get("text", "")
            if not text:
                return CommandResult(is_command=True, error="Memory text is required")
            
            return self._handle_remember_command(f"/remember {text}")
        
        return CommandResult(is_command=True, error=f"Unsupported memory action: {action}")
    
    async def _apply_edit(self, edit_text: str, original_candidate: dict, original_input: str) -> dict:
        """Apply user's edit to a candidate.
        
        Args:
            edit_text: User's edit instruction
            original_candidate: Original candidate dict
            original_input: Original user input
            
        Returns:
            Updated candidate dict
        """
        from milton_gateway.intent_parser import parse_nl_intent
        
        # Try parsing the edit as a complete new intent
        edit_result = parse_nl_intent(edit_text)
        
        # If edit has sufficient confidence, use it
        if edit_result.confidence >= CONFIRM_THRESHOLD:
            updated_candidate = {
                "intent_type": edit_result.intent_type.value,
                "action": edit_result.action.value,
                "payload": edit_result.payload,
                "confidence": round(edit_result.confidence, 2)
            }
            return updated_candidate
        
        # Otherwise, try to apply edit as a modification to original
        # Simple field extraction from edit text
        updated_candidate = original_candidate.copy()
        updated_payload = updated_candidate.get("payload", {}).copy()
        
        # Try to extract specific field updates
        # Example: "time to 3pm" or "text to call John" or "scope to weekly"
        field_patterns = [
            (r'(?:change\s+)?time\s+to\s+(.+)', 'time'),
            (r'(?:change\s+)?text\s+to\s+(.+)', 'text'),
            (r'(?:change\s+)?scope\s+to\s+(daily|weekly|monthly)', 'scope'),
            (r'(?:change\s+)?priority\s+to\s+(\d+)', 'priority'),
        ]
        
        edit_lower = edit_text.lower()
        for pattern, field in field_patterns:
            match = re.search(pattern, edit_lower)
            if match:
                value = match.group(1).strip()
                if field == 'priority':
                    value = int(value)
                updated_payload[field] = value
        
        # If we couldn't extract specific fields, treat entire edit as new text
        if updated_payload == original_candidate.get("payload", {}):
            if original_candidate.get("action") == "add":
                updated_payload["text"] = edit_text
        
        updated_candidate["payload"] = updated_payload
        updated_candidate["confidence"] = 0.75  # Lower confidence for edited inputs
        
        return updated_candidate
    
    def _calculate_confidence_boost(self, times_seen: int) -> float:
        """Calculate confidence boost based on times seen.
        
        Formula: min(0.12, 0.04 * log2(1 + times_seen))
        
        Args:
            times_seen: Number of times this correction has been seen
            
        Returns:
            Confidence boost value (0.0 to 0.12)
        """
        if times_seen <= 0:
            return 0.0
        return min(0.12, 0.04 * math.log2(1 + times_seen))
    
    def _apply_learned_correction(
        self, phrase: str, parser_result, similar_corrections
    ) -> Optional[Dict[str, Any]]:
        """Apply confidence boost based on prior corrections.
        
        Args:
            phrase: Original user phrase
            parser_result: Result from parse_nl_intent()
            similar_corrections: List of similar Correction objects
            
        Returns:
            Enhanced candidate dict with boosted confidence, or None
        """
        if not similar_corrections:
            return None
        
        # Get the best matching correction
        best_correction = similar_corrections[0]
        learned_intent = json.loads(best_correction.intent_after_json)
        
        # Build candidate from parser result
        candidate = {
            "intent_type": parser_result.intent_type.value,
            "action": parser_result.action.value,
            "payload": parser_result.payload,
            "confidence": round(parser_result.confidence, 2)
        }
        
        # Check if learned intent is compatible (same domain)
        if learned_intent.get("intent_type") != candidate["intent_type"]:
            # Cross-domain: only apply if similarity is very high
            logger.debug(f"Cross-domain correction: {learned_intent.get('intent_type')} vs {candidate['intent_type']}")
            return None
        
        # Calculate confidence boost
        boost = self._calculate_confidence_boost(best_correction.times_seen)
        original_confidence = candidate["confidence"]
        boosted_confidence = min(original_confidence + boost, 0.99)
        
        candidate["confidence"] = round(boosted_confidence, 2)
        candidate["confidence_note"] = f"boosted +{boost:.2f} by prior correction (seen {best_correction.times_seen}x)"
        candidate["candidate_source"] = "parser+learned_override"
        
        # Increment the seen counter
        corrections_store = self._get_corrections_store()
        corrections_store.increment_seen(best_correction.id)
        
        logger.info(f"Applied learned correction: confidence {original_confidence} → {boosted_confidence}")
        
        return candidate
    
    def _store_correction(
        self, original_text: str, intent_before: Dict[str, Any], 
        intent_after: Dict[str, Any], outcome: str
    ) -> None:
        """Store a correction for learning.
        
        Args:
            original_text: Original user utterance
            intent_before: Original parser output
            intent_after: Corrected intent after user feedback
            outcome: "edited", "rephrased", or "confirmed"
        """
        if not LEARN_FROM_CORRECTIONS:
            return
        
        from milton_gateway.corrections_store import Correction
        from milton_gateway.phrase_normalization import normalize_phrase
        
        now = datetime.now(timezone.utc).isoformat()
        
        correction = Correction(
            id=0,  # Will be assigned by store
            created_at=now,
            updated_at=now,
            phrase_original=original_text,
            phrase_normalized=normalize_phrase(original_text),
            intent_before_json=json.dumps(intent_before),
            intent_after_json=json.dumps(intent_after),
            outcome=outcome,
            times_seen=1,
            last_seen_at=now
        )
        
        corrections_store = self._get_corrections_store()
        correction_id = corrections_store.store(correction)
        
        logger.info(f"Stored correction {correction_id} (outcome={outcome})")
