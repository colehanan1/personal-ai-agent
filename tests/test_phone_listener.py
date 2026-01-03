"""
Unit tests for Milton iPhone Ask/Answer Listener.

Tests:
- Message prefix parsing (claude/cortex/frontier/status/briefing)
- Action determination logic
- Allowlist enforcement
- Audit logging
- NEXUS routing (mocked)
- Dry-run mode
"""

import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Import phone listener modules
from scripts.ask_from_phone import (
    parse_message_prefix,
    determine_action,
    is_action_allowed,
    handle_incoming_message,
    write_audit_log,
    AuditLogEntry,
    ALLOWED_ACTIONS,
)


@pytest.fixture
def temp_audit_log_dir():
    """Create temporary audit log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_parse_message_prefix_no_prefix():
    """Test message parsing with no prefix (default routing)."""
    prefix, query = parse_message_prefix("What's the weather?")

    assert prefix is None
    assert query == "What's the weather?"


def test_parse_message_prefix_claude():
    """Test parsing claude: prefix."""
    prefix, query = parse_message_prefix("claude: Explain quantum computing")

    assert prefix == "claude"
    assert query == "Explain quantum computing"


def test_parse_message_prefix_cortex():
    """Test parsing cortex: prefix."""
    prefix, query = parse_message_prefix("cortex: Analyze my research papers")

    assert prefix == "cortex"
    assert query == "Analyze my research papers"


def test_parse_message_prefix_frontier():
    """Test parsing frontier: prefix."""
    prefix, query = parse_message_prefix("frontier: Find papers on fMRI")

    assert prefix == "frontier"
    assert query == "Find papers on fMRI"


def test_parse_message_prefix_status():
    """Test parsing status: prefix."""
    prefix, query = parse_message_prefix("status:")

    assert prefix == "status"
    assert query == ""


def test_parse_message_prefix_briefing():
    """Test parsing briefing: prefix."""
    prefix, query = parse_message_prefix("briefing: Morning update")

    assert prefix == "briefing"
    assert query == "Morning update"


def test_parse_message_prefix_case_insensitive():
    """Test that prefix parsing is case-insensitive."""
    prefix1, query1 = parse_message_prefix("CORTEX: Test")
    prefix2, query2 = parse_message_prefix("CoRtEx: Test")

    assert prefix1 == "cortex"
    assert prefix2 == "cortex"
    assert query1 == "Test"
    assert query2 == "Test"


def test_determine_action_default():
    """Test action determination for default (no prefix) message."""
    action = determine_action(None, "What's the weather?")

    assert action == "ask_question"


def test_determine_action_status():
    """Test action determination for status: prefix."""
    action = determine_action("status", "")

    assert action == "get_status"


def test_determine_action_briefing():
    """Test action determination for briefing: prefix."""
    action = determine_action("briefing", "")

    assert action == "get_briefing"


def test_determine_action_cortex_question():
    """Test cortex: prefix without job keywords (ask_question)."""
    action = determine_action("cortex", "What is Python?")

    assert action == "ask_question"


def test_determine_action_cortex_job():
    """Test cortex: prefix with job keywords (enqueue_job)."""
    # Should detect job submission keywords
    action1 = determine_action("cortex", "Analyze my papers tonight")
    action2 = determine_action("cortex", "Research this overnight")
    action3 = determine_action("cortex", "Discover new papers")

    assert action1 == "enqueue_job"
    assert action2 == "enqueue_job"
    assert action3 == "enqueue_job"


def test_is_action_allowed_valid():
    """Test allowlist check for valid actions."""
    assert is_action_allowed("ask_question") is True
    assert is_action_allowed("get_status") is True
    assert is_action_allowed("get_briefing") is True
    assert is_action_allowed("enqueue_job") is True


def test_is_action_allowed_invalid():
    """Test allowlist check for invalid actions."""
    assert is_action_allowed("execute_shell") is False
    assert is_action_allowed("rm_rf") is False
    assert is_action_allowed("invalid_action") is False


def test_audit_log_entry_to_log_line():
    """Test AuditLogEntry serialization to JSONL."""
    entry = AuditLogEntry(
        timestamp="2026-01-02T14:30:25.123456+00:00",
        source="phone_listener",
        action="ask_question",
        message="What's the weather?",
        parsed_prefix=None,
        parsed_query="What's the weather?",
        allowed=True,
        task_id="phone_20260102_143025",
        result_summary="Success: 245 chars",
        error=None
    )

    log_line = entry.to_log_line()

    # Should be valid JSON
    parsed = json.loads(log_line)

    assert parsed["action"] == "ask_question"
    assert parsed["allowed"] is True
    assert parsed["task_id"] == "phone_20260102_143025"
    assert parsed["source"] == "phone_listener"


def test_write_audit_log(temp_audit_log_dir):
    """Test audit log writing to file."""
    with patch("scripts.ask_from_phone.AUDIT_LOG_DIR", temp_audit_log_dir):
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="phone_listener",
            action="ask_question",
            message="Test message",
            parsed_prefix=None,
            parsed_query="Test message",
            allowed=True,
            task_id="test_123",
            result_summary="Success",
            error=None
        )

        write_audit_log(entry)

        # Check log file was created
        log_files = list(temp_audit_log_dir.glob("audit_*.jsonl"))
        assert len(log_files) == 1

        # Verify content
        with log_files[0].open() as f:
            content = f.read()
            parsed = json.loads(content.strip())

        assert parsed["action"] == "ask_question"
        assert parsed["task_id"] == "test_123"


def test_handle_incoming_message_allowed_action():
    """Test handling allowed action with mocked NEXUS."""
    with patch("scripts.ask_from_phone.route_to_nexus") as mock_route:
        with patch("scripts.ask_from_phone.write_audit_log") as mock_audit:
            mock_route.return_value = {
                "answer": "The weather is sunny",
                "task_id": "phone_test_123",
                "agent": "nexus",
                "success": True
            }

            response = handle_incoming_message("What's the weather?")

            # Should call NEXUS routing
            mock_route.assert_called_once()

            # Should write audit log
            mock_audit.assert_called_once()
            audit_entry = mock_audit.call_args[0][0]
            assert audit_entry.allowed is True
            assert audit_entry.action == "ask_question"

            # Should format response correctly
            assert "Q: What's the weather?" in response
            assert "The weather is sunny" in response


def test_handle_incoming_message_denied_action():
    """Test handling denied action (not on allowlist)."""
    with patch("scripts.ask_from_phone.ALLOWED_ACTIONS", {}):  # Empty allowlist
        with patch("scripts.ask_from_phone.write_audit_log") as mock_audit:
            response = handle_incoming_message("What's the weather?")

            # Should write audit log with allowed=False
            mock_audit.assert_called_once()
            audit_entry = mock_audit.call_args[0][0]
            assert audit_entry.allowed is False
            assert audit_entry.error == "Allowlist violation"

            # Should return denial message
            assert "not permitted" in response


def test_handle_incoming_message_with_prefix():
    """Test handling message with cortex: prefix (non-job question)."""
    with patch("scripts.ask_from_phone.execute_allowed_action") as mock_execute:
        with patch("scripts.ask_from_phone.write_audit_log"):
            mock_execute.return_value = {
                "answer": "Python is a programming language",
                "task_id": "phone_cortex_123",
                "agent": "nexus",
                "success": True
            }

            # Use message without job keywords
            response = handle_incoming_message("cortex: What is Python?")

            # Should call execute_allowed_action with cortex prefix
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[0][0] == "ask_question"  # action
            assert call_args[0][1] == "What is Python?"  # query
            assert call_args[0][2] == "cortex"  # prefix


def test_handle_incoming_message_status():
    """Test handling status: prefix."""
    with patch("scripts.ask_from_phone.route_to_nexus") as mock_route:
        with patch("scripts.ask_from_phone.write_audit_log"):
            mock_route.return_value = {
                "answer": "System status: All good",
                "task_id": "phone_status_123",
                "agent": "nexus",
                "success": True
            }

            response = handle_incoming_message("status:")

            # Should route through NEXUS with status query
            mock_route.assert_called_once()
            call_args = mock_route.call_args
            assert "Milton's current status" in call_args[0][0]


def test_handle_incoming_message_enqueue_job():
    """Test handling job enqueue (write operation)."""
    with patch("scripts.ask_from_phone.execute_allowed_action") as mock_execute:
        with patch("scripts.ask_from_phone.write_audit_log"):
            mock_execute.return_value = {
                "answer": "Job enqueued successfully. Job ID: job-20260102-001",
                "task_id": "job-20260102-001",
                "agent": "job_queue",
                "success": True
            }

            response = handle_incoming_message("cortex: Analyze my papers tonight")

            # Should call execute_allowed_action with enqueue_job
            mock_execute.assert_called_once()
            assert "enqueue_job" in str(mock_execute.call_args)


def test_handle_incoming_message_nexus_error():
    """Test handling NEXUS routing errors."""
    with patch("scripts.ask_from_phone.route_to_nexus") as mock_route:
        with patch("scripts.ask_from_phone.write_audit_log") as mock_audit:
            mock_route.return_value = {
                "answer": "Error routing request: Connection failed",
                "task_id": None,
                "agent": "error",
                "success": False,
                "error": "Connection failed"
            }

            response = handle_incoming_message("What's the weather?")

            # Should write audit log with error
            mock_audit.assert_called_once()
            audit_entry = mock_audit.call_args[0][0]
            assert audit_entry.error == "Connection failed"
            assert audit_entry.result_summary == "Failed"

            # Should return error message
            assert "❌" in response
            assert "Error routing request" in response


def test_allowlist_contains_expected_actions():
    """Test that allowlist contains expected actions."""
    # Verify critical actions are in allowlist
    assert "ask_question" in ALLOWED_ACTIONS
    assert "get_status" in ALLOWED_ACTIONS
    assert "get_briefing" in ALLOWED_ACTIONS
    assert "enqueue_job" in ALLOWED_ACTIONS

    # Verify format: (description, read_only)
    action_desc, read_only = ALLOWED_ACTIONS["ask_question"]
    assert isinstance(action_desc, str)
    assert isinstance(read_only, bool)


def test_allowlist_read_only_flags():
    """Test that read-only flags are set correctly."""
    # These should be read-only
    assert ALLOWED_ACTIONS["ask_question"][1] is True
    assert ALLOWED_ACTIONS["get_status"][1] is True
    assert ALLOWED_ACTIONS["get_briefing"][1] is True

    # enqueue_job is write operation
    assert ALLOWED_ACTIONS["enqueue_job"][1] is False


def test_message_parsing_strips_whitespace():
    """Test that message parsing strips leading/trailing whitespace."""
    prefix1, query1 = parse_message_prefix("  cortex: Test  ")
    prefix2, query2 = parse_message_prefix("\n\tWhat's the weather?\n")

    assert prefix1 == "cortex"
    assert query1 == "Test"
    assert prefix2 is None
    assert query2 == "What's the weather?"


def test_audit_log_contains_all_required_fields():
    """Test that audit log entry contains all required fields."""
    entry = AuditLogEntry(
        timestamp="2026-01-02T14:30:25.123456+00:00",
        source="phone_listener",
        action="ask_question",
        message="Test",
        parsed_prefix=None,
        parsed_query="Test",
        allowed=True,
        task_id="test_123",
        result_summary="Success",
        error=None
    )

    log_dict = json.loads(entry.to_log_line())

    # Required fields
    assert "timestamp" in log_dict
    assert "source" in log_dict
    assert "action" in log_dict
    assert "message" in log_dict
    assert "parsed_prefix" in log_dict
    assert "parsed_query" in log_dict
    assert "allowed" in log_dict
    assert "task_id" in log_dict
    assert "result_summary" in log_dict
    assert "error" in log_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
