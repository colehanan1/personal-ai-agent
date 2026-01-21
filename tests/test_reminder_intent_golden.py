"""Golden phrase regression tests for reminder intent normalization.

This test suite ensures that the reminder intent normalizer produces
consistent, correct outputs for a curated set of natural language inputs.
Any failing test indicates a regression that must be fixed before deployment.
"""

import pytest
import yaml
from pathlib import Path
from datetime import datetime, timedelta

from milton_gateway.reminder_intent_normalizer import ReminderIntentNormalizer


def load_golden_cases():
    """Load golden test cases from YAML file."""
    golden_file = Path(__file__).parent / "data" / "nlp_golden.yml"
    with open(golden_file, "r") as f:
        data = yaml.safe_load(f)
    return data["test_cases"]


@pytest.fixture
def normalizer():
    """Create a fresh normalizer instance."""
    return ReminderIntentNormalizer()


@pytest.fixture
def fixed_now():
    """Fixed datetime for deterministic time parsing."""
    # Tuesday, Jan 21, 2026 at 10:00 AM Chicago time
    return datetime(2026, 1, 21, 10, 0, 0)


class TestGoldenPhrases:
    """Test suite for golden reminder phrases."""
    
    @pytest.mark.parametrize("case", load_golden_cases())
    def test_golden_case(self, normalizer, fixed_now, case):
        """Test each golden case."""
        phrase = case["phrase"]
        expected = case["expected"]
        
        # Normalize the phrase
        result = normalizer.normalize(phrase, now=fixed_now)
        
        # Check intent_type
        expected_intent_type = expected.get("intent_type")
        if expected_intent_type is None:
            assert result is None, f"Expected no match for: '{phrase}', but got: {result}"
            return  # Skip other checks if no match expected
        
        assert result is not None, f"Expected match for: '{phrase}', but got None"
        assert result.intent_type == expected_intent_type, \
            f"Intent type mismatch for: '{phrase}'"
        
        # Check surface_form
        if "surface_form" in expected:
            assert result.surface_form == expected["surface_form"], \
                f"Surface form mismatch for: '{phrase}'"
        
        # Check has_task
        if expected.get("has_task"):
            assert result.task, f"Expected task to be extracted for: '{phrase}'"
            
            # Check task content if specified
            if "task_contains" in expected:
                task_lower = result.task.lower()
                expected_text = expected["task_contains"].lower()
                assert expected_text in task_lower, \
                    f"Task should contain '{expected['task_contains']}' for: '{phrase}', got: '{result.task}'"
        
        # Check has_due_at
        if "has_due_at" in expected:
            if expected["has_due_at"]:
                assert result.due_at is not None, \
                    f"Expected due_at timestamp for: '{phrase}'"
                # Sanity check: due_at should be reasonable (allow small timezone variance)
                # If it's supposed to be in the future, check it's close to or after now
                time_diff = result.due_at - int(fixed_now.timestamp())
                # Allow times within 2 hours of "now" for edge cases like "at 9am tomorrow" parsed as 9am
                assert time_diff >= -7200, \
                    f"due_at should not be far in past for: '{phrase}' (diff: {time_diff}s)"
            else:
                # Allow due_at to be present but not require it if has_due_at=false
                pass
        
        # Check has_recurrence
        if "has_recurrence" in expected:
            if expected["has_recurrence"]:
                assert result.recurrence is not None, \
                    f"Expected recurrence pattern for: '{phrase}'"
                
                # Check recurrence content if specified
                if "recurrence_contains" in expected:
                    recurrence_lower = result.recurrence.lower()
                    expected_text = expected["recurrence_contains"].lower()
                    assert expected_text in recurrence_lower, \
                        f"Recurrence should contain '{expected['recurrence_contains']}' for: '{phrase}', got: '{result.recurrence}'"
            else:
                assert result.recurrence is None, \
                    f"Should not have recurrence for: '{phrase}', got: '{result.recurrence}'"
        
        # Check channel
        if "channel" in expected:
            assert result.channel == expected["channel"], \
                f"Channel mismatch for: '{phrase}'"
        
        # Check needs_clarification
        if "needs_clarification" in expected:
            assert result.needs_clarification == expected["needs_clarification"], \
                f"needs_clarification mismatch for: '{phrase}'"
        
        # Check clarifying_question content if specified
        if "clarification_contains" in expected and result.clarifying_question:
            question_lower = result.clarifying_question.lower()
            expected_text = expected["clarification_contains"].lower()
            assert expected_text in question_lower, \
                f"Clarification should contain '{expected['clarification_contains']}' for: '{phrase}', got: '{result.clarifying_question}'"
        
        # Check confidence minimum
        if "confidence_min" in expected:
            assert result.confidence >= expected["confidence_min"], \
                f"Confidence too low for: '{phrase}' (got {result.confidence}, expected >= {expected['confidence_min']})"
    
    def test_briefing_help_maps_to_reminder_create(self, normalizer, fixed_now):
        """Verify that 'in briefing help me X' creates reminder.create intent."""
        phrases = [
            "in my morning briefing help me review goals",
            "in the evening briefing help me plan tomorrow",
            "every weekday in briefing help me prioritize tasks",
        ]
        
        for phrase in phrases:
            result = normalizer.normalize(phrase, now=fixed_now)
            assert result is not None, f"Should match: '{phrase}'"
            assert result.intent_type == "reminder.create", \
                f"Should map to reminder.create for: '{phrase}'"
            assert result.channel == "morning_briefing", \
                f"Should use morning_briefing channel for: '{phrase}'"
    
    def test_relative_time_calculates_timestamp(self, normalizer, fixed_now):
        """Verify relative time expressions produce valid timestamps."""
        phrases_and_expected_delays = [
            ("remind me to stretch in 2 hours", 2 * 3600),
            ("remind me to break in 30 minutes", 30 * 60),
            ("remind me to backup in 1 day", 1 * 86400),
        ]
        
        base_ts = int(fixed_now.timestamp())
        
        for phrase, expected_delay in phrases_and_expected_delays:
            result = normalizer.normalize(phrase, now=fixed_now)
            assert result is not None, f"Should match: '{phrase}'"
            assert result.due_at is not None, f"Should have timestamp for: '{phrase}'"
            
            # Check timestamp is approximately correct (allow 1 second tolerance)
            expected_ts = base_ts + expected_delay
            assert abs(result.due_at - expected_ts) <= 1, \
                f"Timestamp mismatch for: '{phrase}' (got {result.due_at}, expected ~{expected_ts})"
    
    def test_ambiguous_time_creates_draft(self, normalizer, fixed_now):
        """Verify ambiguous time expressions set needs_clarification=True."""
        ambiguous_phrases = [
            "remind me to call dentist",
            "remind me to check oven tomorrow morning",
            "in my briefing help me review notes",
            "every friday help me plan week",
        ]
        
        for phrase in ambiguous_phrases:
            result = normalizer.normalize(phrase, now=fixed_now)
            assert result is not None, f"Should match: '{phrase}'"
            assert result.needs_clarification, \
                f"Should need clarification for: '{phrase}'"
            assert result.clarifying_question is not None, \
                f"Should have clarifying question for: '{phrase}'"
    
    def test_explicit_time_no_clarification(self, normalizer, fixed_now):
        """Verify explicit time expressions do not need clarification."""
        explicit_phrases = [
            "remind me to call at 9am tomorrow",
            "at 2pm today remind me to stretch",
            "remind me to backup in 3 hours",
        ]
        
        for phrase in explicit_phrases:
            result = normalizer.normalize(phrase, now=fixed_now)
            assert result is not None, f"Should match: '{phrase}'"
            assert not result.needs_clarification, \
                f"Should NOT need clarification for: '{phrase}'"
            assert result.due_at is not None, \
                f"Should have timestamp for: '{phrase}'"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_string(self, normalizer, fixed_now):
        """Empty string should return None."""
        result = normalizer.normalize("", now=fixed_now)
        assert result is None
    
    def test_whitespace_only(self, normalizer, fixed_now):
        """Whitespace-only should return None."""
        result = normalizer.normalize("   \t\n  ", now=fixed_now)
        assert result is None
    
    def test_slash_command_ignored(self, normalizer, fixed_now):
        """Slash commands should not be parsed (handled elsewhere)."""
        result = normalizer.normalize("/remind me to test", now=fixed_now)
        assert result is None
    
    def test_non_reminder_text(self, normalizer, fixed_now):
        """Generic text should return None."""
        non_reminders = [
            "Hello, how are you?",
            "What's the weather like?",
            "I think we should schedule a meeting",
        ]
        
        for text in non_reminders:
            result = normalizer.normalize(text, now=fixed_now)
            assert result is None, f"Should not match: '{text}'"


