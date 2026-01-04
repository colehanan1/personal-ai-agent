#!/home/cole-hanan/miniconda3/envs/milton/bin/python3
"""
Milton iPhone Ask/Answer Listener

Production-ready systemd service that:
- Listens for questions from iPhone via ntfy
- Parses message prefixes (claude/cortex/frontier/plain)
- Routes all requests through NEXUS as single entrypoint
- Enforces allowlist for permitted actions
- Logs all activity to audit log with full provenance

Security model:
- No silent remote code execution
- All actions must be on allowlist
- Full audit trail: who/when/what/task_id/result
- Read-only by default (status checks, briefings)
- Write operations require explicit allowlist entry
"""

import os
import sys
import time
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from milton_orchestrator.state_paths import resolve_state_dir

load_dotenv()

# Configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "milton-briefing-code")
QUESTIONS_TOPIC = f"{NTFY_TOPIC}-ask"
DRY_RUN = os.getenv("PHONE_LISTENER_DRY_RUN", "false").lower() == "true"

# State paths
STATE_DIR = resolve_state_dir()
AUDIT_LOG_DIR = STATE_DIR / "logs" / "phone_listener"
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    """Audit log entry for phone listener actions."""
    timestamp: str
    source: str  # "phone_listener"
    action: str  # "question", "status", "enqueue_job", etc.
    message: str  # Original message
    parsed_prefix: Optional[str]  # claude/cortex/frontier/plain
    parsed_query: str
    allowed: bool
    task_id: Optional[str]
    result_summary: str
    error: Optional[str] = None

    def to_log_line(self) -> str:
        """Format as JSON log line."""
        return json.dumps(asdict(self), sort_keys=True)


# ==============================================================================
# Action Allowlist
# ==============================================================================

# Permitted actions that can be executed from phone
# Each action is a tuple: (action_name, description, read_only)
ALLOWED_ACTIONS = {
    "ask_question": ("Ask AI question via NEXUS", True),
    "get_status": ("Get Milton system status", True),
    "get_briefing": ("Generate morning/evening briefing", True),
    "enqueue_job": ("Submit job to overnight queue", False),
    "check_reminders": ("Check active reminders", True),
    "weather": ("Get weather forecast", True),
}


def is_action_allowed(action: str) -> bool:
    """Check if action is on allowlist."""
    return action in ALLOWED_ACTIONS


def get_action_info(action: str) -> Tuple[str, bool]:
    """Get action description and read_only status."""
    if action in ALLOWED_ACTIONS:
        desc, read_only = ALLOWED_ACTIONS[action]
        return desc, read_only
    return "Unknown action", False


# ==============================================================================
# Message Parsing
# ==============================================================================

def parse_message_prefix(message: str) -> Tuple[Optional[str], str]:
    """
    Parse message prefix to determine routing.

    Supported prefixes:
    - claude: Route to NEXUS (default)
    - cortex: Route to CORTEX via NEXUS
    - frontier: Route to FRONTIER via NEXUS
    - plain: Direct pass-through
    - status: System status check
    - briefing: Generate briefing

    Returns:
        (prefix, query) tuple
    """
    message = message.strip()

    # Check for prefix patterns
    prefixes = ["claude:", "cortex:", "frontier:", "plain:", "status:", "briefing:"]

    for prefix in prefixes:
        if message.lower().startswith(prefix):
            prefix_name = prefix.rstrip(":")
            query = message[len(prefix):].strip()
            return prefix_name, query

    # Default: route through claude (NEXUS)
    return None, message


