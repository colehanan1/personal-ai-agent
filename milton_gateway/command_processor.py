"""Command processor for Milton Gateway.

Handles special slash commands that trigger API calls to Milton services.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of processing a command."""

    is_command: bool
    response: Optional[str] = None
    error: Optional[str] = None


class CommandProcessor:
    """Process slash commands and call Milton API."""

    def __init__(self, milton_api_base_url: str = "http://localhost:8001", state_dir: Optional[Path] = None):
        """Initialize command processor.

        Args:
            milton_api_base_url: Base URL for Milton API (default: http://localhost:8001)
            state_dir: Optional state directory path (for testing)
        """
        self.milton_api_base_url = milton_api_base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=10.0)
        self.state_dir = state_dir
        
        # Initialize chat memory store (lazy loaded)
        self._memory_store = None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        if self._memory_store:
            self._memory_store.close()
    
    def _get_memory_store(self):
        """Get or initialize the chat memory store."""
        if self._memory_store is None:
            from storage.chat_memory import ChatMemoryStore
            state_dir = os.getenv("STATE_DIR") or os.getenv("MILTON_STATE_DIR") or Path.home() / ".local" / "state" / "milton"
            state_dir = Path(state_dir)
            db_path = state_dir / "chat_memory.sqlite3"
            self._memory_store = ChatMemoryStore(db_path)
            logger.info(f"Initialized chat memory store at {db_path}")
        return self._memory_store

    async def process_message(self, content: str) -> CommandResult:
        """Process a user message and handle any commands.

        Args:
            content: The user's message

        Returns:
            CommandResult indicating if command was processed
        """
        content = content.strip()

        # Check for /briefing command
        if content.startswith("/briefing "):
            return await self._handle_briefing_command(content)

        # Check for /reminder command
        if content.startswith("/reminder "):
            return await self._handle_reminder_command(content)
        
        # Check for /remember command
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

        # Not a command
        return CommandResult(is_command=False)

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
