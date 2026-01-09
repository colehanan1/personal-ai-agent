"""
Type definitions for the prompting middleware pipeline.

Provides typed dataclasses for:
- PromptSpec: Specification for a reshaped prompt
- CoveQuestion: A verification question in the CoVe pipeline
- CoveFinding: A finding from verification
- PipelineArtifacts: Debug artifacts from the pipeline
- PipelineResult: Final result from the pipeline
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


def _now_utc() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    """Generate a unique ID for artifacts."""
    return str(uuid4())


class VerificationStatus(str, Enum):
    """Status of a CoVe verification check."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    NOT_APPLICABLE = "not_applicable"


class FindingSeverity(str, Enum):
    """Severity level for verification findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class PromptSpec:
    """
    Specification for a reshaped prompt.

    Contains the original user input and the optimized version,
    along with metadata about the transformation.

    Attributes:
        original_prompt: The raw user input.
        reshaped_prompt: The optimized prompt for the LLM.
        category: Detected intent category.
        transformations_applied: List of transformations applied.
        constraints: Extracted/inferred constraints for the request.
        required_outputs: Expected outputs from the request.
        non_goals: What the request explicitly should NOT do.
        confidence: Confidence score (0.0-1.0) in the reshaping.
        used_llm: Whether LLM was used for reshaping.
        timestamp: When the reshaping occurred.
        request_id: Unique identifier for this request.
    """

    original_prompt: str
    reshaped_prompt: str
    category: str = "general"
    transformations_applied: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    confidence: float = 0.5
    used_llm: bool = False
    timestamp: datetime = field(default_factory=_now_utc)
    request_id: str = field(default_factory=_generate_id)

    def was_modified(self) -> bool:
        """Check if the prompt was actually modified."""
        return self.original_prompt.strip() != self.reshaped_prompt.strip()


@dataclass
class CoveQuestion:
    """
    A verification question in the Chain-of-Verification pipeline.

    Each question is designed to verify a specific claim or fact
    in the draft response.

    Attributes:
        question_id: Unique identifier for this question.
        question_text: The verification question.
        target_claim: The claim being verified.
        source_context: Context from the draft that prompted this question.
        answer: The answer obtained (populated after verification).
        verified: Whether verification was successful.
        confidence: Confidence score (0.0-1.0) in the verification.
    """

    question_text: str
    target_claim: str
    source_context: str = ""
    question_id: str = field(default_factory=_generate_id)
    answer: Optional[str] = None
    verified: Optional[bool] = None
    confidence: float = 0.0

    def is_answered(self) -> bool:
        """Check if this question has been answered."""
        return self.answer is not None


@dataclass
class CoveFinding:
    """
    A finding from the verification process.

    Represents a specific issue or confirmation discovered
    during Chain-of-Verification.

    Attributes:
        finding_id: Unique identifier for this finding.
        question_id: ID of the question that led to this finding.
        description: Human-readable description of the finding.
        severity: Severity level of the finding.
        status: Verification status.
        original_text: The original text being verified.
        suggested_correction: Suggested fix if applicable.
        evidence: Supporting evidence for the finding.
    """

    description: str
    severity: FindingSeverity = FindingSeverity.INFO
    status: VerificationStatus = VerificationStatus.NOT_APPLICABLE
    finding_id: str = field(default_factory=_generate_id)
    question_id: Optional[str] = None
    original_text: str = ""
    suggested_correction: Optional[str] = None
    evidence: list[str] = field(default_factory=list)

    def is_critical(self) -> bool:
        """Check if this finding requires attention."""
        return self.severity == FindingSeverity.ERROR or self.status == VerificationStatus.CONTRADICTED


@dataclass
class PipelineArtifacts:
    """
    Debug artifacts from the prompting pipeline.

    Contains all intermediate results from reshaping and verification
    for debugging, tuning, and auditing purposes.

    Attributes:
        request_id: Unique identifier for this pipeline run.
        timestamp: When the pipeline was executed.
        prompt_spec: The prompt specification (if reshaping was applied).
        draft_response: The initial LLM response before verification.
        cove_questions: Verification questions generated.
        cove_findings: Findings from verification.
        final_response: The final response after any corrections.
        metadata: Additional metadata about the pipeline run.
    """

    request_id: str = field(default_factory=_generate_id)
    timestamp: datetime = field(default_factory=_now_utc)
    prompt_spec: Optional[PromptSpec] = None
    draft_response: Optional[str] = None
    cove_questions: list[CoveQuestion] = field(default_factory=list)
    cove_findings: list[CoveFinding] = field(default_factory=list)
    final_response: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_reshaping(self) -> bool:
        """Check if prompt reshaping was applied."""
        return self.prompt_spec is not None and self.prompt_spec.was_modified()

    def has_verification(self) -> bool:
        """Check if CoVe was applied."""
        return len(self.cove_questions) > 0

    def verification_passed(self) -> bool:
        """Check if verification passed without critical findings."""
        return not any(f.is_critical() for f in self.cove_findings)

    def to_dict(self) -> dict[str, Any]:
        """Convert artifacts to a dictionary for storage."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "prompt_spec": {
                "original_prompt": self.prompt_spec.original_prompt,
                "reshaped_prompt": self.prompt_spec.reshaped_prompt,
                "category": self.prompt_spec.category,
                "transformations_applied": self.prompt_spec.transformations_applied,
                "constraints": self.prompt_spec.constraints,
                "required_outputs": self.prompt_spec.required_outputs,
                "non_goals": self.prompt_spec.non_goals,
                "confidence": self.prompt_spec.confidence,
                "used_llm": self.prompt_spec.used_llm,
                "was_modified": self.prompt_spec.was_modified(),
            }
            if self.prompt_spec
            else None,
            "draft_response": self.draft_response,
            "cove_questions": [
                {
                    "question_id": q.question_id,
                    "question_text": q.question_text,
                    "target_claim": q.target_claim,
                    "answer": q.answer,
                    "verified": q.verified,
                    "confidence": q.confidence,
                }
                for q in self.cove_questions
            ],
            "cove_findings": [
                {
                    "finding_id": f.finding_id,
                    "description": f.description,
                    "severity": f.severity.value,
                    "status": f.status.value,
                    "original_text": f.original_text,
                    "suggested_correction": f.suggested_correction,
                }
                for f in self.cove_findings
            ],
            "final_response": self.final_response,
            "metadata": self.metadata,
        }


