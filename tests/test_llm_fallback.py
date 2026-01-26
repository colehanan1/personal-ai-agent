"""Tests for LLM-assisted intent classification fallback.

This module tests Fix 3: LLM fallback for when regex patterns fail.
Tests use mocked LLM responses to ensure hermetic, deterministic behavior.
"""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from milton_gateway.llm_intent_classifier import (
    should_use_fallback,
    classify_intent_with_llm,
    should_execute_classification,
    convert_classification_to_plan,
    MIN_CONFIDENCE_THRESHOLD,
    _parse_and_validate_classification,
)


class TestFallbackTriggerHeuristic:
    """Test the heuristic that determines if fallback should be used."""
    
    def test_should_trigger_on_reminder_keywords(self):
        """Fallback should trigger on reminder-related keywords."""
        phrases = [
            "Set a reminder for me to submit expense report",
            "create a reminder to call dentist",
            "add a reminder for tomorrow",
            "schedule me a reminder",
            "Can you remind me to do X",
        ]
        
        for phrase in phrases:
            assert should_use_fallback(phrase), f"Should trigger for: {phrase}"
    
    def test_should_trigger_on_goal_keywords(self):
        """Fallback should trigger on goal-related keywords."""
        phrases = [
            "set a goal to finish the project",
            "add a goal for this week",
            "my goal is to accomplish X",
        ]
        
        for phrase in phrases:
            assert should_use_fallback(phrase), f"Should trigger for: {phrase}"
    
    def test_should_trigger_on_memory_keywords(self):
        """Fallback should trigger on memory-related keywords."""
        phrases = [
            "remember that my API key is XYZ",
            "save this information",
            "store this note",
            "keep track of my WiFi password",
        ]
        
        for phrase in phrases:
            assert should_use_fallback(phrase), f"Should trigger for: {phrase}"
    
    def test_should_not_trigger_on_generic_chat(self):
        """Fallback should NOT trigger on generic chat."""
        phrases = [
            "Hello, how are you?",
            "What's the weather like?",
            "Tell me a joke",
            "Explain quantum physics",
        ]
        
        for phrase in phrases:
            assert not should_use_fallback(phrase), f"Should NOT trigger for: {phrase}"
    
    def test_should_trigger_on_imperative_verbs(self):
        """Fallback should trigger on imperative action verbs."""
        phrases = [
            "Help me track my expenses",
            "Can you create something for me",
            "Please make a note",
        ]
        
        for phrase in phrases:
            assert should_use_fallback(phrase), f"Should trigger for: {phrase}"


class TestClassificationValidation:
    """Test validation of LLM classifier output."""
    
    def test_valid_reminder_classification(self):
        """Valid reminder classification should pass validation."""
        response = json.dumps({
            "intent_type": "reminder",
            "action": "add",
            "payload": {
                "title": "submit expense report",
                "when": "tomorrow at 4:30 PM",
                "timezone": "America/Chicago"
            },
            "confidence": 0.95,
            "missing_fields": []
        })
        
        result = _parse_and_validate_classification(response)
        
        assert result is not None
        assert result["intent_type"] == "reminder"
        assert result["action"] == "add"
        assert result["confidence"] == 0.95
        assert result["missing_fields"] == []
    
    def test_valid_goal_classification(self):
        """Valid goal classification should pass validation."""
        response = json.dumps({
            "intent_type": "goal",
            "action": "add",
            "payload": {
                "title": "finish project",
                "due": "this week"
            },
            "confidence": 0.90,
            "missing_fields": []
        })
        
        result = _parse_and_validate_classification(response)
        
        assert result is not None
        assert result["intent_type"] == "goal"
    
    def test_invalid_json_rejected(self):
        """Invalid JSON should be rejected."""
        response = "This is not JSON"
        
        result = _parse_and_validate_classification(response)
        
        assert result is None
    
    def test_non_ascii_rejected(self):
        """Non-ASCII output (not JSON-encoded) should be rejected."""
        # This is raw non-ASCII text, not JSON-encoded
        response = '{"intent_type": "reminder", "action": "add", "payload": {"title": "café ☕"}, "confidence": 0.95, "missing_fields": []}'
        
        result = _parse_and_validate_classification(response)
        
        # Should fail ASCII validation
        assert result is None
    
    def test_invalid_intent_type_rejected(self):
        """Invalid intent_type should be rejected."""
        response = json.dumps({
            "intent_type": "invalid_type",
            "action": "add",
            "payload": {},
            "confidence": 0.95,
            "missing_fields": []
        })
        
        result = _parse_and_validate_classification(response)
        
        assert result is None
    
    def test_invalid_action_rejected(self):
        """Invalid action should be rejected."""
        response = json.dumps({
            "intent_type": "reminder",
            "action": "invalid_action",
            "payload": {},
            "confidence": 0.95,
            "missing_fields": []
        })
        
        result = _parse_and_validate_classification(response)
        
        assert result is None
    
    def test_confidence_out_of_range_rejected(self):
        """Confidence outside [0.0, 1.0] should be rejected."""
        response = json.dumps({
            "intent_type": "reminder",
            "action": "add",
            "payload": {},
            "confidence": 1.5,  # Invalid
            "missing_fields": []
        })
        
        result = _parse_and_validate_classification(response)
        
        assert result is None
    
    def test_markdown_code_blocks_handled(self):
        """Markdown code blocks should be stripped."""
        response = """```json
{
  "intent_type": "reminder",
  "action": "add",
  "payload": {"title": "test", "when": "tomorrow", "timezone": "America/Chicago"},
  "confidence": 0.90,
  "missing_fields": []
}
```"""
        
        result = _parse_and_validate_classification(response)
        
        assert result is not None
        assert result["intent_type"] == "reminder"