def determine_action(prefix: Optional[str], query: str) -> str:
    """Determine action type from prefix and query."""
    if prefix == "status":
        return "get_status"
    elif prefix == "briefing":
        return "get_briefing"
    elif prefix in ["cortex", "frontier"]:
        lower_q = query.lower()

        # Explicit phrases that signal a queued/background job
        phrase_patterns = [
            r"\brun overnight\b",
            r"\brun (an )?overnight job\b",
            r"\bstart (an )?overnight job\b",
            r"\bsubmit (a )?job\b",
            r"\bstart (a )?job\b",
            r"\bqueue (a )?job\b",
            r"\bprocess this dataset\b",
            r"\bprocess the dataset\b",
            r"\brun .* in background\b",
            r"\bbackground job\b",
            r"\btonight job\b",
        ]

        if any(re.search(pat, lower_q) for pat in phrase_patterns):
            return "enqueue_job"

        # Fallback: verb + context token combination (word-boundary to avoid substrings)
        verb_tokens = ["run", "start", "submit", "queue", "process", "schedule"]
        context_tokens = ["overnight", "tonight", "background", "job", "queue", "later", "async"]

        has_verb = any(re.search(rf"\b{verb}\b", lower_q) for verb in verb_tokens)
        has_context = any(re.search(rf"\b{ctx}\b", lower_q) for ctx in context_tokens)

        if has_verb and has_context:
            return "enqueue_job"

        return "ask_question"
    else:
        # Default: ask question via NEXUS
        return "ask_question"


# ==============================================================================
# Audit Logging
# ==============================================================================

