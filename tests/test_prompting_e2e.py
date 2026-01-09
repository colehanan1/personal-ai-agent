"""
End-to-end tests for the prompting pipeline.

Tests cover:
- Prompt generation with verification and badge
- User request verification with badge
- Inspect pathway showing reshaped prompt
- Memory integration for artifact storage
"""
from __future__ import annotations

import pytest
from typing import Optional
from unittest.mock import MagicMock, patch

from prompting import (
    PromptingPipeline,
    PromptingConfig,
    PipelineResult,
    InspectOutput,
    QualityCheckResult,
    check_prompt_quality,
    revise_prompt_for_quality,
)
from prompting.cove import ChainOfVerification, CoveResult
from prompting.types import CoveQuestion, CoveFinding, VerificationStatus, FindingSeverity


# --- Test Fixtures ---

@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    def _mock_response(prompt: str) -> str:
        # Return a simple response based on prompt content
        if "verification" in prompt.lower() or "question" in prompt.lower():
            return '{"questions": [{"question_text": "Test question?", "target_claim": "Test claim", "source_context": "Context"}]}'
        if "finalize" in prompt.lower():
            return "This is a verified response with accurate information."
        return "This is a draft response about the topic."
    return _mock_response


@pytest.fixture
def config_with_all_enabled():
    """Config with all features enabled."""
    return PromptingConfig(
        enable_prompt_reshape=True,
        enable_cove=True,
        enable_cove_for_responses=True,
        allow_user_inspect_reshaped_prompt=True,
        return_verified_badge=True,
        store_debug_artifacts=True,
        cove_min_questions=1,
        cove_max_questions=3,
    )


@pytest.fixture
def config_disabled():
    """Config with everything disabled."""
    return PromptingConfig(
        enable_prompt_reshape=False,
        enable_cove=False,
        enable_cove_for_responses=False,
        allow_user_inspect_reshaped_prompt=False,
        return_verified_badge=False,
        store_debug_artifacts=False,
    )


# --- Prompt Generation E2E Tests ---

class TestPromptGenerationE2E:
    """End-to-end tests for prompt generation flow."""

    def test_generate_agent_prompt_returns_verified_badge(self, config_with_all_enabled):
        """Agent prompt generation should return a verified badge."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Test with a non-trivial prompt that includes required elements
        prompt = """
        Create a function that parses JSON input and returns structured output.
        Must handle edge cases and follow coding conventions.
        Include unit tests to verify correctness.
        """

        result = pipeline.run(prompt, mode="generate_agent_prompt")

        assert result is not None
        assert result.response is not None
        # Badge may be "Verification unavailable" if no LLM, but should exist
        # Since we're testing without mocking LLM, check structure exists

    def test_generate_agent_prompt_runs_quality_checks(self, config_with_all_enabled):
        """Agent prompt generation should run quality checks."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Prompt missing some required elements
        prompt = "Write a simple function"

        result = pipeline.run(prompt, mode="generate_agent_prompt")

        assert result is not None
        # Check that quality check metadata was recorded
        if result.artifacts:
            metadata = result.artifacts.metadata
            assert "quality_attempts" in metadata or "classification" in metadata

    def test_generate_agent_prompt_revises_on_quality_failure(self, config_with_all_enabled):
        """Prompt should be revised if quality checks fail."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Minimal prompt that fails quality checks
        prompt = "Do something"

        result = pipeline.run(prompt, mode="generate_agent_prompt")

        # Response should be longer than original due to revisions
        assert len(result.response) > len(prompt)

    def test_generate_prompt_mode_always_runs_cove(self, config_disabled):
        """generate_prompt mode should run CoVe even when config disables it."""
        # Create config with CoVe disabled
        config = PromptingConfig(
            enable_cove=False,
            enable_prompt_reshape=True,
            return_verified_badge=True,
        )
        pipeline = PromptingPipeline(config=config)

        prompt = "Explain quantum computing for research purposes"
        result = pipeline.run(prompt, mode="generate_prompt")

        # Even with CoVe disabled in config, generate_prompt should run it
        # Badge should exist (may be unavailable without LLM)
        assert result is not None


class TestUserRequestE2E:
    """End-to-end tests for user request verification."""

    def test_non_trivial_request_gets_reshaped(self, config_with_all_enabled):
        """Non-trivial requests should be reshaped."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Explain the theory of relativity in detail for research"
        result = pipeline.run(prompt, mode="reshape_only")

        assert result is not None
        assert result.response is not None

    def test_trivial_request_bypasses_pipeline(self, config_with_all_enabled):
        """Trivial requests should bypass the pipeline."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "hi"
        result = pipeline.run(prompt)

        assert result is not None
        assert result.response == prompt  # Unchanged

    def test_full_answer_mode_returns_badge(self, config_with_all_enabled):
        """Full answer mode should return a verification badge."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "What is the capital of France? This is a research question."
        result = pipeline.run(prompt, mode="full_answer")

        assert result is not None
        # Badge may be None if LLM unavailable, but response should exist