class TestSafetyGates:
    """Test safety gates that prevent unsafe execution."""
    
    def test_high_confidence_passes(self):
        """High confidence >= 0.85 should pass."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "confidence": 0.90,
            "missing_fields": []
        }
        
        assert should_execute_classification(classification)
    
    def test_low_confidence_fails(self):
        """Low confidence < 0.85 should fail."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "confidence": 0.75,  # Below threshold
            "missing_fields": []
        }
        
        assert not should_execute_classification(classification)
    
    def test_unknown_intent_fails(self):
        """Unknown intent should fail."""
        classification = {
            "intent_type": "unknown",
            "action": "add",
            "confidence": 0.95,
            "missing_fields": []
        }
        
        assert not should_execute_classification(classification)
    
    def test_noop_action_fails(self):
        """NOOP action should fail."""
        classification = {
            "intent_type": "reminder",
            "action": "noop",
            "confidence": 0.95,
            "missing_fields": []
        }
        
        assert not should_execute_classification(classification)
    
    def test_missing_fields_fails(self):
        """Missing required fields should fail."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "confidence": 0.95,
            "missing_fields": ["when"]  # Missing time
        }
        
        assert not should_execute_classification(classification)
    
    def test_all_gates_pass_succeeds(self):
        """All gates passing should succeed."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "confidence": 0.95,
            "missing_fields": []
        }
        
        assert should_execute_classification(classification)


