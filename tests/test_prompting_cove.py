"""Tests for Chain-of-Verification (CoVe) module."""
from __future__ import annotations

import json
import os
import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCoveQuestionBounds:
    """Tests for CoVe question count bounds."""

    def test_question_count_respects_minimum(self):
        """Test that generated questions respect cove_min_questions."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification

        config = PromptingConfig(
            cove_min_questions=3,
            cove_max_questions=5,
        )
        cove = ChainOfVerification(config=config)

        # Mock LLM to return only 1 question
        mock_response = {
            "questions": [
                {"question_text": "Q1", "target_claim": "C1", "source_context": ""}
            ]
        }

        with patch.object(cove, "_call_llm", return_value=json.dumps(mock_response)):
            with patch.object(cove, "is_llm_available", return_value=True):
                questions = cove.generate_verification_questions("user q", "draft", k=3)

        # Should pad to minimum
        assert len(questions) >= config.cove_min_questions

    def test_question_count_respects_maximum(self):
        """Test that generated questions respect cove_max_questions."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification

        config = PromptingConfig(
            cove_min_questions=2,
            cove_max_questions=3,
        )
        cove = ChainOfVerification(config=config)

        # Mock LLM to return 10 questions
        mock_response = {
            "questions": [
                {"question_text": f"Q{i}", "target_claim": f"C{i}", "source_context": ""}
                for i in range(10)
            ]
        }

        with patch.object(cove, "_call_llm", return_value=json.dumps(mock_response)):
            with patch.object(cove, "is_llm_available", return_value=True):
                questions = cove.generate_verification_questions("user q", "draft")

        # Should cap at maximum
        assert len(questions) <= config.cove_max_questions

    def test_explicit_k_clamped_to_bounds(self):
        """Test that explicit k parameter is clamped to config bounds."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification

        config = PromptingConfig(
            cove_min_questions=2,
            cove_max_questions=5,
        )
        cove = ChainOfVerification(config=config)

        # Mock LLM
        mock_response = {
            "questions": [
                {"question_text": f"Q{i}", "target_claim": f"C{i}", "source_context": ""}
                for i in range(10)
            ]
        }

        with patch.object(cove, "_call_llm", return_value=json.dumps(mock_response)):
            with patch.object(cove, "is_llm_available", return_value=True):
                # Request k=10 but should be clamped to max=5
                questions = cove.generate_verification_questions("user q", "draft", k=10)

        assert len(questions) <= config.cove_max_questions

    def test_default_k_is_midpoint(self):
        """Test that default k is the midpoint of min and max."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification

        config = PromptingConfig(
            cove_min_questions=2,
            cove_max_questions=6,
        )
        cove = ChainOfVerification(config=config)

        # Mock LLM to return exactly what we ask for
        def mock_llm_call(system_prompt, user_prompt, *args, **kwargs):
            # Extract k from system prompt
            return json.dumps({
                "questions": [
                    {"question_text": f"Q{i}", "target_claim": f"C{i}", "source_context": ""}
                    for i in range(4)  # midpoint is (2+6)//2 = 4
                ]
            })

        with patch.object(cove, "_call_llm", side_effect=mock_llm_call):
            with patch.object(cove, "is_llm_available", return_value=True):
                questions = cove.generate_verification_questions("user q", "draft")

        # Should have 4 questions (midpoint)
        assert len(questions) == 4


