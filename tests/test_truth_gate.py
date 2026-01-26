"""Tests for the truth gate - ensuring LLM never claims execution unless DB write occurred.

This module tests Fix 2: preventing false claims of action execution.
"""

import pytest
from milton_gateway.server import _build_action_context, _inject_action_context_into_prompt


class TestActionContextBuilder:
    """Test the action context builder for truth gate."""
    
    def test_noop_action_context(self):
        """NOOP actions should show no detection and no execution."""
        plan = {
            "action": "NOOP",
            "payload": {"reason": "no_action_detected"}
        }
        
        context = _build_action_context(plan, exec_result=None)
        
        assert context["action_detected"] is False
        assert context["action_executed"] is False
        assert context["action_type"] is None
        assert context["reason"] == "no_action_detected"
        assert context["details"] == {}
    
    def test_clarify_action_context(self):
        """CLARIFY actions should show detection but no execution."""
        plan = {
            "action": "CLARIFY",
            "payload": {"question": "When would you like to be reminded?"}
        }
        
        context = _build_action_context(plan, exec_result=None)
        
        assert context["action_detected"] is True
        assert context["action_executed"] is False
        assert context["action_type"] == "CLARIFY"
        assert context["reason"] == "needs_clarification"
        assert "question" in context["details"]
    
    def test_action_detected_not_executed(self):
        """Actions detected but not executed yet should show correct status."""
        plan = {
            "action": "CREATE_REMINDER",
            "payload": {"title": "test", "when": "tomorrow", "timezone": "America/Chicago"}
        }
        
        context = _build_action_context(plan, exec_result=None)
        
        assert context["action_detected"] is True
        assert context["action_executed"] is False
        assert context["action_type"] == "CREATE_REMINDER"
        assert context["reason"] == "not_executed"
    
    def test_action_execution_failed(self):
        """Failed executions should show detected but not executed."""
        plan = {
            "action": "CREATE_REMINDER",
            "payload": {"title": "test"}
        }
        exec_result = {
            "status": "error",
            "errors": ["missing_required_field:when"]
        }
        
        context = _build_action_context(plan, exec_result)
        
        assert context["action_detected"] is True
        assert context["action_executed"] is False
        assert context["action_type"] == "CREATE_REMINDER"
        assert context["reason"] == "execution_failed"
        assert "errors" in context["details"]
    
    def test_action_executed_successfully(self):
        """Successful executions should show both detected and executed."""
        plan = {
            "action": "CREATE_REMINDER",
            "payload": {"title": "test", "when": "tomorrow", "timezone": "America/Chicago"}
        }
        exec_result = {
            "status": "ok",
            "artifacts": {"reminder_id": "abc123", "due_at": 1234567890}
        }
        
        context = _build_action_context(plan, exec_result)
        
        assert context["action_detected"] is True
        assert context["action_executed"] is True
        assert context["action_type"] == "CREATE_REMINDER"
        assert context["reason"] == "executed_ok"
        assert context["details"]["reminder_id"] == "abc123"


class TestActionContextInjection:
    """Test action context injection into system prompt."""
    
    def test_inject_noop_context(self):
        """NOOP context should inject warning about no action detected."""
        base_prompt = "You are Milton, a helpful assistant."
        
        action_context = {
            "action_detected": False,
            "action_executed": False,
            "action_type": None,
            "reason": "no_action_detected",
            "details": {},
        }
        
        result = _inject_action_context_into_prompt(base_prompt, action_context)
        
        # Should contain base prompt
        assert "You are Milton" in result
        
        # Should contain truth gate warnings
        assert "ACTION EXECUTION STATUS" in result
        assert "NO ACTION WAS DETECTED OR EXECUTED" in result
        assert "DO NOT claim or imply that any action was taken" in result
        assert "Acknowledge that NO action was executed" in result
    
    def test_inject_clarification_needed_context(self):
        """Clarification context should inject appropriate guidance."""
        base_prompt = "You are Milton, a helpful assistant."
        
        action_context = {
            "action_detected": True,
            "action_executed": False,
            "action_type": "CLARIFY",
            "reason": "needs_clarification",
            "details": {"question": "When would you like to be reminded?"},
        }
        
        result = _inject_action_context_into_prompt(base_prompt, action_context)
        
        assert "AN ACTION WAS DETECTED" in result
        assert "BUT NOT EXECUTED" in result
        assert "needs clarification" in result
        assert "NOT claim that anything was saved/created/executed" in result
    
    def test_inject_execution_failed_context(self):
        """Failed execution context should inject failure guidance."""
        base_prompt = "You are Milton, a helpful assistant."
        
        action_context = {
            "action_detected": True,
            "action_executed": False,
            "action_type": "CREATE_REMINDER",
            "reason": "execution_failed",
            "details": {"errors": ["missing_field:when"]},
        }
        
        result = _inject_action_context_into_prompt(base_prompt, action_context)
        
        assert "BUT NOT EXECUTED" in result
        assert "Execution failed" in result
        assert "Acknowledge that the action FAILED" in result
        assert "NOT claim success" in result
    
    def test_inject_success_context(self):
        """Successful execution context should inject success guidance."""
        base_prompt = "You are Milton, a helpful assistant."
        
        action_context = {
            "action_detected": True,
            "action_executed": True,
            "action_type": "CREATE_REMINDER",
            "reason": "executed_ok",
            "details": {"reminder_id": "abc123"},
        }
        
        result = _inject_action_context_into_prompt(base_prompt, action_context)
        
        assert "ACTION WAS SUCCESSFULLY EXECUTED" in result
        assert "Confirm that the action was completed" in result
        assert "Reference specific IDs or details" in result