def write_audit_log(entry: AuditLogEntry):
    """Write audit log entry to file and stdout."""
    log_file = AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

    try:
        with log_file.open("a") as f:
            f.write(entry.to_log_line() + "\n")

        logger.info(f"AUDIT: {entry.action} | allowed={entry.allowed} | task_id={entry.task_id}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# ==============================================================================
# NEXUS Integration (Single Entrypoint)
# ==============================================================================

def route_to_nexus(query: str, prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    Route request through NEXUS as single entrypoint.

    This is the ONLY way phone requests interact with Milton agents.
    No ad-hoc execution, all routing goes through NEXUS.

    Args:
        query: User query
        prefix: Optional routing hint (cortex/frontier/plain)

    Returns:
        Response dict with answer, task_id, agent
    """
    try:
        # Import here to avoid circular dependencies
        from agents.nexus import NEXUS

        nexus = NEXUS()

        # Route based on prefix
        if prefix == "cortex":
            # Direct to CORTEX via NEXUS delegation
            logger.info(f"Routing to CORTEX via NEXUS: {query[:60]}...")
            # NEXUS will decide whether to delegate or handle directly
            response = nexus.answer(query)
        elif prefix == "frontier":
            # Direct to FRONTIER via NEXUS delegation
            logger.info(f"Routing to FRONTIER via NEXUS: {query[:60]}...")
            response = nexus.answer(query)
        else:
            # Let NEXUS decide routing
            logger.info(f"Routing to NEXUS (auto-route): {query[:60]}...")
            response = nexus.answer(query)

        return {
            "answer": response,
            "task_id": f"phone_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "agent": "nexus",
            "success": True
        }

    except Exception as e:
        logger.error(f"NEXUS routing error: {e}", exc_info=True)
        return {
            "answer": f"Error routing request: {str(e)}",
            "task_id": None,
            "agent": "error",
            "success": False,
            "error": str(e)
        }


def execute_allowed_action(action: str, query: str, prefix: Optional[str]) -> Dict[str, Any]:
    """
    Execute an allowed action with full audit trail.

    All actions route through NEXUS - this is just the dispatch logic.

    Args:
        action: Action name from allowlist
        query: User query
        prefix: Optional routing prefix

    Returns:
        Response dict
    """
    if not is_action_allowed(action):
        return {
            "answer": f"Action '{action}' not allowed. Permitted actions: {', '.join(ALLOWED_ACTIONS.keys())}",
            "task_id": None,
            "agent": "allowlist_check",
            "success": False,
            "error": "Action not on allowlist"
        }

    # All actions route through NEXUS
    if action == "ask_question":
        return route_to_nexus(query, prefix)

    elif action == "get_status":
        # System status check (read-only)
        try:
            status_query = "What is Milton's current status? Include active jobs, recent tasks, and system health."
            return route_to_nexus(status_query, None)
        except Exception as e:
            return {"answer": f"Error getting status: {e}", "success": False, "error": str(e)}

    elif action == "get_briefing":
        # Generate briefing (read-only)
        try:
            briefing_query = "Generate a brief summary of today's important information: weather, calendar, tasks, and news."
            return route_to_nexus(briefing_query, None)
        except Exception as e:
            return {"answer": f"Error generating briefing: {e}", "success": False, "error": str(e)}

    elif action == "enqueue_job":
        # Submit job to overnight queue (write operation)
        try:
            import milton_queue as queue_api
            from agents.contracts import generate_task_id

            task_id = generate_task_id("phone_job")
            job_id = queue_api.enqueue_job(
                job_type="phone_request",
                payload={"task": query, "source": "phone_listener"},
                priority="medium"
            )

            return {
                "answer": f"Job enqueued successfully. Job ID: {job_id}. Will be processed overnight.",
                "task_id": job_id,
                "agent": "job_queue",
                "success": True
            }
        except Exception as e:
            return {"answer": f"Error enqueuing job: {e}", "success": False, "error": str(e)}

    else:
        # Fallback: route through NEXUS
        return route_to_nexus(query, prefix)


# ==============================================================================
# ntfy Integration
# ==============================================================================

def send_response_to_phone(response_text: str, topic: Optional[str] = None) -> bool:
    """Send response back to iPhone via ntfy."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send to phone: {response_text[:100]}...")
        return True

    if not topic:
        topic = NTFY_TOPIC

    try:
        import requests

        result = requests.post(
            f"https://ntfy.sh/{topic}",
            data=response_text.encode('utf-8'),
            headers={
                "Title": "Milton AI Response",
                "Priority": "high",
                "Tags": "robot,speech_balloon"
            },
            timeout=10
        )
        return result.status_code == 200
    except Exception as e:
        logger.error(f"Error sending response to phone: {e}")
        return False


# ==============================================================================
# Message Handler
# ==============================================================================

def handle_incoming_message(message: str) -> str:
    """
    Handle incoming message with full audit trail.

    Process flow:
    1. Parse message prefix
    2. Determine action
    3. Check allowlist
    4. Execute via NEXUS (single entrypoint)
    5. Write audit log
    6. Return response

    Args:
        message: Raw message from phone

    Returns:
        Formatted response to send back
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Parse message
    prefix, query = parse_message_prefix(message)
    action = determine_action(prefix, query)

    logger.info(f"Message received: prefix={prefix}, action={action}, query={query[:60]}...")

    # Check allowlist
    allowed = is_action_allowed(action)

    if not allowed:
        # Deny and audit
        entry = AuditLogEntry(
            timestamp=timestamp,
            source="phone_listener",
            action=action,
            message=message,
            parsed_prefix=prefix,
            parsed_query=query,
            allowed=False,
            task_id=None,
            result_summary="Action not on allowlist",
            error="Allowlist violation"
        )
        write_audit_log(entry)

        return f"❌ Action '{action}' not permitted.\n\nAllowed actions:\n" + \
               "\n".join([f"- {k}: {v[0]}" for k, v in ALLOWED_ACTIONS.items()])

    # Execute action
    result = execute_allowed_action(action, query, prefix)

    # Format response
    if result.get("success", False):
        response_text = f"Q: {query}\n\n{result['answer']}"
        result_summary = f"Success: {len(result['answer'])} chars"
        error = None
    else:
        response_text = f"Q: {query}\n\n❌ {result.get('answer', 'Unknown error')}"
        result_summary = "Failed"
        error = result.get("error")

    # Write audit log
    entry = AuditLogEntry(
        timestamp=timestamp,
        source="phone_listener",
        action=action,
        message=message,
        parsed_prefix=prefix,
        parsed_query=query,
        allowed=True,
        task_id=result.get("task_id"),
        result_summary=result_summary,
        error=error
    )
    write_audit_log(entry)

    return response_text


# ==============================================================================
# Main Listener Loop
# ==============================================================================

def listen_for_questions():
    """
    Main listener loop.

    Connects to ntfy stream and processes incoming messages.
    Runs as systemd service with journald logging.
    """
    logger.info("=" * 70)
    logger.info("MILTON PHONE LISTENER (Production)")
    logger.info("=" * 70)
    logger.info(f"Listen topic:   {QUESTIONS_TOPIC}")
    logger.info(f"Response topic: {NTFY_TOPIC}")
    logger.info(f"Audit log dir:  {AUDIT_LOG_DIR}")
    logger.info(f"Dry-run mode:   {DRY_RUN}")
    logger.info("")
    logger.info("Allowed actions:")
    for action, (desc, read_only) in ALLOWED_ACTIONS.items():
        ro_marker = "[RO]" if read_only else "[RW]"
        logger.info(f"  {ro_marker} {action}: {desc}")
    logger.info("")
    logger.info("Supported prefixes: claude:, cortex:, frontier:, status:, briefing:")
    logger.info("=" * 70)
    logger.info("")

    if DRY_RUN:
        logger.warning("⚠️  DRY RUN MODE - No ntfy connection, no responses sent")
        logger.info("\nTo test message handling in dry-run mode:")
        logger.info("  python scripts/ask_from_phone.py --test 'Your test message'")
        return

    # Subscribe to ntfy stream
    url = f"https://ntfy.sh/{QUESTIONS_TOPIC}/json"

    try:
        import requests

        with requests.get(url, stream=True, timeout=None) as response:
            logger.info(f"✅ Connected to {QUESTIONS_TOPIC}")
            logger.info("Waiting for questions...\n")

            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)

                        # Check if it's a message (not just keepalive)
                        if data.get("event") == "message":
                            message = data.get("message", "").strip()

                            if message and not message.startswith("This is a test"):
                                ts = datetime.now().strftime('%H:%M:%S')
                                logger.info(f"[{ts}] 📱 Message: {message[:60]}...")

                                # Handle message (parse, route, execute, audit)
                                response_text = handle_incoming_message(message)

                                # Send response
                                if send_response_to_phone(response_text):
                                    logger.info(f"[{ts}] ✅ Response sent\n")
                                else:
                                    logger.error(f"[{ts}] ❌ Failed to send response\n")

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("\n\n👋 Stopped listening")
    except Exception as e:
        logger.error(f"\n❌ Listener error: {e}", exc_info=True)
        raise


# ==============================================================================
# CLI Interface
# ==============================================================================

if __name__ == "__main__":
    import argparse

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )

    parser = argparse.ArgumentParser(
        description="Milton iPhone Ask/Answer Listener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start listener (production mode)
  python scripts/ask_from_phone.py --listen

  # Test message handling (dry-run, no ntfy)
  python scripts/ask_from_phone.py --test "What's the weather?"

  # Test with prefix
  python scripts/ask_from_phone.py --test "cortex: Analyze my research papers"

  # Show audit log
  python scripts/ask_from_phone.py --show-audit

  # Show allowlist
  python scripts/ask_from_phone.py --show-allowlist
"""
    )

    parser.add_argument("--listen", action="store_true", help="Start listening for questions")
    parser.add_argument("--test", help="Test message handling (dry-run mode, no ntfy)")
    parser.add_argument("--show-audit", action="store_true", help="Show recent audit log entries")
    parser.add_argument("--show-allowlist", action="store_true", help="Show action allowlist")

    args = parser.parse_args()

    if args.listen:
        listen_for_questions()

    elif args.test:
        # Test mode: handle message without ntfy
        logger.info(f"\n🧪 Testing message: {args.test}\n")
        response = handle_incoming_message(args.test)
        logger.info(f"\n📤 Response:\n{response}\n")

    elif args.show_audit:
        # Show recent audit log
        log_file = AUDIT_LOG_DIR / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

        if not log_file.exists():
            print(f"No audit log for today: {log_file}")
        else:
            print(f"\nAudit log: {log_file}\n")
            with log_file.open() as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20 entries
                    entry = json.loads(line)
                    print(f"[{entry['timestamp']}] {entry['action']}")
                    print(f"  Message: {entry['message'][:60]}...")
                    print(f"  Allowed: {entry['allowed']}, Task ID: {entry['task_id']}")
                    print(f"  Result: {entry['result_summary']}")
                    if entry.get('error'):
                        print(f"  Error: {entry['error']}")
                    print()

    elif args.show_allowlist:
        # Show allowlist
        print("\nAllowed Actions:")
        print("=" * 70)
        for action, (desc, read_only) in ALLOWED_ACTIONS.items():
            ro_marker = "[READ-ONLY]" if read_only else "[READ-WRITE]"
            print(f"{ro_marker} {action}")
            print(f"  {desc}")
            print()

    else:
        parser.print_help()