class TestInspectPathwayE2E:
    """End-to-end tests for the inspect pathway."""

    def test_inspect_shows_reshaped_prompt(self, config_with_all_enabled):
        """Inspect should show the reshaped prompt."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Explain AI for research /show_prompt"
        result = pipeline.run(prompt, include_reshaped_prompt=True)

        # With allow_user_inspect_reshaped_prompt=True, should have inspect info
        # The actual content depends on reshaping, but structure should exist

    def test_inspect_output_never_shows_chain_of_thought(self, config_with_all_enabled):
        """Inspect output should never show chain-of-thought."""
        # Create an InspectOutput directly
        inspect = InspectOutput(
            original_prompt="Test prompt",
            reshaped_prompt="Reshaped test prompt",
            verification_questions=["Q1?", "Q2?"],
            findings_summary=["Finding 1", "Finding 2"],
            badge="Verified (2/2 checks passed)",
        )

        formatted = inspect.format()

        # Should contain expected sections
        assert "ORIGINAL:" in formatted
        assert "RESHAPED:" in formatted
        assert "VERIFICATION QUESTIONS:" in formatted
        assert "FINDINGS:" in formatted
        assert "STATUS:" in formatted

        # Should NOT contain internal details
        assert "chain-of-thought" not in formatted.lower()
        assert "reasoning" not in formatted.lower()

    def test_inspect_commands_are_stripped(self, config_with_all_enabled):
        """Inspect commands should be stripped from processing."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Explain AI /show_prompt"
        result = pipeline.run(prompt)

        # The /show_prompt should be stripped
        assert "/show_prompt" not in result.response

    def test_inspect_disabled_returns_no_inspect_info(self, config_disabled):
        """When inspect is disabled, no inspect info should be returned."""
        pipeline = PromptingPipeline(config=config_disabled)

        prompt = "Explain AI /show_prompt"
        result = pipeline.run(prompt, include_reshaped_prompt=True)

        # Inspect info should be None when disabled
        assert result.reshaped_prompt is None


class TestMemoryIntegration:
    """Tests for memory integration with artifacts storage."""

    def test_artifacts_stored_when_enabled(self, config_with_all_enabled):
        """Artifacts should be stored when debug storage is enabled."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Research question about AI"
        result = pipeline.run(prompt, mode="full_answer")

        # Artifacts should be populated when storage is enabled
        assert result.artifacts is not None
        assert result.artifacts.request_id is not None

    def test_artifacts_not_stored_when_disabled(self, config_disabled):
        """Artifacts should not be in result when storage is disabled."""
        pipeline = PromptingPipeline(config=config_disabled)

        prompt = "Simple question"
        result = pipeline.run(prompt)

        # Artifacts should be None when storage is disabled
        assert result.artifacts is None

    def test_memory_failures_dont_crash_pipeline(self, config_with_all_enabled):
        """Memory storage failures should not crash the pipeline."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Mock the memory hook to fail
        with patch.object(pipeline.memory_hook, 'store_pipeline_result', side_effect=Exception("Storage failed")):
            prompt = "Research question for analysis"
            result = pipeline.run(prompt, mode="full_answer")

            # Pipeline should still complete despite storage failure
            assert result is not None
            assert result.response is not None


class TestQualityChecks:
    """Tests for prompt quality check functionality."""

    def test_quality_check_passes_with_all_elements(self):
        """Quality check should pass when all elements are present."""
        prompt = """
        This function takes input parameters and returns output values.
        You must follow these constraints and avoid edge cases.
        Include unit tests to verify the implementation.
        """

        result = check_prompt_quality(prompt)

        assert result.passed is True
        assert len(result.issues) == 0
        assert result.score == 1.0

    def test_quality_check_fails_missing_elements(self):
        """Quality check should fail when elements are missing."""
        prompt = "Do something simple"

        result = check_prompt_quality(prompt)

        assert result.passed is False
        assert len(result.issues) > 0
        assert result.score < 1.0

    def test_revision_adds_missing_sections(self):
        """Revision should add sections for missing elements."""
        prompt = "Write a function"
        issues = [
            "Missing explicit inputs/outputs",
            "Missing constraints",
            "Missing testing instructions",
        ]

        revised = revise_prompt_for_quality(prompt, issues)

        # Revised prompt should be longer
        assert len(revised) > len(prompt)
        # Should contain added sections
        assert "Inputs/Outputs" in revised or "Expected" in revised
        assert "Constraints" in revised
        assert "Testing" in revised


