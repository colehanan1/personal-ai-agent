"""
Configuration for the prompting middleware.

Provides PromptingConfig dataclass with flags to control:
- Prompt reshaping (rewrite user input into an "ideal prompt")
- CoVe (Chain-of-Verification) pipeline
- Inspectability and debug artifact storage
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean from environment variable string."""
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _parse_int(value: Optional[str], default: int) -> int:
    """Parse integer from environment variable string."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_list(value: Optional[str], default: list[str]) -> list[str]:
    """Parse comma-separated list from environment variable string."""
    if value is None:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items if items else default


# Default categories that trigger prompt reshaping (most categories except trivial)
DEFAULT_RESHAPE_CATEGORIES: list[str] = [
    "research",
    "analysis",
    "coding",
    "planning",
    "creative",
    "explanation",
    "comparison",
    "recommendation",
    "problem_solving",
    "summarization",
]

# Default categories that trigger CoVe (non-trivial, fact-heavy categories)
DEFAULT_COVE_CATEGORIES: list[str] = [
    "research",
    "analysis",
    "explanation",
    "comparison",
    "recommendation",
    "problem_solving",
]

# Categories excluded from reshaping (trivial/simple)
EXCLUDED_RESHAPE_CATEGORIES: list[str] = [
    "reminder",
    "timer",
    "greeting",
    "acknowledgment",
    "simple_query",
]


@dataclass
class PromptingConfig:
    """
    Configuration for the prompting middleware pipeline.

    Controls prompt reshaping, Chain-of-Verification (CoVe), and debug storage.
    All settings have sensible defaults that preserve existing behavior when
    the pipeline is disabled.

    Attributes:
        enable_prompt_reshape: If True, rewrite user input into an optimized prompt
            before sending to the LLM. Default: False (preserves current behavior).
        enable_cove: If True, run Chain-of-Verification pipeline on responses
            to improve factual accuracy. Default: False.
        enable_cove_for_responses: If True, run CoVe on non-trivial user responses
            before returning them. This is config-gated separately from enable_cove.
            Default: False.
        cove_min_questions: Minimum number of verification questions to generate.
        cove_max_questions: Maximum number of verification questions to generate.
        allow_user_inspect_reshaped_prompt: If True, include the reshaped prompt
            in the response when explicitly requested. Default: False.
        return_verified_badge: If True, include a "Verified" badge/summary with
            responses that passed CoVe. Default: True.
        store_debug_artifacts: If True, store pipeline artifacts (draft, questions,
            findings) for debugging and tuning. Default: True.
        categories_triggering_reshape: List of intent categories that trigger
            prompt reshaping. Default includes most non-trivial categories.
        categories_triggering_cove: List of intent categories that trigger
            the CoVe pipeline. Default includes fact-heavy categories.
    """

    enable_prompt_reshape: bool = False
    enable_cove: bool = False
    enable_cove_for_responses: bool = False
    cove_min_questions: int = 2
    cove_max_questions: int = 5
    allow_user_inspect_reshaped_prompt: bool = False
    return_verified_badge: bool = True
    store_debug_artifacts: bool = True
    categories_triggering_reshape: list[str] = field(
        default_factory=lambda: DEFAULT_RESHAPE_CATEGORIES.copy()
    )
    categories_triggering_cove: list[str] = field(
        default_factory=lambda: DEFAULT_COVE_CATEGORIES.copy()
    )

    @classmethod
    def from_env(cls) -> "PromptingConfig":
        """
        Load configuration from environment variables.

        Environment variables (all prefixed with PROMPTING_):
            PROMPTING_ENABLE_RESHAPE: Enable prompt reshaping (default: false)
            PROMPTING_ENABLE_COVE: Enable Chain-of-Verification (default: false)
            PROMPTING_ENABLE_COVE_FOR_RESPONSES: Enable CoVe for user responses (default: false)
            PROMPTING_COVE_MIN_QUESTIONS: Min verification questions (default: 2)
            PROMPTING_COVE_MAX_QUESTIONS: Max verification questions (default: 5)
            PROMPTING_ALLOW_INSPECT_RESHAPED: Allow users to see reshaped prompt (default: false)
            PROMPTING_RETURN_VERIFIED_BADGE: Include verified badge (default: true)
            PROMPTING_STORE_DEBUG_ARTIFACTS: Store debug artifacts (default: true)
            PROMPTING_RESHAPE_CATEGORIES: Comma-separated categories for reshape
            PROMPTING_COVE_CATEGORIES: Comma-separated categories for CoVe

        Returns:
            PromptingConfig instance with values from environment.
        """
        return cls(
            enable_prompt_reshape=_parse_bool(
                os.getenv("PROMPTING_ENABLE_RESHAPE"), default=False
            ),
            enable_cove=_parse_bool(
                os.getenv("PROMPTING_ENABLE_COVE"), default=False
            ),
            enable_cove_for_responses=_parse_bool(
                os.getenv("PROMPTING_ENABLE_COVE_FOR_RESPONSES"), default=False
            ),
            cove_min_questions=_parse_int(
                os.getenv("PROMPTING_COVE_MIN_QUESTIONS"), default=2
            ),
            cove_max_questions=_parse_int(
                os.getenv("PROMPTING_COVE_MAX_QUESTIONS"), default=5
            ),
            allow_user_inspect_reshaped_prompt=_parse_bool(
                os.getenv("PROMPTING_ALLOW_INSPECT_RESHAPED"), default=False
            ),
            return_verified_badge=_parse_bool(
                os.getenv("PROMPTING_RETURN_VERIFIED_BADGE"), default=True
            ),
            store_debug_artifacts=_parse_bool(
                os.getenv("PROMPTING_STORE_DEBUG_ARTIFACTS"), default=True
            ),
            categories_triggering_reshape=_parse_list(
                os.getenv("PROMPTING_RESHAPE_CATEGORIES"),
                default=DEFAULT_RESHAPE_CATEGORIES.copy(),
            ),
            categories_triggering_cove=_parse_list(
                os.getenv("PROMPTING_COVE_CATEGORIES"),
                default=DEFAULT_COVE_CATEGORIES.copy(),
            ),
        )

    def validate(self) -> list[str]:
        """
        Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        if self.cove_min_questions < 1:
            errors.append("cove_min_questions must be at least 1")
        if self.cove_max_questions < self.cove_min_questions:
            errors.append(
                "cove_max_questions must be >= cove_min_questions"
            )
        if self.cove_max_questions > 10:
            errors.append("cove_max_questions should not exceed 10")

        return errors

    def should_reshape(self, category: str) -> bool:
        """Check if a category should trigger prompt reshaping."""
        if not self.enable_prompt_reshape:
            return False
        return category.lower() in [c.lower() for c in self.categories_triggering_reshape]

    def should_run_cove(self, category: str) -> bool:
        """Check if a category should trigger Chain-of-Verification."""
        if not self.enable_cove:
            return False
        return category.lower() in [c.lower() for c in self.categories_triggering_cove]
