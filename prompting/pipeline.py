"""
Prompting middleware pipeline.

Main entrypoint for the prompting middleware that orchestrates:
- Prompt reshaping (rewrite user input into optimized prompts)
- Chain-of-Verification (CoVe) for factual accuracy
- Debug artifact storage for tuning

Supports four modes:
- reshape_only: Just reshape the prompt (default)
- full_answer: Generate draft answer + CoVe verification
- generate_prompt: Reshape prompt + ALWAYS CoVe-verify the prompt itself
- generate_agent_prompt: Quality checks + ALWAYS CoVe for agent-facing prompts
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .classifier import ClassificationResult, classify_prompt
from .config import PromptingConfig
from .cove import ChainOfVerification, CoveResult, verify_prompt as cove_verify_prompt
from .memory_hook import MemoryHook, get_memory_hook
from .quality_checks import check_prompt_quality, revise_prompt_for_quality
from .reshape import ReshapeResult, reshape_user_input
from .types import (
    CoveFinding,
    CoveQuestion,
    InspectOutput,
    PipelineArtifacts,
    PipelineResult,
    PromptSpec,
)

logger = logging.getLogger(__name__)


class PromptingPipeline:
    """
    Main prompting middleware pipeline.

    Orchestrates prompt reshaping and Chain-of-Verification (CoVe)
    to improve prompt quality and response accuracy.

    Currently a scaffold implementation that passes through input
    unchanged. Future versions will add LLM-based reshaping and
    verification.

    Attributes:
        config: Pipeline configuration.
        memory_hook: Hook for storing artifacts to memory.
    """

    def __init__(
        self,
        config: Optional[PromptingConfig] = None,
        memory_hook: Optional[MemoryHook] = None,
        repo_root: Optional[Path] = None,
    ):
        """
        Initialize the prompting pipeline.

        Args:
            config: Pipeline configuration. Defaults to PromptingConfig.from_env().
            memory_hook: Memory hook for artifact storage. Defaults to global hook.
            repo_root: Repository root for memory backend.
        """
        self.config = config or PromptingConfig.from_env()
        self.memory_hook = memory_hook or get_memory_hook(repo_root=repo_root)
        self._repo_root = repo_root

    def run(
        self,
        user_input: str,
        request_id: Optional[str] = None,
        include_reshaped_prompt: bool = False,
        mode: str = "reshape_only",
    ) -> PipelineResult:
        """
        Run the prompting pipeline on user input.

        Pipeline stages:
        1. Check for inspect flag (/show_prompt or "inspect prompt")
        2. Intent classification
        3. Trivial check - bypass if trivial
        4. Prompt reshaping (if enabled and category matches)
        5. Mode-specific handling:
           - reshape_only: Return reshaped prompt as response
           - full_answer: Generate draft + CoVe verify
           - generate_prompt: ALWAYS CoVe-verify the reshaped prompt
        6. Artifact storage

        Args:
            user_input: The raw user input.
            request_id: Optional request ID for tracking.
            include_reshaped_prompt: Whether to include reshaped prompt in result.
            mode: Pipeline mode:
                - "reshape_only": Just reshape the prompt (default)
                - "full_answer": Generate draft answer + CoVe verify
                - "generate_prompt": ALWAYS CoVe-verify the reshaped prompt
                - "generate_agent_prompt": Quality checks + ALWAYS CoVe for agent prompts

        Returns:
            PipelineResult with the processed response.
        """
        request_id = request_id or str(uuid4())

        # Check for inspect flag in user input
        include_reshaped_prompt = include_reshaped_prompt or self._check_inspect_flag(
            user_input
        )

        # Strip inspect commands from user input for processing
        processed_input = self._strip_inspect_commands(user_input)

        # Classify the prompt
        classification = classify_prompt(processed_input)
        logger.debug(
            f"Classified prompt as '{classification.category}' "
            f"(confidence: {classification.confidence:.2f}, trivial: {classification.is_trivial})"
        )

        # Create artifacts container
        artifacts = PipelineArtifacts(
            request_id=request_id,
            metadata={
                "classification": {
                    "category": classification.category,
                    "confidence": classification.confidence,
                    "subcategories": classification.subcategories,
                    "is_trivial": classification.is_trivial,
                }
            },
        )

        # Check if pipeline should be bypassed
        if classification.is_trivial:
            logger.debug("Trivial request - bypassing pipeline")
            return self._create_passthrough_result(
                processed_input, request_id, artifacts, classification,
                include_reshaped_prompt=include_reshaped_prompt,
            )

        # Determine what pipeline stages to run
        should_reshape = self.config.should_reshape(classification.category)
        should_run_cove = self.config.should_run_cove(classification.category)

        logger.debug(
            f"Pipeline stages: reshape={should_reshape}, cove={should_run_cove}"
        )

        # Reshape the prompt (uses LLM if available, otherwise heuristics)
        prompt_spec = self._reshape_prompt(
            processed_input, classification, should_reshape, request_id
        )
        artifacts.prompt_spec = prompt_spec

        # Initialize variables for mode handling
        draft_response: str
        final_response: str
        verified_badge: Optional[str] = None

        # Handle different modes
        if mode == "reshape_only":
            # Just reshape - no LLM call for answer
            draft_response = prompt_spec.reshaped_prompt
            final_response = draft_response

        elif mode == "full_answer":
            # Generate draft answer via LLM, then CoVe verify
            cove = ChainOfVerification(
                config=self.config,
                memory_hook=self.memory_hook,
            )

            # Generate draft response
            try:
                draft_response = cove.generate_draft(prompt_spec.reshaped_prompt)
            except Exception as e:
                logger.warning(f"Draft generation failed, using reshaped prompt: {e}")
                draft_response = prompt_spec.reshaped_prompt

            artifacts.draft_response = draft_response

            # Run CoVe if enabled for this category
            if should_run_cove:
                try:
                    cove_result = cove.run(
                        user_input=prompt_spec.reshaped_prompt,
                        draft=draft_response,
                        request_id=request_id,
                    )
                    artifacts.cove_questions = cove_result.questions
                    artifacts.cove_findings = cove_result.findings
                    final_response = cove_result.final_response
                    if self.config.return_verified_badge:
                        verified_badge = cove_result.badge
                except Exception as e:
                    logger.warning(f"CoVe failed, returning draft: {e}")
                    final_response = draft_response
                    if self.config.return_verified_badge:
                        verified_badge = "Verification unavailable"
            else:
                final_response = draft_response

        elif mode == "generate_prompt":
            # ALWAYS CoVe-verify the reshaped prompt (regardless of should_run_cove)
            draft_response = prompt_spec.reshaped_prompt
            artifacts.draft_response = draft_response

            try:
                cove_result = cove_verify_prompt(
                    reshaped_prompt=prompt_spec.reshaped_prompt,
                    original_prompt=processed_input,
                    config=self.config,
                )
                artifacts.cove_questions = cove_result.questions
                artifacts.cove_findings = cove_result.findings
                final_response = cove_result.final_response
                if self.config.return_verified_badge:
                    verified_badge = cove_result.badge
            except Exception as e:
                logger.warning(f"Prompt verification failed: {e}")
                final_response = draft_response
                if self.config.return_verified_badge:
                    verified_badge = "Verification unavailable"

        elif mode == "generate_agent_prompt":
            # Agent-facing prompt generation with quality checks and ALWAYS CoVe
            draft_prompt = prompt_spec.reshaped_prompt
            draft_response = draft_prompt  # Set for later assignment to artifacts
            artifacts.draft_response = draft_prompt

            # Quality check with revision loop (max 2 retries)
            MAX_QUALITY_RETRIES = 2
            quality_attempts = 0
            for attempt in range(MAX_QUALITY_RETRIES + 1):
                quality_result = check_prompt_quality(draft_prompt)
                quality_attempts = attempt + 1
                if quality_result.passed:
                    logger.debug(f"Quality check passed on attempt {quality_attempts}")
                    break
                if attempt < MAX_QUALITY_RETRIES:
                    logger.debug(
                        f"Quality check failed (attempt {quality_attempts}), "
                        f"revising for: {quality_result.issues}"
                    )
                    draft_prompt = revise_prompt_for_quality(
                        draft_prompt, quality_result.issues
                    )
                else:
                    logger.warning(
                        f"Quality check still failing after {MAX_QUALITY_RETRIES} "
                        f"revision attempts: {quality_result.issues}"
                    )

            artifacts.metadata["quality_attempts"] = quality_attempts
            artifacts.metadata["quality_score"] = quality_result.score
            artifacts.metadata["quality_passed"] = quality_result.passed

            # ALWAYS run CoVe on agent prompts (regardless of config.should_run_cove)
            try:
                cove_result = cove_verify_prompt(
                    reshaped_prompt=draft_prompt,
                    original_prompt=processed_input,
                    config=self.config,
                )
                artifacts.cove_questions = cove_result.questions
                artifacts.cove_findings = cove_result.findings
                final_response = cove_result.final_response
                if self.config.return_verified_badge:
                    verified_badge = cove_result.badge
            except Exception as e:
                logger.warning(f"Agent prompt verification failed: {e}")
                final_response = draft_prompt
                if self.config.return_verified_badge:
                    verified_badge = "Verification unavailable"

        else:
            # Unknown mode - fall back to reshape_only behavior
            logger.warning(f"Unknown mode '{mode}', defaulting to reshape_only")
            draft_response = prompt_spec.reshaped_prompt
            final_response = draft_response

        artifacts.draft_response = draft_response
        artifacts.final_response = final_response

        # Store artifacts to memory if enabled
        if self.config.store_debug_artifacts:
            self._store_artifacts(artifacts)

        # Build result
        result = self._build_result(
            final_response,
            artifacts,
            include_reshaped_prompt,
            verified_badge=verified_badge,
        )

        return result

    def _check_inspect_flag(self, user_input: str) -> bool:
        """
        Check if user input contains an inspect flag.

        Recognized patterns:
        - /show_prompt
        - /inspect_prompt
        - "inspect prompt" or "show prompt" at end of input

        Args:
            user_input: The raw user input.

        Returns:
            True if inspect flag is present.
        """
        import re

        text = user_input.strip().lower()

        # Check for slash commands
        if "/show_prompt" in text or "/inspect_prompt" in text:
            return True

        # Check for natural language at end
        patterns = [
            r"\binspect\s+prompt\s*$",
            r"\bshow\s+prompt\s*$",
            r"\bshow\s+reshaped\s*$",
            r"\bshow\s+reshaped\s+prompt\s*$",
        ]
        return any(re.search(p, text) for p in patterns)

    def _strip_inspect_commands(self, user_input: str) -> str:
        """
        Remove inspect commands from user input.

        Args:
            user_input: The raw user input.

        Returns:
            User input with inspect commands removed.
        """
        import re

        text = user_input.strip()

        # Remove slash commands
        text = re.sub(r"\s*/show_prompt\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*/inspect_prompt\b", "", text, flags=re.IGNORECASE)

        # Remove natural language commands at end
        text = re.sub(r"\s+inspect\s+prompt\s*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+show\s+prompt\s*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+show\s+reshaped(\s+prompt)?\s*$", "", text, flags=re.IGNORECASE)

        return text.strip()

    def _reshape_prompt(
        self,
        user_input: str,
        classification: ClassificationResult,
        should_reshape: bool,
        request_id: str,
    ) -> PromptSpec:
        """
        Reshape the user input into an optimized prompt.

        Uses LLM-based reshaping when available, falls back to
        deterministic heuristics.

        Args:
            user_input: Original user input.
            classification: Classification result.
            should_reshape: Whether reshaping is enabled for this category.
            request_id: Request ID for tracking.

        Returns:
            PromptSpec with original and reshaped prompt.
        """
        if not should_reshape:
            # No reshaping requested - return unchanged
            return PromptSpec(
                original_prompt=user_input,
                reshaped_prompt=user_input,
                category=classification.category,
                transformations_applied=[],
                request_id=request_id,
            )

        # Perform actual reshaping
        try:
            result: ReshapeResult = reshape_user_input(
                user_input,
                classification=classification,
            )

            return PromptSpec(
                original_prompt=user_input,
                reshaped_prompt=result.reshaped_prompt,
                category=classification.category,
                transformations_applied=result.transformations,
                constraints=result.constraints,
                required_outputs=result.required_outputs,
                non_goals=result.non_goals,
                confidence=result.confidence,
                used_llm=result.used_llm,
                request_id=request_id,
            )

        except Exception as e:
            logger.warning(f"Reshaping failed, returning original: {e}")
            return PromptSpec(
                original_prompt=user_input,
                reshaped_prompt=user_input,
                category=classification.category,
                transformations_applied=["reshape_failed"],
                request_id=request_id,
            )

    def _run_cove(
        self,
        user_input: str,
        draft_response: str,
        classification: ClassificationResult,
        request_id: str,
    ) -> tuple[list[CoveQuestion], list[CoveFinding]]:
        """
        Run Chain-of-Verification on the draft response.

        Args:
            user_input: The original user input (for context).
            draft_response: The draft response to verify.
            classification: Classification result.
            request_id: Request ID for tracking.

        Returns:
            Tuple of (questions, findings).
        """
        cove = ChainOfVerification(
            config=self.config,
            memory_hook=self.memory_hook,
        )

        try:
            result = cove.run(
                user_input=user_input,
                draft=draft_response,
                request_id=request_id,
            )
            return result.questions, result.findings
        except Exception as e:
            logger.warning(f"CoVe failed: {e}")
            return [], []

    def _store_artifacts(self, artifacts: PipelineArtifacts) -> None:
        """
        Store pipeline artifacts to memory.

        Args:
            artifacts: The artifacts to store.
        """
        try:
            stored_ids = self.memory_hook.store_pipeline_result(artifacts)
            if stored_ids:
                logger.debug(f"Stored {len(stored_ids)} artifact(s) to memory")
        except Exception as e:
            # Don't fail the pipeline if storage fails
            logger.warning(f"Failed to store artifacts: {e}")

    def _build_result(
        self,
        response: str,
        artifacts: PipelineArtifacts,
        include_reshaped_prompt: bool,
        verified_badge: Optional[str] = None,
    ) -> PipelineResult:
        """
        Build the final pipeline result.

        Args:
            response: The final response text.
            artifacts: Pipeline artifacts.
            include_reshaped_prompt: Whether to include reshaped prompt.
            verified_badge: Optional pre-computed verified badge.

        Returns:
            PipelineResult with appropriate fields populated.
        """
        # Determine if verified
        verified = artifacts.has_verification() and artifacts.verification_passed()

        # Use passed badge if provided, otherwise generate from artifacts
        if verified_badge is None and verified and self.config.return_verified_badge:
            verified_badge = self._generate_verified_badge(artifacts)

        # Include reshaped prompt if allowed and requested, using InspectOutput
        reshaped_prompt: Optional[str] = None
        if include_reshaped_prompt and self.config.allow_user_inspect_reshaped_prompt:
            if artifacts.prompt_spec:
                spec = artifacts.prompt_spec
                # Build InspectOutput with verification details (never shows chain-of-thought)
                inspect_obj = InspectOutput(
                    original_prompt=spec.original_prompt,
                    reshaped_prompt=spec.reshaped_prompt,
                    verification_questions=[q.question_text for q in artifacts.cove_questions],
                    findings_summary=[f.description for f in artifacts.cove_findings],
                    badge=verified_badge,
                )
                reshaped_prompt = inspect_obj.format()

        # Include artifacts if debug storage is enabled
        result_artifacts: Optional[PipelineArtifacts] = None
        if self.config.store_debug_artifacts:
            result_artifacts = artifacts

        return PipelineResult(
            response=response,
            verified=verified,
            verified_badge=verified_badge,
            reshaped_prompt=reshaped_prompt,
            artifacts=result_artifacts,
            request_id=artifacts.request_id,
        )

    def _generate_verified_badge(self, artifacts: PipelineArtifacts) -> str:
        """
        Generate a verified badge/summary.

        Args:
            artifacts: Pipeline artifacts with verification results.

        Returns:
            Verified badge string.
        """
        questions_count = len(artifacts.cove_questions)
        verified_count = sum(1 for q in artifacts.cove_questions if q.verified)

        if questions_count == 0:
            return "✓ Verified"

        return f"✓ Verified ({verified_count}/{questions_count} checks passed)"

    def _create_passthrough_result(
        self,
        user_input: str,
        request_id: str,
        artifacts: PipelineArtifacts,
        classification: ClassificationResult,
        include_reshaped_prompt: bool = False,
    ) -> PipelineResult:
        """
        Create a passthrough result for trivial or bypassed requests.

        Args:
            user_input: Original user input.
            request_id: Request ID.
            artifacts: Artifacts container.
            classification: Classification result.
            include_reshaped_prompt: Whether to include reshaped prompt metadata.

        Returns:
            PipelineResult with input unchanged.
        """
        prompt_spec = PromptSpec(
            original_prompt=user_input,
            reshaped_prompt=user_input,
            category=classification.category,
            transformations_applied=["passthrough"],
            request_id=request_id,
        )
        artifacts.prompt_spec = prompt_spec
        artifacts.draft_response = user_input
        artifacts.final_response = user_input

        # Include reshaped prompt metadata if requested (even for passthrough)
        reshaped_prompt_metadata: Optional[str] = None
        if include_reshaped_prompt and self.config.allow_user_inspect_reshaped_prompt:
            reshaped_prompt_metadata = (
                f"[Passthrough - no reshaping applied]\n"
                f"Category: {classification.category}\n"
                f"Is trivial: {classification.is_trivial}"
            )

        return PipelineResult(
            response=user_input,
            verified=False,
            verified_badge=None,
            reshaped_prompt=reshaped_prompt_metadata,
            artifacts=artifacts if self.config.store_debug_artifacts else None,
            request_id=request_id,
        )


# Convenience function for simple usage
def run_pipeline(
    user_input: str,
    config: Optional[PromptingConfig] = None,
    request_id: Optional[str] = None,
    include_reshaped_prompt: bool = False,
    mode: str = "reshape_only",
) -> PipelineResult:
    """
    Run the prompting pipeline on user input.

    Convenience function that creates a pipeline and runs it.

    Args:
        user_input: The raw user input.
        config: Optional pipeline configuration.
        request_id: Optional request ID for tracking.
        include_reshaped_prompt: Whether to include reshaped prompt in result.
        mode: Pipeline mode:
            - "reshape_only": Just reshape the prompt (default)
            - "full_answer": Generate draft answer + CoVe verify
            - "generate_prompt": ALWAYS CoVe-verify the reshaped prompt
            - "generate_agent_prompt": Quality checks + ALWAYS CoVe for agent prompts

    Returns:
        PipelineResult from the pipeline.
    """
    pipeline = PromptingPipeline(config=config)
    return pipeline.run(
        user_input,
        request_id=request_id,
        include_reshaped_prompt=include_reshaped_prompt,
        mode=mode,
    )