@dataclass
class PipelineResult:
    """
    Final result from the prompting pipeline.

    Contains the output to return to the user, along with optional
    metadata for transparency and debugging.

    Attributes:
        response: The final response text.
        verified: Whether the response passed verification.
        verified_badge: Optional badge/summary for verified responses.
        reshaped_prompt: The reshaped prompt (only if inspection allowed).
        artifacts: Full pipeline artifacts (only if debug storage enabled).
        request_id: Unique identifier for this request.
    """

    response: str
    verified: bool = False
    verified_badge: Optional[str] = None
    reshaped_prompt: Optional[str] = None
    artifacts: Optional[PipelineArtifacts] = None
    request_id: str = field(default_factory=_generate_id)

    @classmethod
    def passthrough(cls, original_input: str, request_id: Optional[str] = None) -> "PipelineResult":
        """
        Create a passthrough result (no pipeline processing).

        Used when the pipeline is disabled or not applicable.

        Args:
            original_input: The original user input to pass through.
            request_id: Optional request ID to use.

        Returns:
            PipelineResult with the original input unchanged.
        """
        return cls(
            response=original_input,
            verified=False,
            verified_badge=None,
            reshaped_prompt=None,
            artifacts=PipelineArtifacts(
                request_id=request_id or _generate_id(),
                prompt_spec=PromptSpec(
                    original_prompt=original_input,
                    reshaped_prompt=original_input,
                    category="passthrough",
                    transformations_applied=[],
                    request_id=request_id or _generate_id(),
                ),
            ),
            request_id=request_id or _generate_id(),
        )


@dataclass
class InspectOutput:
    """
    Concise inspect output for user viewing.

    Shows prompt transformation and verification results without
    chain-of-thought or internal reasoning.

    Attributes:
        original_prompt: The raw user input.
        reshaped_prompt: The transformed prompt.
        verification_questions: List of verification question texts.
        findings_summary: One-line summaries of findings.
        badge: Verification status badge.
    """

    original_prompt: str
    reshaped_prompt: str
    verification_questions: list[str] = field(default_factory=list)
    findings_summary: list[str] = field(default_factory=list)
    badge: Optional[str] = None

    def format(self) -> str:
        """
        Format for display - never shows chain-of-thought.

        Returns:
            Concise, human-readable inspection output.
        """
        lines = [
            "=== Prompt Inspection ===",
            "",
            "ORIGINAL:",
            self.original_prompt,
            "",
            "RESHAPED:",
            self.reshaped_prompt,
        ]

        if self.verification_questions:
            lines.extend(["", "VERIFICATION QUESTIONS:"])
            for i, q in enumerate(self.verification_questions, 1):
                lines.append(f"  {i}. {q}")

        if self.findings_summary:
            lines.extend(["", "FINDINGS:"])
            for finding in self.findings_summary:
                lines.append(f"  - {finding}")

        if self.badge:
            lines.extend(["", f"STATUS: {self.badge}"])

        return "\n".join(lines)
