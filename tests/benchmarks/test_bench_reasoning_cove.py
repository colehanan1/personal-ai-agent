"""
Tests for CoVe reasoning benchmark tier.

Tests CoVe evaluation with mocked backend responses.
"""
import pytest
from unittest.mock import Mock

from benchmarks.tiers.reasoning_cove import (
    CoveEvaluator,
    CoveTestCase,
    CoveEvaluation,
    DEFAULT_COVE_TEST_CASES,
)
from benchmarks.backends.base import InferenceResult


class TestCoveTestCase:
    """Test CoveTestCase dataclass."""
    
    def test_basic_test_case(self):
        """Test creating a test case."""
        test_case = CoveTestCase(
            id="test1",
            question="What is 2+2?",
            draft_response="2+2 equals 5.",
            expected_issues=["Incorrect calculation"],
        )
        
        assert test_case.id == "test1"
        assert test_case.question == "What is 2+2?"
        assert len(test_case.expected_issues) == 1


class TestCoveEvaluator:
    """Test CoveEvaluator."""
    
    def test_initialization(self):
        """Test evaluator initialization."""
        mock_backend = Mock()
        evaluator = CoveEvaluator(backend=mock_backend)
        
        assert evaluator.backend == mock_backend
    
    def test_evaluate_test_case_perfect(self):
        """Test evaluation with perfect verification."""
        mock_backend = Mock()
        
        # Mock verification question generation
        mock_backend.run_inference.side_effect = [
            # First call: generate questions
            InferenceResult(
                prompt="",
                response="1. Is Sydney the capital of Australia?\n2. What is the actual capital?\n3. Are you sure?",
            ),
            # Subsequent calls: answer questions (indicating issues)
            InferenceResult(prompt="", response="No, Sydney is not the capital."),
            InferenceResult(prompt="", response="The capital is Canberra."),
            InferenceResult(prompt="", response="Yes, Canberra is definitely the capital."),
        ]
        
        evaluator = CoveEvaluator(backend=mock_backend)
        
        test_case = CoveTestCase(
            id="test1",
            question="What is the capital of Australia?",
            draft_response="The capital is Sydney.",
            expected_issues=["Sydney is not capital"],
        )
        
        result = evaluator.evaluate_test_case(test_case)
        
        assert result.test_case_id == "test1"
        assert result.verification_questions_generated >= 2
        assert result.issues_found > 0
        assert result.expected_issues == 1
    
    def test_evaluate_test_case_no_issues(self):
        """Test evaluation with correct response."""
        mock_backend = Mock()
        
        # Mock responses that don't indicate issues
        mock_backend.run_inference.side_effect = [
            # Generate questions
            InferenceResult(
                prompt="",
                response="1. Where is Paris located?\n2. What country has Paris as capital?",
            ),
            # Answer questions (no issues - affirmative, no negation words)
            InferenceResult(prompt="", response="Paris is the capital of France."),
            InferenceResult(prompt="", response="France has Paris as the capital."),
        ]
        
        evaluator = CoveEvaluator(backend=mock_backend)
        
        test_case = CoveTestCase(
            id="test2",
            question="What is the capital of France?",
            draft_response="The capital is Paris.",
            expected_issues=[],  # No issues expected
        )
        
        result = evaluator.evaluate_test_case(test_case)
        
        assert result.test_case_id == "test2"
        assert result.passed is True  # Should pass if no issues expected
    
    def test_evaluate_multiple_cases(self):
        """Test evaluating multiple test cases."""
        mock_backend = Mock()
        
        # Simple mock that always generates questions and finds issues
        def mock_inference(prompt, **kwargs):
            if "generate" in prompt.lower() or "verification" in prompt.lower():
                return InferenceResult(
                    prompt=prompt,
                    response="1. Is this correct?\n2. Are you sure?",
                )
            else:
                return InferenceResult(
                    prompt=prompt,
                    response="No, that is incorrect.",
                )
        
        mock_backend.run_inference.side_effect = mock_inference
        
        evaluator = CoveEvaluator(backend=mock_backend)
        
        test_cases = [
            CoveTestCase(
                id="t1",
                question="Q1",
                draft_response="R1",
                expected_issues=["Issue 1"],
            ),
            CoveTestCase(
                id="t2",
                question="Q2",
                draft_response="R2",
                expected_issues=["Issue 2"],
            ),
        ]
        
        results = evaluator.evaluate(test_cases)
        
        assert results["total_cases"] == 2
        assert "pass_rate" in results
        assert "results" in results
        assert len(results["results"]) == 2
    
    def test_evaluate_with_backend_error(self):
        """Test evaluation when backend returns errors."""
        mock_backend = Mock()
        mock_backend.run_inference.return_value = InferenceResult(
            prompt="",
            response="",
            error="Backend connection failed",
        )
        
        evaluator = CoveEvaluator(backend=mock_backend)
        
        test_case = CoveTestCase(
            id="test3",
            question="Test",
            draft_response="Test",
            expected_issues=[],
        )
        
        result = evaluator.evaluate_test_case(test_case)
        
        assert result.passed is False
        assert result.verification_questions_generated == 0
    
    def test_default_test_cases_exist(self):
        """Test that default test cases are defined."""
        assert len(DEFAULT_COVE_TEST_CASES) > 0
        
        for test_case in DEFAULT_COVE_TEST_CASES:
            assert test_case.id
            assert test_case.question
            assert test_case.draft_response
            assert isinstance(test_case.expected_issues, list)


class TestCoveIssueDetection:
    """Test issue detection logic."""
    
    def test_detect_issues_with_negation(self):
        """Test that negations are detected as issues."""
        mock_backend = Mock()
        evaluator = CoveEvaluator(backend=mock_backend)
        
        answers = [
            {"question": "Is X correct?", "answer": "No, X is incorrect.", "error": None},
            {"question": "Is Y valid?", "answer": "Y is not valid.", "error": None},
        ]
        
        issues = evaluator._detect_issues(answers)
        
        assert len(issues) == 2
    
    def test_detect_no_issues(self):
        """Test that affirmative answers don't create issues."""
        mock_backend = Mock()
        evaluator = CoveEvaluator(backend=mock_backend)
        
        answers = [
            {"question": "Is X correct?", "answer": "Yes, X is correct.", "error": None},
            {"question": "Is Y valid?", "answer": "Y is completely valid.", "error": None},
        ]
        
        issues = evaluator._detect_issues(answers)
        
        assert len(issues) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
