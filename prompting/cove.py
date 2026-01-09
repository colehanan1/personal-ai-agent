"""
Chain-of-Verification (CoVe) module for the prompting middleware.

Implements multi-step verification to improve factual accuracy:
1. Generate draft response
2. Generate verification questions
3. Answer questions independently
4. Finalize answer with corrections

Gracefully degrades when LLM unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import requests

from .config import PromptingConfig
from .types import (
    CoveFinding,
    CoveQuestion,
    FindingSeverity,
    PipelineArtifacts,
    VerificationStatus,
)

if TYPE_CHECKING:
    from .memory_hook import MemoryHook

logger = logging.getLogger(__name__)

# Template directory relative to this module
TEMPLATES_DIR = Path(__file__).parent / "templates"


class CoveError(Exception):
    """Error during CoVe processing."""

    pass


@dataclass
class CoveResult:
    """
    Result of Chain-of-Verification process.

    Attributes:
        draft_response: The initial draft response.
        final_response: The finalized response after verification.
        questions: List of verification questions generated.
        findings: List of verification findings.
        verified: Whether verification passed without critical issues.
        badge: Verification badge string for metadata.
        error: Error message if CoVe failed.
    """

    draft_response: str
    final_response: str
    questions: list[CoveQuestion] = field(default_factory=list)
    findings: list[CoveFinding] = field(default_factory=list)
    verified: bool = False
    badge: Optional[str] = None
    error: Optional[str] = None

    def is_revised(self) -> bool:
        """Check if the final response differs from the draft."""
        return self.draft_response.strip() != self.final_response.strip()


class ChainOfVerification:
    """
    Chain-of-Verification implementation.

    Orchestrates the multi-step verification process:
    1. Generate draft response (optional, if not provided)
    2. Generate verification questions from draft
    3. Answer each question independently
    4. Finalize answer incorporating findings

    Attributes:
        config: Pipeline configuration.
        llm_url: LLM API URL.
        model_name: Model name for LLM calls.
        memory_hook: Optional memory hook for artifact storage.
    """

    def __init__(
        self,
        config: Optional[PromptingConfig] = None,
        llm_url: Optional[str] = None,
        model_name: Optional[str] = None,
        memory_hook: Optional["MemoryHook"] = None,
    ):
        """
        Initialize ChainOfVerification.

        Args:
            config: Pipeline configuration. Defaults to PromptingConfig.from_env().
            llm_url: LLM API URL. Defaults to env var.
            model_name: Model name. Defaults to env var.
            memory_hook: Memory hook for artifact storage.
        """
        self.config = config or PromptingConfig.from_env()
        self.llm_url = (
            llm_url or os.getenv("LLM_API_URL") or os.getenv("OLLAMA_API_URL")
        )
        self.model_name = (
            model_name or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL")
        )
        self.memory_hook = memory_hook
        self._llm_available: Optional[bool] = None
        self._templates: dict[str, str] = {}

    def is_llm_available(self) -> bool:
        """Check if LLM backend is reachable."""
        if self._llm_available is not None:
            return self._llm_available

        if not self.llm_url or not self.model_name:
            self._llm_available = False
            return False

        try:
            url = f"{self.llm_url.rstrip('/')}/v1/models"
            response = requests.get(url, timeout=5)
            self._llm_available = response.status_code == 200
        except Exception:
            self._llm_available = False

        return self._llm_available

    def _load_template(self, name: str) -> str:
        """
        Load a template file by name.

        Args:
            name: Template name (without .txt extension).

        Returns:
            Template content.

        Raises:
            CoveError: If template not found.
        """
        if name in self._templates:
            return self._templates[name]

        template_path = TEMPLATES_DIR / f"{name}.txt"
        if not template_path.exists():
            raise CoveError(f"Template not found: {template_path}")

        content = template_path.read_text()
        self._templates[name] = content
        return content

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        """
        Make an LLM API call.

        Args:
            system_prompt: System message content.
            user_prompt: User message content.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            Response content string.

        Raises:
            CoveError: If LLM call fails.
        """
        if not self.is_llm_available():
            raise CoveError("LLM not available")

        url = f"{self.llm_url.rstrip('/')}/v1/chat/completions"
        api_key = os.getenv("LLM_API_KEY") or os.getenv("VLLM_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = requests.post(url, json=payload, timeout=60, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            raise CoveError(f"LLM request failed: {e}")
        except (KeyError, IndexError) as e:
            raise CoveError(f"Invalid LLM response format: {e}")

    def generate_draft(
        self,
        user_input: str,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Generate a draft response for the user input.

        Args:
            user_input: The user's question/request.
            context: Optional context dictionary.

        Returns:
            Draft response string.

        Raises:
            CoveError: If draft generation fails.
        """
        system_prompt = (
            "You are a helpful assistant. Answer the user's question "
            "accurately and concisely. Provide factual information."
        )

        user_prompt = user_input
        if context:
            user_prompt = f"Context: {json.dumps(context)}\n\nQuestion: {user_input}"

        return self._call_llm(
            system_prompt, user_prompt, max_tokens=1000, temperature=0.7
        )

    def generate_verification_questions(
        self,
        question: str,
        draft: str,
        k: Optional[int] = None,
    ) -> list[CoveQuestion]:
        """
        Generate k verification questions from the draft response.

        Args:
            question: The original user question.
            draft: The draft response to verify.
            k: Number of questions to generate. Defaults to config midpoint.

        Returns:
            List of CoveQuestion objects.
        """
        # Determine number of questions
        min_k = self.config.cove_min_questions
        max_k = self.config.cove_max_questions
        if k is None:
            k = (min_k + max_k) // 2
        k = max(min_k, min(max_k, k))  # Clamp to bounds

        if not self.is_llm_available():
            logger.warning("LLM not available - returning empty questions")
            return []

        try:
            template = self._load_template("cove_generate_questions.system")
            system_prompt = template.format(k=k, min_k=min_k, max_k=max_k)

            user_prompt = f"Original question: {question}\n\nDraft response:\n{draft}"

            content = self._call_llm(system_prompt, user_prompt, max_tokens=800)

            # Parse JSON response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if not json_match:
                logger.warning("No JSON found in question generation response")
                return []

            data = json.loads(json_match.group())
            questions_data = data.get("questions", [])

            # Convert to CoveQuestion objects, respecting bounds
            questions = []
            for q_data in questions_data[:max_k]:
                questions.append(
                    CoveQuestion(
                        question_text=q_data.get("question_text", ""),
                        target_claim=q_data.get("target_claim", ""),
                        source_context=q_data.get("source_context", ""),
                    )
                )

            # Ensure minimum questions (pad with generic if needed)
            while len(questions) < min_k:
                questions.append(
                    CoveQuestion(
                        question_text="Is the information accurate?",
                        target_claim="General accuracy check",
                        source_context="",
                    )
                )

            return questions

        except (CoveError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to generate verification questions: {e}")
            return []

    def answer_verification_question_independently(
        self,
        vq: CoveQuestion,
    ) -> CoveQuestion:
        """
        Answer a verification question independently (without seeing draft).

        Args:
            vq: The CoveQuestion to answer.

        Returns:
            The CoveQuestion with answer, verified, and confidence populated.
        """
        if not self.is_llm_available():
            vq.answer = "Verification unavailable - LLM not accessible"
            vq.verified = None
            vq.confidence = 0.0
            return vq

        try:
            template = self._load_template("cove_check_one.system")

            user_prompt = f"Question: {vq.question_text}"

            content = self._call_llm(template, user_prompt, max_tokens=200)

            # Parse JSON response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json.loads(json_match.group())
                vq.answer = data.get("answer", content)
                vq.verified = data.get("verified", None)
                vq.confidence = data.get("confidence", 0.5)
            else:
                # Fallback: use raw content as answer
                vq.answer = content.strip()
                vq.verified = None
                vq.confidence = 0.5

        except (CoveError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to answer verification question: {e}")
            vq.answer = f"Verification failed: {e}"
            vq.verified = None
            vq.confidence = 0.0

        return vq

    def finalize_answer(
        self,
        question: str,
        draft: str,
        findings: list[tuple[CoveQuestion, Optional[CoveFinding]]],
    ) -> tuple[str, list[CoveFinding]]:
        """
        Produce final answer incorporating verification findings.

        Args:
            question: Original user question.
            draft: Draft response.
            findings: List of (question, finding) tuples from verification.

        Returns:
            Tuple of (final_response, findings_list).
        """
        cove_findings: list[CoveFinding] = []

        # Extract findings from tuples
        for vq, finding in findings:
            if finding:
                cove_findings.append(finding)

        if not self.is_llm_available():
            # Return draft unchanged with unavailable badge
            return draft, cove_findings

        try:
            template = self._load_template("cove_finalize.system")

            # Build verification summary
            verification_summary = []
            for vq, finding in findings:
                status = (
                    "PASSED"
                    if vq.verified
                    else "NEEDS_REVIEW" if vq.verified is None else "FAILED"
                )
                verification_summary.append(
                    f"Claim: {vq.target_claim}\n"
                    f"Verification: {vq.answer}\n"
                    f"Status: {status}\n"
                )

            user_prompt = (
                f"Original question: {question}\n\n"
                f"Draft response:\n{draft}\n\n"
                f"Verification results:\n" + "\n".join(verification_summary)
            )

            final_response = self._call_llm(template, user_prompt, max_tokens=1200)
            return final_response.strip(), cove_findings

        except CoveError as e:
            logger.warning(f"Failed to finalize answer: {e}")
            # Return draft unchanged
            return draft, cove_findings

    def _create_finding_from_question(
        self,
        vq: CoveQuestion,
    ) -> Optional[CoveFinding]:
        """
        Create a CoveFinding from an answered verification question.

        Args:
            vq: Answered CoveQuestion.

        Returns:
            CoveFinding if there's something notable, None otherwise.
        """
        if vq.verified is True:
            return None  # No finding needed for verified claims

        if vq.verified is False:
            return CoveFinding(
                description=f"Claim may be inaccurate: {vq.target_claim}",
                severity=FindingSeverity.WARNING,
                status=VerificationStatus.CONTRADICTED,
                question_id=vq.question_id,
                original_text=vq.source_context,
                suggested_correction=vq.answer,
                evidence=[vq.answer] if vq.answer else [],
            )

        if vq.verified is None and vq.confidence < 0.5:
            return CoveFinding(
                description=f"Could not verify claim: {vq.target_claim}",
                severity=FindingSeverity.INFO,
                status=VerificationStatus.UNVERIFIED,
                question_id=vq.question_id,
                original_text=vq.source_context,
            )

        return None

    def run(
        self,
        user_input: str,
        draft: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> CoveResult:
        """
        Run the full Chain-of-Verification process.

        Args:
            user_input: The user's question/request.
            draft: Optional pre-generated draft response.
            context: Optional context dictionary.
            request_id: Request ID for tracking.

        Returns:
            CoveResult with verification results.
        """
        # Generate draft if not provided
        if draft is None:
            try:
                draft = self.generate_draft(user_input, context)
            except CoveError as e:
                return CoveResult(
                    draft_response="",
                    final_response="",
                    error=f"Failed to generate draft: {e}",
                    badge="Verification unavailable",
                )

        # Generate verification questions
        questions = self.generate_verification_questions(user_input, draft)

        if not questions:
            # No questions generated - return draft as-is
            return CoveResult(
                draft_response=draft,
                final_response=draft,
                questions=[],
                findings=[],
                verified=True,
                badge="Verified: no claims to check",
            )

        # Answer each question independently
        findings_pairs: list[tuple[CoveQuestion, Optional[CoveFinding]]] = []
        for vq in questions:
            vq = self.answer_verification_question_independently(vq)
            finding = self._create_finding_from_question(vq)
            findings_pairs.append((vq, finding))

        # Finalize answer
        final_response, cove_findings = self.finalize_answer(
            user_input, draft, findings_pairs
        )

        # Determine verification status
        critical_findings = [f for f in cove_findings if f.is_critical()]
        verified = len(critical_findings) == 0

        # Generate badge
        if verified:
            revised = draft.strip() != final_response.strip()
            if revised:
                badge = f"Verified: ran {len(questions)} checks; revised from draft"
            else:
                badge = f"Verified: ran {len(questions)} checks; no revisions needed"
        else:
            badge = f"Verification: {len(critical_findings)} issue(s) found"

        # Store artifacts if memory hook available
        if self.memory_hook and self.config.store_debug_artifacts:
            artifacts = PipelineArtifacts(
                request_id=request_id or "",
                draft_response=draft,
                cove_questions=questions,
                cove_findings=cove_findings,
                final_response=final_response,
            )
            try:
                self.memory_hook.store_verification_artifacts(artifacts)
            except Exception as e:
                logger.warning(f"Failed to store CoVe artifacts: {e}")

        return CoveResult(
            draft_response=draft,
            final_response=final_response,
            questions=questions,
            findings=cove_findings,
            verified=verified,
            badge=badge,
        )


# Convenience functions


def run_cove(
    user_input: str,
    draft: Optional[str] = None,
    config: Optional[PromptingConfig] = None,
) -> CoveResult:
    """
    Run Chain-of-Verification on user input.

    Convenience function that creates a ChainOfVerification and runs it.

    Args:
        user_input: The user's question/request.
        draft: Optional pre-generated draft response.
        config: Optional pipeline configuration.

    Returns:
        CoveResult with verification results.
    """
    cove = ChainOfVerification(config=config)
    return cove.run(user_input, draft=draft)


def verify_prompt(
    reshaped_prompt: str,
    original_prompt: str,
    config: Optional[PromptingConfig] = None,
) -> CoveResult:
    """
    Verify a reshaped prompt for clarity, completeness, and correctness.

    Used in mode="generate_prompt" to verify the prompt itself.

    Args:
        reshaped_prompt: The reshaped prompt to verify.
        original_prompt: The original user prompt.
        config: Optional pipeline configuration.

    Returns:
        CoveResult with verification of the prompt.
    """
    verification_request = (
        f"Verify this reshaped prompt preserves the user's intent:\n"
        f"Original: {original_prompt}\n"
        f"Reshaped: {reshaped_prompt}"
    )

    cove = ChainOfVerification(config=config)
    return cove.run(
        user_input=verification_request,
        draft=reshaped_prompt,
    )