class TestTruthGateIntegration:
    """Integration tests for truth gate behavior."""
    
    def test_set_reminder_before_fix1_should_be_noop(self):
        """Before Fix 1, 'set a reminder' should result in NOOP."""
        # This test validates the original problem - before Fix 1,
        # "set a reminder" would return NOOP and the LLM might hallucinate
        from milton_gateway.action_planner import extract_action_plan
        from datetime import datetime
        
        text = "Set a reminder for me to submit my expense reimbursement tomorrow at 4:30 PM"
        now_iso = datetime(2025, 1, 1, 12, 0, 0).isoformat()
        tz = "America/Chicago"
        
        plan = extract_action_plan(text, now_iso, tz)
        
        # After Fix 1, this should now be CREATE_REMINDER, not NOOP
        # But we want to test that NOOP case is handled correctly
        # So we'll manually create a NOOP plan for testing
        noop_plan = {
            "action": "NOOP",
            "payload": {"reason": "unsupported_phrasing"}
        }
        
        context = _build_action_context(noop_plan, exec_result=None)
        
        # Verify the context correctly shows no execution
        assert context["action_executed"] is False
        assert context["action_detected"] is False
        
        # Verify the injected prompt has warnings
        base_prompt = "You are a helpful assistant."
        injected_prompt = _inject_action_context_into_prompt(base_prompt, context)
        
        assert "NO ACTION WAS DETECTED OR EXECUTED" in injected_prompt
        assert "DO NOT claim or imply that any action was taken" in injected_prompt
    
    def test_successful_reminder_creation_context(self):
        """Successful reminder creation should have full execution context."""
        plan = {
            "action": "CREATE_REMINDER",
            "payload": {
                "title": "Call dentist",
                "when": "tomorrow at 9am",
                "timezone": "America/Chicago"
            }
        }
        exec_result = {
            "status": "ok",
            "artifacts": {
                "reminder_id": "reminder_20250101_120000_abc",
                "due_at": 1704117600,
                "title": "Call dentist",
            }
        }
        
        context = _build_action_context(plan, exec_result)
        
        assert context["action_executed"] is True
        assert context["action_detected"] is True
        assert context["reason"] == "executed_ok"
        assert "reminder_id" in context["details"]
        
        # Verify the prompt allows success claims
        base_prompt = "You are a helpful assistant."
        injected_prompt = _inject_action_context_into_prompt(base_prompt, context)
        
        assert "SUCCESSFULLY EXECUTED" in injected_prompt
        assert "Confirm that the action was completed" in injected_prompt


class TestNegativeCases:
    """Test negative cases - what the truth gate should prevent."""
    
    def test_noop_context_forbids_success_claim(self):
        """NOOP context should explicitly forbid claiming success."""
        action_context = {
            "action_detected": False,
            "action_executed": False,
            "action_type": None,
            "reason": "no_action_detected",
            "details": {},
        }
        
        base_prompt = "You are a helpful assistant."
        injected_prompt = _inject_action_context_into_prompt(base_prompt, action_context)
        
        # Should contain explicit prohibitions
        assert "DO NOT CLAIM" in injected_prompt.upper()
        assert "NO ACTION WAS" in injected_prompt.upper()
        assert "NOT EXECUTED" in injected_prompt.upper() or "NO ACTION" in injected_prompt.upper()
        
        # Must mention that action wasn't detected/executed
        assert ("NO ACTION WAS DETECTED" in injected_prompt.upper() or 
                "NO ACTION WAS EXECUTED" in injected_prompt.upper())
    
    def test_clarify_context_forbids_success_claim(self):
        """Clarification context should forbid claiming execution."""
        action_context = {
            "action_detected": True,
            "action_executed": False,
            "action_type": "CLARIFY",
            "reason": "needs_clarification",
            "details": {"question": "When?"},
        }
        
        base_prompt = "You are a helpful assistant."
        injected_prompt = _inject_action_context_into_prompt(base_prompt, action_context)
        
        # Should forbid success claims
        assert "NOT claim that anything was saved/created/executed" in injected_prompt
        assert "NOT EXECUTED" in injected_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
