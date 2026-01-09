"""
Prompt reshaping module for the prompting middleware.

Transforms user input into an optimized "ideal prompt" for Milton:
- Concise and explicit constraints
- Structured format
- Intent-aware transformations

Supports LLM-based reshaping with fallback to deterministic heuristics.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from .classifier import ClassificationResult

logger = logging.getLogger(__name__)


# Token-efficient system prompt for reshaping
RESHAPE_SYSTEM_PROMPT = """You are a prompt optimizer. Rewrite user input into a structured, high-quality prompt.

Rules:
- Be concise and explicit
- Extract and structure constraints
- Identify required outputs and non-goals
- For prompt-writing requests: preserve the user's intent, do not add your own constraints
- Output ONLY valid JSON, no explanation

Output format:
{
  "reshaped_prompt": "The optimized prompt text",
  "constraints": ["constraint 1", "constraint 2"],
  "required_outputs": ["output 1"],
  "non_goals": ["what to avoid"],
  "confidence": 0.9
}"""


@dataclass
class ReshapeResult:
    """
    Result of prompt reshaping.

    Attributes:
        original_text: The original user input.
        reshaped_prompt: The optimized prompt for downstream use.
        intent_category: Detected intent category.
        constraints: List of extracted/inferred constraints.
        required_outputs: Expected outputs from the request.
        non_goals: What the request explicitly should NOT do.
        confidence: Confidence score (0.0-1.0) in the reshaping.
        used_llm: Whether LLM was used for reshaping.
        transformations: List of transformations applied.
    """

    original_text: str
    reshaped_prompt: str
    intent_category: str = "general"
    constraints: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    confidence: float = 0.5
    used_llm: bool = False
    transformations: list[str] = field(default_factory=list)

    def was_modified(self) -> bool:
        """Check if the prompt was actually modified."""
        return self.original_text.strip() != self.reshaped_prompt.strip()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_text": self.original_text,
            "reshaped_prompt": self.reshaped_prompt,
            "intent_category": self.intent_category,
            "constraints": self.constraints,
            "required_outputs": self.required_outputs,
            "non_goals": self.non_goals,
            "confidence": self.confidence,
            "used_llm": self.used_llm,
            "transformations": self.transformations,
            "was_modified": self.was_modified(),
        }


class PromptReshaper:
    """
    Reshapes user input into optimized prompts.

    Uses LLM when available, falls back to deterministic heuristics.
    """

    def __init__(
        self,
        llm_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_timeout: int = 30,
    ):
        """
        Initialize the reshaper.

        Args:
            llm_url: LLM API URL (defaults to env var).
            llm_model: Model name (defaults to env var).
            llm_timeout: Timeout for LLM calls in seconds.
        """
        self.llm_url = (
            llm_url
            or os.getenv("LLM_API_URL")
            or os.getenv("OLLAMA_API_URL")
        )
        self.llm_model = (
            llm_model
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL")
        )
        self.llm_timeout = llm_timeout
        self._llm_available: Optional[bool] = None

    def is_llm_available(self) -> bool:
        """Check if LLM backend is reachable."""
        if self._llm_available is not None:
            return self._llm_available

        if not self.llm_url or not self.llm_model:
            self._llm_available = False
            return False

        try:
            url = f"{self.llm_url.rstrip('/')}/v1/models"
            response = requests.get(url, timeout=5)
            self._llm_available = response.status_code == 200
        except Exception:
            self._llm_available = False

        return self._llm_available

    def reshape(
        self,
        user_text: str,
        classification: Optional[ClassificationResult] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ReshapeResult:
        """
        Reshape user input into an optimized prompt.

        Args:
            user_text: The raw user input.
            classification: Classification result (if available).
            context: Additional context for reshaping.

        Returns:
            ReshapeResult with original and reshaped prompt.
        """
        if not user_text or not user_text.strip():
            return ReshapeResult(
                original_text=user_text,
                reshaped_prompt=user_text,
                confidence=1.0,
            )

        category = classification.category if classification else "general"

        # Try LLM-based reshaping first
        if self.is_llm_available():
            try:
                return self._reshape_with_llm(user_text, category, context)
            except Exception as e:
                logger.warning(f"LLM reshaping failed, falling back to heuristic: {e}")

        # Fall back to deterministic heuristic
        return self._reshape_heuristic(user_text, category, context)

    def _reshape_with_llm(
        self,
        user_text: str,
        category: str,
        context: Optional[dict[str, Any]],
    ) -> ReshapeResult:
        """Reshape using LLM backend."""
        # Build the prompt for the reshaper
        user_prompt = f"Category: {category}\nUser input: {user_text}"
        if context:
            user_prompt += f"\nContext: {json.dumps(context)}"

        url = f"{self.llm_url.rstrip('/')}/v1/chat/completions"
        api_key = os.getenv("LLM_API_KEY") or os.getenv("VLLM_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": RESHAPE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 500,
            "temperature": 0.3,  # Lower temp for more consistent output
        }

        response = requests.post(
            url, json=payload, timeout=self.llm_timeout, headers=headers
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]

        # Parse JSON response
        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            # Fall back to using content as reshaped prompt
            return ReshapeResult(
                original_text=user_text,
                reshaped_prompt=content.strip(),
                intent_category=category,
                confidence=0.5,
                used_llm=True,
                transformations=["llm_reshape_fallback"],
            )

        return ReshapeResult(
            original_text=user_text,
            reshaped_prompt=data.get("reshaped_prompt", user_text),
            intent_category=category,
            constraints=data.get("constraints", []),
            required_outputs=data.get("required_outputs", []),
            non_goals=data.get("non_goals", []),
            confidence=data.get("confidence", 0.8),
            used_llm=True,
            transformations=["llm_reshape"],
        )

    def _reshape_heuristic(
        self,
        user_text: str,
        category: str,
        context: Optional[dict[str, Any]],
    ) -> ReshapeResult:
        """
        Deterministic heuristic-based reshaping.

        Applies category-specific templates and structure.
        """
        transformations: list[str] = []
        constraints: list[str] = []
        required_outputs: list[str] = []
        non_goals: list[str] = []
        confidence = 0.6

        text = user_text.strip()
        reshaped = text

        # Category-specific reshaping
        if category == "research":
            reshaped, trans = self._reshape_research(text)
            transformations.extend(trans)
            required_outputs.extend(["key findings", "sources"])
            constraints.append("use authoritative sources")

        elif category == "analysis":
            reshaped, trans = self._reshape_analysis(text)
            transformations.extend(trans)
            required_outputs.extend(["analysis", "conclusions"])
            constraints.append("be objective and evidence-based")

        elif category == "coding":
            reshaped, trans = self._reshape_coding(text)
            transformations.extend(trans)
            required_outputs.append("working code")
            constraints.extend(["follow best practices", "include error handling"])
            non_goals.append("over-engineering")

        elif category == "planning":
            reshaped, trans = self._reshape_planning(text)
            transformations.extend(trans)
            required_outputs.extend(["action steps", "priorities"])
            constraints.append("be actionable and specific")

        elif category == "creative":
            reshaped, trans = self._reshape_creative(text)
            transformations.extend(trans)
            constraints.append("maintain creative freedom")

        elif category == "explanation":
            reshaped, trans = self._reshape_explanation(text)
            transformations.extend(trans)
            required_outputs.append("clear explanation")
            constraints.append("be concise and accessible")

        elif category == "problem_solving":
            reshaped, trans = self._reshape_problem_solving(text)
            transformations.extend(trans)
            required_outputs.extend(["solution", "reasoning"])

        elif category == "summarization":
            reshaped, trans = self._reshape_summarization(text)
            transformations.extend(trans)
            required_outputs.append("concise summary")
            constraints.append("preserve key information")

        else:
            # General cleanup for other categories
            reshaped, trans = self._general_cleanup(text)
            transformations.extend(trans)

        # Check if this is a prompt-writing request (meta-prompt)
        if self._is_prompt_writing_request(text):
            # For prompt-writing, preserve user intent more carefully
            reshaped = self._reshape_prompt_writing_request(text)
            transformations = ["meta_prompt_handling"]
            constraints = ["preserve user's original requirements"]
            non_goals.append("adding unsolicited constraints")
            confidence = 0.85

        return ReshapeResult(
            original_text=user_text,
            reshaped_prompt=reshaped,
            intent_category=category,
            constraints=constraints,
            required_outputs=required_outputs,
            non_goals=non_goals,
            confidence=confidence,
            used_llm=False,
            transformations=transformations,
        )

    def _is_prompt_writing_request(self, text: str) -> bool:
        """Detect if the request is for writing prompts for agents."""
        patterns = [
            r"\b(write|create|generate|design|draft)\s+(a\s+)?(prompt|instruction|system\s+prompt)",
            r"\bprompt\s+for\s+(an?\s+)?(agent|ai|assistant|llm|model)",
            r"\b(agent|system)\s+(prompt|instruction)",
            r"\bprompting\s+(guide|template|strategy)",
        ]
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in patterns)

    def _reshape_prompt_writing_request(self, text: str) -> str:
        """Handle prompt-writing requests carefully."""
        # For meta-prompts, structure the request but preserve user requirements
        lines = [
            "Task: Create a prompt/instructions for an AI agent.",
            "",
            "Requirements from user:",
            text,
            "",
            "Guidelines:",
            "- Follow the user's specifications exactly",
            "- Include clear role definition",
            "- Define expected outputs",
            "- Add appropriate constraints if not specified",
        ]
        return "\n".join(lines)

    def _reshape_research(self, text: str) -> tuple[str, list[str]]:
        """Reshape research requests."""
        transformations = []

        # Add structure for research requests
        if not re.search(r"\b(recent|latest|current|up-to-date)\b", text, re.I):
            text = f"Provide up-to-date research on: {text}"
            transformations.append("added_recency")

        if not re.search(r"\b(source|cite|reference)\b", text, re.I):
            text += " Include key sources."
            transformations.append("added_source_request")

        return text, transformations

    def _reshape_analysis(self, text: str) -> tuple[str, list[str]]:
        """Reshape analysis requests."""
        transformations = []

        # Structure analysis requests
        if not re.search(r"\b(pros?\s*(and|&)?\s*cons?|trade-?off|compare)\b", text, re.I):
            # Check if it's a comparison-style analysis
            pass

        if "analyze" not in text.lower():
            text = f"Analyze: {text}"
            transformations.append("explicit_analyze")

        return text, transformations

    def _reshape_coding(self, text: str) -> tuple[str, list[str]]:
        """Reshape coding requests."""
        transformations = []

        # Add code quality expectations
        if not re.search(r"\b(test|testing)\b", text, re.I):
            text += " Consider edge cases."
            transformations.append("added_edge_cases")

        return text, transformations

    def _reshape_planning(self, text: str) -> tuple[str, list[str]]:
        """Reshape planning requests."""
        transformations = []

        if not re.search(r"\b(step|phase|action|task)\b", text, re.I):
            text = f"Create an actionable plan for: {text}"
            transformations.append("explicit_planning")

        return text, transformations

    def _reshape_creative(self, text: str) -> tuple[str, list[str]]:
        """Reshape creative requests."""
        transformations = []

        # Preserve creative freedom, minimal transformation
        if len(text) < 20:
            text = f"Create: {text}"
            transformations.append("added_context")

        return text, transformations

    def _reshape_explanation(self, text: str) -> tuple[str, list[str]]:
        """Reshape explanation requests."""
        transformations = []

        # Add clarity request
        if not re.search(r"\b(simple|clear|basic|eli5)\b", text, re.I):
            text += " Explain clearly."
            transformations.append("added_clarity")

        return text, transformations

    def _reshape_problem_solving(self, text: str) -> tuple[str, list[str]]:
        """Reshape problem-solving requests."""
        transformations = []

        if not re.search(r"\b(solution|solve|fix|resolve)\b", text, re.I):
            text = f"Help solve: {text}"
            transformations.append("explicit_problem_solving")

        return text, transformations

    def _reshape_summarization(self, text: str) -> tuple[str, list[str]]:
        """Reshape summarization requests."""
        transformations = []

        if not re.search(r"\b(brief|concise|short|key\s+points)\b", text, re.I):
            text = f"Provide a concise summary of: {text}"
            transformations.append("explicit_summarize")

        return text, transformations

    def _general_cleanup(self, text: str) -> tuple[str, list[str]]:
        """General text cleanup and structuring."""
        transformations = []

        # Remove excessive whitespace
        original_len = len(text)
        text = " ".join(text.split())
        if len(text) < original_len:
            transformations.append("whitespace_cleanup")

        # Ensure text ends with proper punctuation
        if text and text[-1] not in ".!?":
            text += "."
            transformations.append("added_punctuation")

        return text, transformations


# Singleton reshaper instance
_reshaper: Optional[PromptReshaper] = None


def get_reshaper() -> PromptReshaper:
    """Get the global reshaper instance."""
    global _reshaper
    if _reshaper is None:
        _reshaper = PromptReshaper()
    return _reshaper


def reset_reshaper() -> None:
    """Reset the global reshaper (for testing)."""
    global _reshaper
    _reshaper = None


def reshape_user_input(
    user_text: str,
    context: Optional[dict[str, Any]] = None,
    classification: Optional[ClassificationResult] = None,
) -> ReshapeResult:
    """
    Convenience function to reshape user input.

    Args:
        user_text: The raw user input.
        context: Optional context for reshaping.
        classification: Optional classification result.

    Returns:
        ReshapeResult with reshaped prompt and metadata.
    """
    reshaper = get_reshaper()
    return reshaper.reshape(user_text, classification=classification, context=context)