class TestPlanConversion:
    """Test conversion from classification to action plan."""
    
    def test_reminder_conversion(self):
        """Reminder classification should convert to CREATE_REMINDER."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "payload": {
                "title": "call dentist",
                "when": "tomorrow at 9am",
            },
            "confidence": 0.95,
            "missing_fields": []
        }
        
        plan = convert_classification_to_plan(classification, "America/Chicago")
        
        assert plan["action"] == "CREATE_REMINDER"
        assert plan["payload"]["title"] == "call dentist"
        assert plan["payload"]["when"] == "tomorrow at 9am"
        assert plan["payload"]["timezone"] == "America/Chicago"
        assert plan["confidence"] == 0.95
        assert plan["source"] == "llm_fallback"
    
    def test_goal_conversion(self):
        """Goal classification should convert to CREATE_GOAL."""
        classification = {
            "intent_type": "goal",
            "action": "add",
            "payload": {
                "title": "finish project",
                "due": "this week"
            },
            "confidence": 0.90,
            "missing_fields": []
        }
        
        plan = convert_classification_to_plan(classification, "America/Chicago")
        
        assert plan["action"] == "CREATE_GOAL"
        assert plan["payload"]["title"] == "finish project"
        assert plan["source"] == "llm_fallback"
    
    def test_memory_conversion(self):
        """Memory classification should convert to CREATE_MEMORY."""
        classification = {
            "intent_type": "memory",
            "action": "add",
            "payload": {
                "key": "wifi",
                "value": "MyPassword123",
                "text": "remember my wifi is MyPassword123"
            },
            "confidence": 0.92,
            "missing_fields": []
        }
        
        plan = convert_classification_to_plan(classification, "America/Chicago")
        
        assert plan["action"] == "CREATE_MEMORY"
        assert plan["payload"]["key"] == "wifi"
        assert plan["source"] == "llm_fallback"


@pytest.mark.asyncio
class TestLLMClassifierIntegration:
    """Integration tests with mocked LLM responses."""
    
    async def test_successful_reminder_classification(self):
        """Test successful reminder classification with mocked LLM."""
        # Mock LLM response
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent_type": "reminder",
                        "action": "add",
                        "payload": {
                            "title": "submit expense report",
                            "when": "tomorrow at 4:30 PM",
                            "timezone": "America/Chicago"
                        },
                        "confidence": 0.95,
                        "missing_fields": []
                    })
                }
            }]
        }
        
        # Create mock LLM client
        mock_llm_client = AsyncMock()
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_llm_response)
        
        # Call classifier
        result = await classify_intent_with_llm(
            "Set a reminder for me to submit my expense report tomorrow at 4:30 PM",
            mock_llm_client,
            "2026-01-26T10:00:00Z",
            "America/Chicago"
        )
        
        assert result is not None
        assert result["intent_type"] == "reminder"
        assert result["action"] == "add"
        assert result["confidence"] == 0.95
        assert should_execute_classification(result)
    
    async def test_low_confidence_classification(self):
        """Test classification with low confidence (should not execute)."""
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent_type": "reminder",
                        "action": "add",
                        "payload": {
                            "title": "something",
                            "when": "unclear",
                            "timezone": "America/Chicago"
                        },
                        "confidence": 0.60,  # Below threshold
                        "missing_fields": []
                    })
                }
            }]
        }
        
        mock_llm_client = AsyncMock()
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_llm_response)
        
        result = await classify_intent_with_llm(
            "Set a reminder to do something",
            mock_llm_client,
            "2026-01-26T10:00:00Z",
            "America/Chicago"
        )
        
        assert result is not None
        assert result["confidence"] == 0.60
        assert not should_execute_classification(result)  # Safety gate
    
    async def test_missing_fields_classification(self):
        """Test classification with missing required fields."""
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "intent_type": "reminder",
                        "action": "add",
                        "payload": {
                            "title": "submit expense report"
                            # Missing "when"
                        },
                        "confidence": 0.90,
                        "missing_fields": ["when"]  # LLM detected missing field
                    })
                }
            }]
        }
        
        mock_llm_client = AsyncMock()
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_llm_response)
        
        result = await classify_intent_with_llm(
            "Set a reminder to submit my expense report",
            mock_llm_client,
            "2026-01-26T10:00:00Z",
            "America/Chicago"
        )
        
        assert result is not None
        assert "when" in result["missing_fields"]
        assert not should_execute_classification(result)  # Safety gate
    
    async def test_llm_returns_invalid_json(self):
        """Test handling of invalid JSON from LLM."""
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": "I think the user wants a reminder, but I'm not sure."
                }
            }]
        }
        
        mock_llm_client = AsyncMock()
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_llm_response)
        
        result = await classify_intent_with_llm(
            "Set a reminder...",
            mock_llm_client,
            "2026-01-26T10:00:00Z",
            "America/Chicago"
        )
        
        assert result is None  # Invalid response rejected
    
    async def test_llm_error_handling(self):
        """Test error handling when LLM call fails."""
        mock_llm_client = AsyncMock()
        mock_llm_client.chat_completion = AsyncMock(side_effect=Exception("LLM error"))
        
        result = await classify_intent_with_llm(
            "Set a reminder...",
            mock_llm_client,
            "2026-01-26T10:00:00Z",
            "America/Chicago"
        )
        
        assert result is None  # Error handled gracefully


class TestDeterministicBehavior:
    """Test that fallback behavior is deterministic and testable."""
    
    def test_heuristic_is_deterministic(self):
        """Same input should always produce same heuristic result."""
        text = "Set a reminder for me to submit expense report"
        
        results = [should_use_fallback(text) for _ in range(10)]
        
        assert all(r == results[0] for r in results), "Heuristic should be deterministic"
    
    def test_validation_is_deterministic(self):
        """Same JSON should always validate the same way."""
        json_str = json.dumps({
            "intent_type": "reminder",
            "action": "add",
            "payload": {},
            "confidence": 0.95,
            "missing_fields": []
        })
        
        results = [_parse_and_validate_classification(json_str) for _ in range(10)]
        
        assert all(r is not None for r in results), "Validation should be deterministic"
    
    def test_safety_gates_are_deterministic(self):
        """Same classification should always pass/fail gates the same way."""
        classification = {
            "intent_type": "reminder",
            "action": "add",
            "confidence": 0.75,  # Below threshold
            "missing_fields": []
        }
        
        results = [should_execute_classification(classification) for _ in range(10)]
        
        assert all(r is False for r in results), "Safety gates should be deterministic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