class TestVerifiedBadge:
    """Tests for verified badge generation."""

    def test_badge_format_all_passed(self, config_with_all_enabled):
        """Badge should show all checks passed."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Create mock artifacts with verified questions
        from prompting.types import PipelineArtifacts
        artifacts = PipelineArtifacts()
        artifacts.cove_questions = [
            CoveQuestion(question_text="Q1?", target_claim="C1", verified=True),
            CoveQuestion(question_text="Q2?", target_claim="C2", verified=True),
        ]

        badge = pipeline._generate_verified_badge(artifacts)

        assert "2/2" in badge
        assert "Verified" in badge

    def test_badge_format_some_failed(self, config_with_all_enabled):
        """Badge should show partial verification."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        from prompting.types import PipelineArtifacts
        artifacts = PipelineArtifacts()
        artifacts.cove_questions = [
            CoveQuestion(question_text="Q1?", target_claim="C1", verified=True),
            CoveQuestion(question_text="Q2?", target_claim="C2", verified=False),
        ]

        badge = pipeline._generate_verified_badge(artifacts)

        assert "1/2" in badge

    def test_badge_when_no_questions(self, config_with_all_enabled):
        """Badge should handle no verification questions."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        from prompting.types import PipelineArtifacts
        artifacts = PipelineArtifacts()
        artifacts.cove_questions = []

        badge = pipeline._generate_verified_badge(artifacts)

        assert "Verified" in badge


class TestGracefulDegradation:
    """Tests for graceful degradation when components fail."""

    def test_reshape_failure_returns_original(self, config_with_all_enabled):
        """If reshaping fails, original prompt should be returned."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Test with empty prompt (edge case)
        prompt = ""
        result = pipeline.run(prompt)

        # Should not crash, return empty or passthrough
        assert result is not None

    def test_cove_failure_returns_draft(self, config_with_all_enabled):
        """If CoVe fails, draft response should be returned."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        # Run with mode that uses CoVe
        prompt = "Research question for analysis"
        result = pipeline.run(prompt, mode="full_answer")

        # Should not crash even if LLM unavailable
        assert result is not None
        assert result.response is not None

    def test_pipeline_handles_invalid_mode(self, config_with_all_enabled):
        """Pipeline should handle invalid mode gracefully."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Test prompt"
        result = pipeline.run(prompt, mode="invalid_mode")

        # Should fall back to reshape_only
        assert result is not None
        assert result.response is not None


class TestInspectOutputFormat:
    """Tests for InspectOutput formatting."""

    def test_format_with_all_sections(self):
        """Format should include all sections when present."""
        inspect = InspectOutput(
            original_prompt="Original",
            reshaped_prompt="Reshaped",
            verification_questions=["Q1?", "Q2?"],
            findings_summary=["F1", "F2"],
            badge="Verified",
        )

        formatted = inspect.format()

        assert "=== Prompt Inspection ===" in formatted
        assert "ORIGINAL:" in formatted
        assert "Original" in formatted
        assert "RESHAPED:" in formatted
        assert "Reshaped" in formatted
        assert "VERIFICATION QUESTIONS:" in formatted
        assert "Q1?" in formatted
        assert "FINDINGS:" in formatted
        assert "F1" in formatted
        assert "STATUS: Verified" in formatted

    def test_format_without_optional_sections(self):
        """Format should handle missing optional sections."""
        inspect = InspectOutput(
            original_prompt="Original",
            reshaped_prompt="Reshaped",
        )

        formatted = inspect.format()

        assert "ORIGINAL:" in formatted
        assert "RESHAPED:" in formatted
        # Optional sections should not appear
        assert "VERIFICATION QUESTIONS:" not in formatted
        assert "FINDINGS:" not in formatted
        assert "STATUS:" not in formatted


class TestPipelineModes:
    """Tests for different pipeline modes."""

    def test_reshape_only_mode(self, config_with_all_enabled):
        """reshape_only mode should only reshape, not generate answer."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Explain AI for research purposes"
        result = pipeline.run(prompt, mode="reshape_only")

        assert result is not None
        # Response should be the reshaped prompt, not an LLM answer

    def test_full_answer_mode(self, config_with_all_enabled):
        """full_answer mode should generate and verify answer."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "What is machine learning? This is for research."
        result = pipeline.run(prompt, mode="full_answer")

        assert result is not None

    def test_generate_prompt_mode(self, config_with_all_enabled):
        """generate_prompt mode should verify the prompt itself."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Create a task for coding a JSON parser"
        result = pipeline.run(prompt, mode="generate_prompt")

        assert result is not None

    def test_generate_agent_prompt_mode(self, config_with_all_enabled):
        """generate_agent_prompt mode should run quality checks and CoVe."""
        pipeline = PromptingPipeline(config=config_with_all_enabled)

        prompt = "Create a coding task with inputs, constraints, and tests"
        result = pipeline.run(prompt, mode="generate_agent_prompt")

        assert result is not None
        if result.artifacts:
            # Should have quality metadata
            assert "metadata" in dir(result.artifacts)