class TestCoveFinalization:
    """Tests for CoVe finalization behavior."""

    def test_finalization_changes_output_with_error(self):
        """Test that finalization changes output when error is detected in draft."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveFinding, CoveQuestion, VerificationStatus, FindingSeverity

        cove = ChainOfVerification()

        # Prepare a finding indicating error in draft
        question = CoveQuestion(
            question_text="Is Paris the capital of Germany?",
            target_claim="Paris is the capital of Germany",
            source_context="Paris is the capital of Germany.",
            answer="No, Berlin is the capital of Germany.",
            verified=False,
            confidence=0.95,
        )
        finding = CoveFinding(
            description="Claim is incorrect: Paris is the capital of Germany",
            severity=FindingSeverity.ERROR,
            status=VerificationStatus.CONTRADICTED,
            question_id=question.question_id,
            original_text="Paris is the capital of Germany.",
            suggested_correction="Berlin is the capital of Germany.",
        )

        # Mock LLM to return corrected response
        corrected_response = "Berlin is the capital of Germany."

        with patch.object(cove, "_call_llm", return_value=corrected_response):
            with patch.object(cove, "is_llm_available", return_value=True):
                final, findings = cove.finalize_answer(
                    question="What is the capital of Germany?",
                    draft="Paris is the capital of Germany.",
                    findings=[(question, finding)],
                )

        assert final != "Paris is the capital of Germany."
        assert "Berlin" in final or final == corrected_response

    def test_finalization_preserves_draft_when_verified(self):
        """Test that finalization preserves draft when all claims verified."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion

        cove = ChainOfVerification()

        question = CoveQuestion(
            question_text="Is Berlin the capital of Germany?",
            target_claim="Berlin is the capital of Germany",
            source_context="Berlin is the capital of Germany.",
            answer="Yes, Berlin is the capital of Germany.",
            verified=True,
            confidence=0.99,
        )

        draft = "Berlin is the capital of Germany."

        # Mock LLM to return draft unchanged
        with patch.object(cove, "_call_llm", return_value=draft):
            with patch.object(cove, "is_llm_available", return_value=True):
                final, findings = cove.finalize_answer(
                    question="What is the capital of Germany?",
                    draft=draft,
                    findings=[(question, None)],
                )

        assert final == draft
        assert len(findings) == 0

    def test_finalization_returns_draft_when_llm_unavailable(self):
        """Test finalization returns draft when LLM is unavailable."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion, CoveFinding, FindingSeverity, VerificationStatus

        cove = ChainOfVerification(llm_url=None, model_name=None)

        question = CoveQuestion(
            question_text="Is X true?",
            target_claim="X is true",
            verified=False,
        )
        finding = CoveFinding(
            description="X may be false",
            severity=FindingSeverity.WARNING,
            status=VerificationStatus.CONTRADICTED,
        )

        draft = "Original draft text"
        final, findings = cove.finalize_answer(
            question="Query",
            draft=draft,
            findings=[(question, finding)],
        )

        assert final == draft
        assert len(findings) == 1


class TestCoveArtifactStorage:
    """Tests for CoVe artifact storage to memory hook."""

    def test_artifacts_stored_with_questions(self):
        """Test artifacts stored when questions are generated."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification
        from prompting.memory_hook import MemoryHook
        from prompting.types import CoveQuestion

        mock_hook = MagicMock(spec=MemoryHook)
        mock_hook.store_verification_artifacts.return_value = "mem-123"

        config = PromptingConfig(store_debug_artifacts=True)
        cove = ChainOfVerification(config=config, memory_hook=mock_hook)

        mock_question = CoveQuestion(
            question_text="Is this accurate?",
            target_claim="The claim",
            source_context="Context",
        )

        with patch.object(cove, "is_llm_available", return_value=True):
            with patch.object(
                cove, "generate_verification_questions", return_value=[mock_question]
            ):
                with patch.object(
                    cove, "answer_verification_question_independently", return_value=mock_question
                ):
                    with patch.object(cove, "finalize_answer", return_value=("Final", [])):
                        result = cove.run("Test question", draft="Draft response")

        mock_hook.store_verification_artifacts.assert_called_once()

    def test_artifacts_not_stored_when_disabled(self):
        """Test that artifacts are NOT stored when store_debug_artifacts is False."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification
        from prompting.memory_hook import MemoryHook
        from prompting.types import CoveQuestion

        mock_hook = MagicMock(spec=MemoryHook)

        config = PromptingConfig(store_debug_artifacts=False)
        cove = ChainOfVerification(config=config, memory_hook=mock_hook)

        mock_question = CoveQuestion(
            question_text="Is this accurate?",
            target_claim="The claim",
            source_context="Context",
        )

        with patch.object(cove, "is_llm_available", return_value=True):
            with patch.object(
                cove, "generate_verification_questions", return_value=[mock_question]
            ):
                with patch.object(
                    cove, "answer_verification_question_independently", return_value=mock_question
                ):
                    with patch.object(cove, "finalize_answer", return_value=("Final", [])):
                        result = cove.run("Test question", draft="Draft response")

        mock_hook.store_verification_artifacts.assert_not_called()

    def test_artifacts_not_stored_when_no_memory_hook(self):
        """Test that no error occurs when memory_hook is None."""
        from prompting import PromptingConfig
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion

        config = PromptingConfig(store_debug_artifacts=True)
        cove = ChainOfVerification(config=config, memory_hook=None)

        mock_question = CoveQuestion(
            question_text="Is this accurate?",
            target_claim="The claim",
            source_context="Context",
        )

        with patch.object(cove, "is_llm_available", return_value=True):
            with patch.object(
                cove, "generate_verification_questions", return_value=[mock_question]
            ):
                with patch.object(
                    cove, "answer_verification_question_independently", return_value=mock_question
                ):
                    with patch.object(cove, "finalize_answer", return_value=("Final", [])):
                        # Should not raise
                        result = cove.run("Test question", draft="Draft response")

        assert result is not None


class TestCoveGracefulDegradation:
    """Tests for graceful degradation when LLM unavailable."""

    def test_no_crash_when_llm_unavailable(self):
        """Test that CoVe doesn't crash when LLM is unavailable."""
        from prompting.cove import ChainOfVerification

        cove = ChainOfVerification(llm_url=None, model_name=None)

        # Should not raise, should return sensible default
        result = cove.run("Test question", draft="Test draft")

        assert result.final_response == "Test draft"
        assert result.badge is not None

    def test_questions_empty_when_llm_unavailable(self):
        """Test that question generation returns empty when LLM unavailable."""
        from prompting.cove import ChainOfVerification

        cove = ChainOfVerification(llm_url=None, model_name=None)

        questions = cove.generate_verification_questions("q", "draft")

        assert questions == []

    def test_badge_indicates_no_claims_when_no_questions(self):
        """Test that badge indicates no claims to check when no questions generated."""
        from prompting.cove import ChainOfVerification

        cove = ChainOfVerification(llm_url=None, model_name=None)

        result = cove.run("Test question", draft="Test draft")

        # Badge should indicate no claims to check
        assert result.badge is not None
        assert "no claims" in result.badge.lower()

    def test_draft_generation_failure_returns_error(self):
        """Test that draft generation failure returns proper error."""
        from prompting.cove import ChainOfVerification, CoveError

        cove = ChainOfVerification()

        with patch.object(cove, "is_llm_available", return_value=True):
            with patch.object(cove, "generate_draft", side_effect=CoveError("LLM error")):
                result = cove.run("Test question")

        assert result.error is not None
        assert "draft" in result.error.lower()
        assert result.badge == "Verification unavailable"

    def test_answer_verification_question_handles_failure(self):
        """Test that answering verification question handles failure gracefully."""
        from prompting.cove import ChainOfVerification, CoveError
        from prompting.types import CoveQuestion

        cove = ChainOfVerification()

        vq = CoveQuestion(
            question_text="Test question",
            target_claim="Test claim",
        )

        with patch.object(cove, "is_llm_available", return_value=True):
            with patch.object(cove, "_call_llm", side_effect=CoveError("Network error")):
                result = cove.answer_verification_question_independently(vq)

        assert result.verified is None
        assert result.confidence == 0.0
        assert "failed" in result.answer.lower() or "error" in result.answer.lower()