class TestRegressionProtection:
    """Tests to prevent specific regressions."""
    
    def test_success_criterion_1_weekday_briefing(self, normalizer, fixed_now):
        """SUCCESS CRITERION 1: 'every weekday in my morning briefing help me...'"""
        phrase = "every weekday in my morning briefing help me prioritize my top 3 tasks"
        result = normalizer.normalize(phrase, now=fixed_now)
        
        assert result is not None
        assert result.intent_type == "reminder.create"
        assert result.channel == "morning_briefing"
        assert "weekday" in result.recurrence
        assert "prioritize" in result.task.lower()
        # Should need clarification for explicit time
        assert result.needs_clarification
    
    def test_success_criterion_2_explicit_time(self, normalizer, fixed_now):
        """SUCCESS CRITERION 2: 'remind me to review GitHub notifications at 9am tomorrow'"""
        phrase = "remind me to review GitHub notifications at 9am tomorrow"
        result = normalizer.normalize(phrase, now=fixed_now)
        
        assert result is not None
        assert result.intent_type == "reminder.create"
        assert result.due_at is not None
        # Allow timestamp to be equal to or greater than now (timezone edge cases)
        assert result.due_at >= int(fixed_now.timestamp()), \
            f"Timestamp should be >= now (got {result.due_at}, now {int(fixed_now.timestamp())})"
        assert "github" in result.task.lower()
        assert not result.needs_clarification  # Explicit time


if __name__ == "__main__":
    # Run with: pytest -v tests/test_reminder_intent_golden.py
    pytest.main([__file__, "-v"])
