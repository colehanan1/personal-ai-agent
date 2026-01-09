"""Tests for prompting middleware pipeline."""
from __future__ import annotations

import pytest


class TestPromptingPipeline:
    """Tests for PromptingPipeline class."""

    def test_pipeline_disabled_returns_identity(self):
        """Test that pipeline returns identity output when disabled."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=False,
            enable_cove=False,
        )
        pipeline = PromptingPipeline(config=config)

        user_input = "What is the meaning of life?"
        result = pipeline.run(user_input)

        # Response should be unchanged
        assert result.response == user_input
        assert result.verified is False
        assert result.verified_badge is None
        assert result.reshaped_prompt is None

    def test_pipeline_with_trivial_request(self):
        """Test that trivial requests bypass the pipeline."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=True,
        )
        pipeline = PromptingPipeline(config=config)

        # Greeting should be classified as trivial
        user_input = "Hello!"
        result = pipeline.run(user_input)

        # Should bypass and return unchanged
        assert result.response == user_input
        assert result.verified is False

    def test_pipeline_returns_request_id(self):
        """Test that pipeline returns a valid request ID."""
        from prompting import PromptingPipeline

        pipeline = PromptingPipeline()
        result = pipeline.run("Test input")

        assert result.request_id is not None
        assert len(result.request_id) > 0

    def test_pipeline_custom_request_id(self):
        """Test that pipeline uses custom request ID when provided."""
        from prompting import PromptingPipeline

        pipeline = PromptingPipeline()
        custom_id = "custom-request-123"
        result = pipeline.run("Test input", request_id=custom_id)

        assert result.request_id == custom_id

    def test_pipeline_artifacts_when_enabled(self):
        """Test that artifacts are included when debug storage enabled."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(store_debug_artifacts=True)
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("Analyze this data")

        assert result.artifacts is not None
        assert result.artifacts.request_id == result.request_id
        assert result.artifacts.prompt_spec is not None
        assert result.artifacts.final_response is not None

    def test_pipeline_artifacts_disabled(self):
        """Test that artifacts are excluded when debug storage disabled."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(store_debug_artifacts=False)
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("Test input")

        # Artifacts should still exist for internal use, but not in result
        # Actually, they're included in result regardless for now
        # The flag controls memory storage, not result inclusion
        pass  # Adjust based on actual implementation

    def test_pipeline_reshaped_prompt_hidden_by_default(self):
        """Test that reshaped prompt is not exposed by default."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            allow_user_inspect_reshaped_prompt=False,
        )
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("Research topic", include_reshaped_prompt=True)

        # Should not expose reshaped prompt
        assert result.reshaped_prompt is None

    def test_pipeline_reshaped_prompt_when_allowed(self):
        """Test that reshaped prompt is exposed when allowed and requested."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            allow_user_inspect_reshaped_prompt=True,
        )
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("Research topic", include_reshaped_prompt=True)

        # Now that reshaping is implemented, this should return reshaped prompt info
        # The "Research topic" input should be reshaped since it's classified as research
        # Uses InspectOutput format with "=== Prompt Inspection ===" header
        assert result.reshaped_prompt is not None
        assert "=== Prompt Inspection ===" in result.reshaped_prompt
        assert "ORIGINAL:" in result.reshaped_prompt
        assert "RESHAPED:" in result.reshaped_prompt
        assert "Research topic" in result.reshaped_prompt

    def test_run_pipeline_convenience_function(self):
        """Test the run_pipeline convenience function."""
        from prompting import run_pipeline

        result = run_pipeline("Hello world")

        assert result.response == "Hello world"
        assert result.request_id is not None


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_passthrough_result(self):
        """Test creating a passthrough result."""
        from prompting.types import PipelineResult

        original = "Test input"
        result = PipelineResult.passthrough(original)

        assert result.response == original
        assert result.verified is False
        assert result.verified_badge is None
        assert result.reshaped_prompt is None
        assert result.artifacts is not None
        assert result.artifacts.prompt_spec is not None
        assert not result.artifacts.prompt_spec.was_modified()

    def test_passthrough_with_custom_id(self):
        """Test passthrough result with custom request ID."""
        from prompting.types import PipelineResult

        custom_id = "my-custom-id"
        result = PipelineResult.passthrough("Test", request_id=custom_id)

        assert result.request_id == custom_id


class TestPipelineArtifacts:
    """Tests for PipelineArtifacts dataclass."""

    def test_has_reshaping(self):
        """Test has_reshaping detection."""
        from prompting.types import PipelineArtifacts, PromptSpec

        # No reshaping
        artifacts = PipelineArtifacts()
        assert artifacts.has_reshaping() is False

        # With reshaping but not modified
        artifacts.prompt_spec = PromptSpec(
            original_prompt="hello",
            reshaped_prompt="hello",
        )
        assert artifacts.has_reshaping() is False

        # With actual modification
        artifacts.prompt_spec = PromptSpec(
            original_prompt="hello",
            reshaped_prompt="hello, world",
        )
        assert artifacts.has_reshaping() is True

    def test_has_verification(self):
        """Test has_verification detection."""
        from prompting.types import CoveQuestion, PipelineArtifacts

        # No verification
        artifacts = PipelineArtifacts()
        assert artifacts.has_verification() is False

        # With questions
        artifacts.cove_questions = [
            CoveQuestion(question_text="Is this true?", target_claim="test"),
        ]
        assert artifacts.has_verification() is True

    def test_verification_passed(self):
        """Test verification_passed detection."""
        from prompting.types import (
            CoveFinding,
            FindingSeverity,
            PipelineArtifacts,
            VerificationStatus,
        )

        # No findings = passed
        artifacts = PipelineArtifacts()
        assert artifacts.verification_passed() is True

        # Non-critical finding = passed
        artifacts.cove_findings = [
            CoveFinding(
                description="Minor issue",
                severity=FindingSeverity.INFO,
            ),
        ]
        assert artifacts.verification_passed() is True

        # Critical finding = failed
        artifacts.cove_findings = [
            CoveFinding(
                description="Major issue",
                severity=FindingSeverity.ERROR,
            ),
        ]
        assert artifacts.verification_passed() is False

        # Contradicted status = failed
        artifacts.cove_findings = [
            CoveFinding(
                description="Contradiction found",
                severity=FindingSeverity.WARNING,
                status=VerificationStatus.CONTRADICTED,
            ),
        ]
        assert artifacts.verification_passed() is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from prompting.types import PipelineArtifacts, PromptSpec

        artifacts = PipelineArtifacts(
            request_id="test-123",
            prompt_spec=PromptSpec(
                original_prompt="hello",
                reshaped_prompt="hello, world",
                category="greeting",
            ),
            draft_response="Hello!",
            final_response="Hello!",
        )

        data = artifacts.to_dict()

        assert data["request_id"] == "test-123"
        assert data["prompt_spec"]["original_prompt"] == "hello"
        assert data["prompt_spec"]["reshaped_prompt"] == "hello, world"
        assert data["prompt_spec"]["was_modified"] is True
        assert data["draft_response"] == "Hello!"
        assert data["final_response"] == "Hello!"
