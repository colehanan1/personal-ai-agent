"""
Chain-of-Verification (CoVe) reasoning benchmark tier.

Evaluates model reasoning quality using Chain-of-Verification methodology.
Measures pass rate for verification tasks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from benchmarks.backends.base import BenchmarkBackend

logger = logging.getLogger(__name__)


@dataclass
class CoveTestCase:
    """A single CoVe test case."""
    id: str
    question: str
    draft_response: str
    expected_issues: List[str]  # List of expected verification issues
    category: str = "reasoning"


@dataclass
class CoveEvaluation:
    """Result of CoVe evaluation."""
    test_case_id: str
    passed: bool
    verification_questions_generated: int
    issues_found: int
    expected_issues: int
    error: Optional[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


class CoveEvaluator:
    """
    Evaluator for Chain-of-Verification reasoning.
    
    Runs CoVe verification on test cases and measures pass rate.
    """
    
    def __init__(
        self,
        backend: BenchmarkBackend,
        llm_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize CoVe evaluator.
        
        Args:
            backend: Backend for inference
            llm_url: URL of LLM API (optional, defaults to backend URL)
            model_name: Model name for CoVe verification
        """
        self.backend = backend
        self.llm_url = llm_url
        self.model_name = model_name
    
    def evaluate_test_case(self, test_case: CoveTestCase) -> CoveEvaluation:
        """
        Evaluate a single CoVe test case.
        
        Args:
            test_case: Test case to evaluate
        
        Returns:
            CoveEvaluation result
        """
        try:
            # Generate verification questions
            questions = self._generate_verification_questions(
                test_case.question,
                test_case.draft_response
            )
            
            if not questions:
                return CoveEvaluation(
                    test_case_id=test_case.id,
                    passed=False,
                    verification_questions_generated=0,
                    issues_found=0,
                    expected_issues=len(test_case.expected_issues),
                    error="No verification questions generated",
                )
            
            # Answer verification questions
            answers = self._answer_verification_questions(questions)
            
            # Check for issues
            issues_found = self._detect_issues(answers)
            
            # Determine pass/fail
            # Pass if we found at least some of the expected issues
            expected_count = len(test_case.expected_issues)
            found_count = len(issues_found)
            
            # Consider it a pass if we found at least 50% of expected issues
            # or if there were no expected issues and we found none
            if expected_count == 0:
                passed = found_count == 0
            else:
                passed = found_count >= (expected_count * 0.5)
            
            return CoveEvaluation(
                test_case_id=test_case.id,
                passed=passed,
                verification_questions_generated=len(questions),
                issues_found=found_count,
                expected_issues=expected_count,
                details={
                    "questions": questions,
                    "issues": issues_found,
                },
            )
        
        except Exception as e:
            logger.error(f"CoVe evaluation failed for {test_case.id}: {e}")
            return CoveEvaluation(
                test_case_id=test_case.id,
                passed=False,
                verification_questions_generated=0,
                issues_found=0,
                expected_issues=len(test_case.expected_issues),
                error=str(e),
            )
    
    def _generate_verification_questions(
        self,
        question: str,
        draft_response: str,
        num_questions: int = 3,
    ) -> List[str]:
        """
        Generate verification questions for a draft response.
        
        Args:
            question: Original question
            draft_response: Draft response to verify
            num_questions: Number of questions to generate
        
        Returns:
            List of verification questions
        """
        prompt = f"""Given this question and draft answer, generate {num_questions} verification questions to check the accuracy of the claims made.

Question: {question}

Draft Answer: {draft_response}

Generate verification questions that would help identify any factual errors or unsupported claims. List them one per line."""
        
        result = self.backend.run_inference(
            prompt=prompt,
            max_tokens=200,
            temperature=0.3,
        )
        
        if result.error:
            logger.warning(f"Failed to generate verification questions: {result.error}")
            return []
        
        # Parse questions from response
        questions = []
        for line in result.response.split('\n'):
            line = line.strip()
            # Remove numbering and question markers
            line = line.lstrip('0123456789.-) ')
            if line and len(line) > 10 and '?' in line:
                questions.append(line)
        
        return questions[:num_questions]
    
    def _answer_verification_questions(
        self,
        questions: List[str],
    ) -> List[Dict[str, str]]:
        """
        Answer verification questions independently.
        
        Args:
            questions: List of verification questions
        
        Returns:
            List of question-answer pairs
        """
        answers = []
        for question in questions:
            result = self.backend.run_inference(
                prompt=question,
                max_tokens=100,
                temperature=0.0,
            )
            
            answers.append({
                "question": question,
                "answer": result.response if not result.error else "[Error]",
                "error": result.error,
            })
        
        return answers
    
    def _detect_issues(
        self,
        answers: List[Dict[str, str]],
    ) -> List[str]:
        """
        Detect issues from verification answers.
        
        Args:
            answers: List of verification question answers
        
        Returns:
            List of detected issues
        """
        issues = []
        
        for qa in answers:
            answer = qa["answer"].lower()
            
            # Simple heuristic: look for negations, corrections, or uncertainties
            issue_indicators = [
                "no", "not", "incorrect", "wrong", "false", "inaccurate",
                "unclear", "uncertain", "cannot", "unable", "insufficient",
                "lacks", "missing", "error", "mistake",
            ]
            
            if any(indicator in answer for indicator in issue_indicators):
                issues.append(qa["question"])
        
        return issues
    
    def evaluate(
        self,
        test_cases: List[CoveTestCase],
    ) -> Dict[str, Any]:
        """
        Evaluate multiple CoVe test cases.
        
        Args:
            test_cases: List of test cases
        
        Returns:
            Dictionary with pass rate and details
        """
        if not test_cases:
            return {
                "pass_rate": 0.0,
                "total_cases": 0,
                "passed": 0,
                "failed": 0,
                "error": "No test cases provided",
            }
        
        results = []
        passed_count = 0
        
        for test_case in test_cases:
            evaluation = self.evaluate_test_case(test_case)
            results.append(evaluation)
            
            if evaluation.passed:
                passed_count += 1
        
        total = len(test_cases)
        pass_rate = (passed_count / total) * 100 if total > 0 else 0.0
        
        return {
            "pass_rate": pass_rate,
            "total_cases": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "results": results,
        }


# Default CoVe test cases
DEFAULT_COVE_TEST_CASES = [
    CoveTestCase(
        id="capitals_error",
        question="What is the capital of Australia?",
        draft_response="The capital of Australia is Sydney.",
        expected_issues=["Sydney is not the capital, Canberra is"],
        category="factual",
    ),
    CoveTestCase(
        id="year_error",
        question="When did World War II end?",
        draft_response="World War II ended in 1944.",
        expected_issues=["Ended in 1945, not 1944"],
        category="factual",
    ),
    CoveTestCase(
        id="math_error",
        question="What is 15 * 12?",
        draft_response="15 multiplied by 12 equals 190.",
        expected_issues=["15 * 12 = 180, not 190"],
        category="reasoning",
    ),
]