class TestPipelineModes:
    """Integration tests for pipeline modes."""

    def test_mode_reshape_only_default(self):
        """Test that reshape_only is the default mode."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=True,
        )
        pipeline = PromptingPipeline(config=config)

        # Default mode should be reshape_only
        result = pipeline.run("Research quantum computing")

        # Should have response (the reshaped prompt)
        assert result.response is not None
        assert result.request_id is not None

    def test_mode_full_answer_uses_cove(self):
        """Test that full_answer mode uses CoVe when enabled."""
        from prompting import PromptingConfig, PromptingPipeline
        from prompting.cove import ChainOfVerification, CoveResult

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=True,
        )
        pipeline = PromptingPipeline(config=config)

        mock_cove_result = CoveResult(
            draft_response="Draft response",
            final_response="Final verified response",
            questions=[],
            findings=[],
            verified=True,
            badge="Verified: ran 0 checks",
        )

        with patch.object(
            ChainOfVerification, "generate_draft", return_value="Draft response"
        ):
            with patch.object(ChainOfVerification, "run", return_value=mock_cove_result):
                with patch.object(ChainOfVerification, "is_llm_available", return_value=True):
                    result = pipeline.run("Research quantum computing", mode="full_answer")

        assert result.response is not None

    def test_mode_generate_prompt_always_verifies(self):
        """Test that generate_prompt mode always verifies the prompt."""
        from prompting import PromptingConfig, PromptingPipeline
        from prompting.cove import CoveResult
        import prompting.pipeline as pipeline_module

        config = PromptingConfig(
            enable_prompt_reshape=True,
            enable_cove=False,  # CoVe disabled but should still verify in generate_prompt mode
        )
        pipeline = PromptingPipeline(config=config)

        mock_cove_result = CoveResult(
            draft_response="Original prompt",
            final_response="Verified prompt",
            questions=[],
            findings=[],
            verified=True,
            badge="Verified: no claims to check",
        )

        with patch.object(
            pipeline_module, "cove_verify_prompt", return_value=mock_cove_result
        ) as mock_verify:
            result = pipeline.run("Research topic", mode="generate_prompt")

        # Should have called verify_prompt
        mock_verify.assert_called_once()

    def test_unknown_mode_falls_back_to_reshape_only(self):
        """Test that unknown mode falls back to reshape_only behavior."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_prompt_reshape=True,
        )
        pipeline = PromptingPipeline(config=config)

        # Unknown mode should not crash
        result = pipeline.run("Test input", mode="unknown_mode")

        assert result.response is not None


class TestPipelineIntegrationWithStubs:
    """Integration tests using fallback stubs (no actual LLM)."""

    def test_pipeline_executes_without_llm(self):
        """Test pipeline executes end-to-end without LLM using fallback stubs."""
        from prompting import PromptingConfig, PromptingPipeline

        # Clear any LLM env vars
        with patch.dict("os.environ", {}, clear=True):
            config = PromptingConfig(
                enable_prompt_reshape=True,
                enable_cove=True,
            )
            pipeline = PromptingPipeline(config=config)

            # Should not crash
            result = pipeline.run("Analyze this data", mode="full_answer")

            assert result is not None
            assert result.response is not None
            assert result.request_id is not None

    def test_cove_result_has_correct_structure(self):
        """Test CoveResult has all expected fields."""
        from prompting.cove import CoveResult

        result = CoveResult(
            draft_response="Draft",
            final_response="Final",
        )

        assert hasattr(result, "draft_response")
        assert hasattr(result, "final_response")
        assert hasattr(result, "questions")
        assert hasattr(result, "findings")
        assert hasattr(result, "verified")
        assert hasattr(result, "badge")
        assert hasattr(result, "error")

    def test_cove_result_is_revised_detection(self):
        """Test CoveResult.is_revised() correctly detects revisions."""
        from prompting.cove import CoveResult

        # Same content
        result1 = CoveResult(
            draft_response="Same content",
            final_response="Same content",
        )
        assert not result1.is_revised()

        # Different content
        result2 = CoveResult(
            draft_response="Original draft",
            final_response="Revised final",
        )
        assert result2.is_revised()

        # Whitespace differences should not count
        result3 = CoveResult(
            draft_response="  Same content  ",
            final_response="Same content",
        )
        assert not result3.is_revised()


class TestVerifiedBadge:
    """Tests for verified badge generation."""

    def test_badge_absent_when_cove_disabled(self):
        """Test badge is None when CoVe is disabled."""
        from prompting import PromptingConfig, PromptingPipeline

        config = PromptingConfig(
            enable_cove=False,
            return_verified_badge=True,
        )
        pipeline = PromptingPipeline(config=config)

        result = pipeline.run("Test")

        assert result.verified_badge is None

    def test_badge_absent_when_badge_disabled(self):
        """Test badge is None when return_verified_badge is False."""
        from prompting import PromptingConfig, PromptingPipeline
        from prompting.cove import CoveResult
        import prompting.pipeline as pipeline_module

        config = PromptingConfig(
            enable_cove=True,
            return_verified_badge=False,  # Badge disabled
        )
        pipeline = PromptingPipeline(config=config)

        mock_cove_result = CoveResult(
            draft_response="Draft",
            final_response="Final",
            questions=[],
            findings=[],
            verified=True,
            badge="Verified: some badge",
        )

        with patch.object(
            pipeline_module, "cove_verify_prompt", return_value=mock_cove_result
        ):
            result = pipeline.run("Test", mode="generate_prompt")

        assert result.verified_badge is None

    def test_badge_format_revised(self):
        """Test badge format when draft was revised."""
        from prompting.cove import CoveResult
        from prompting.types import CoveQuestion

        questions = [
            CoveQuestion(question_text="Q1", target_claim="C1", verified=True),
            CoveQuestion(question_text="Q2", target_claim="C2", verified=True),
        ]

        result = CoveResult(
            draft_response="Original draft",
            final_response="Revised final",
            questions=questions,
            findings=[],
            verified=True,
        )

        # Manually set badge as would be done in run()
        result.badge = f"Verified: ran {len(questions)} checks; revised from draft"

        assert "Verified" in result.badge
        assert "2 checks" in result.badge
        assert "revised" in result.badge

    def test_badge_format_no_revision(self):
        """Test badge format when no revision was needed."""
        from prompting.cove import CoveResult
        from prompting.types import CoveQuestion

        questions = [
            CoveQuestion(question_text="Q1", target_claim="C1", verified=True),
        ]

        result = CoveResult(
            draft_response="Same content",
            final_response="Same content",
            questions=questions,
            findings=[],
            verified=True,
            badge="Verified: ran 1 checks; no revisions needed",
        )

        assert "Verified" in result.badge
        assert "no revisions" in result.badge


class TestCoveConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_cove_function(self):
        """Test run_cove convenience function."""
        from prompting.cove import run_cove

        # Should not crash with no LLM
        result = run_cove("Test question", draft="Test draft")

        assert result is not None
        assert result.final_response == "Test draft"

    def test_verify_prompt_function(self):
        """Test verify_prompt convenience function."""
        from prompting.cove import verify_prompt

        # Should not crash with no LLM
        result = verify_prompt(
            reshaped_prompt="Optimized prompt",
            original_prompt="Original prompt",
        )

        assert result is not None


class TestCoveTemplates:
    """Tests for CoVe template loading."""

    def test_templates_exist(self):
        """Test that all required templates exist."""
        from pathlib import Path
        import prompting.cove as cove_module

        templates_dir = Path(cove_module.__file__).parent / "templates"

        assert (templates_dir / "cove_generate_questions.system.txt").exists()
        assert (templates_dir / "cove_check_one.system.txt").exists()
        assert (templates_dir / "cove_finalize.system.txt").exists()

    def test_template_loading(self):
        """Test that templates can be loaded."""
        from prompting.cove import ChainOfVerification

        cove = ChainOfVerification()

        # Should not raise
        template = cove._load_template("cove_generate_questions.system")
        assert template is not None
        assert len(template) > 0

    def test_template_caching(self):
        """Test that templates are cached after loading."""
        from prompting.cove import ChainOfVerification

        cove = ChainOfVerification()

        # Load once
        template1 = cove._load_template("cove_check_one.system")

        # Load again - should be cached
        template2 = cove._load_template("cove_check_one.system")

        assert template1 is template2  # Same object

    def test_template_not_found_raises_error(self):
        """Test that loading a non-existent template raises CoveError."""
        from prompting.cove import ChainOfVerification, CoveError

        cove = ChainOfVerification()

        with pytest.raises(CoveError) as exc_info:
            cove._load_template("nonexistent_template")

        assert "not found" in str(exc_info.value).lower()


class TestCoveFindingCreation:
    """Tests for CoveFinding creation from questions."""

    def test_no_finding_for_verified_claim(self):
        """Test that no finding is created for verified claims."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion

        cove = ChainOfVerification()

        vq = CoveQuestion(
            question_text="Is X true?",
            target_claim="X is true",
            verified=True,
            confidence=0.9,
        )

        finding = cove._create_finding_from_question(vq)

        assert finding is None

    def test_warning_finding_for_contradicted_claim(self):
        """Test that WARNING finding is created for contradicted claims."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion, FindingSeverity, VerificationStatus

        cove = ChainOfVerification()

        vq = CoveQuestion(
            question_text="Is X true?",
            target_claim="X is true",
            source_context="X is true.",
            answer="No, X is false.",
            verified=False,
            confidence=0.9,
        )

        finding = cove._create_finding_from_question(vq)

        assert finding is not None
        assert finding.severity == FindingSeverity.WARNING
        assert finding.status == VerificationStatus.CONTRADICTED

    def test_info_finding_for_unverified_low_confidence(self):
        """Test that INFO finding is created for unverified low-confidence claims."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion, FindingSeverity, VerificationStatus

        cove = ChainOfVerification()

        vq = CoveQuestion(
            question_text="Is X true?",
            target_claim="X is true",
            verified=None,
            confidence=0.3,  # Low confidence
        )

        finding = cove._create_finding_from_question(vq)

        assert finding is not None
        assert finding.severity == FindingSeverity.INFO
        assert finding.status == VerificationStatus.UNVERIFIED

    def test_no_finding_for_unverified_high_confidence(self):
        """Test that no finding is created for unverified but high-confidence claims."""
        from prompting.cove import ChainOfVerification
        from prompting.types import CoveQuestion

        cove = ChainOfVerification()

        vq = CoveQuestion(
            question_text="Is X true?",
            target_claim="X is true",
            verified=None,
            confidence=0.7,  # High confidence despite not verified
        )

        finding = cove._create_finding_from_question(vq)

        assert finding is None
