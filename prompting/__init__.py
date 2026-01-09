"""
Prompting middleware for Milton.

Provides prompt reshaping and Chain-of-Verification (CoVe) capabilities
to improve prompt quality and response accuracy.

Main components:
- PromptingPipeline: Main pipeline class for processing prompts
- PromptingConfig: Configuration for pipeline behavior
- IntentClassifier: Interface for prompt classification

Usage:
    from prompting import PromptingPipeline, PromptingConfig

    # Use default config (from environment)
    pipeline = PromptingPipeline()
    result = pipeline.run("What is quantum computing?")

    # Or with custom config
    config = PromptingConfig(
        enable_prompt_reshape=True,
        enable_cove=True,
    )
    pipeline = PromptingPipeline(config=config)
    result = pipeline.run("Explain the theory of relativity")

    # Access result
    print(result.response)
    print(result.verified)  # True if CoVe passed
"""
from .classifier import (
    ClassificationResult,
    HeuristicClassifier,
    IntentClassifier,
    classify_prompt,
    get_classifier,
    set_classifier,
)
from .config import (
    DEFAULT_COVE_CATEGORIES,
    DEFAULT_RESHAPE_CATEGORIES,
    EXCLUDED_RESHAPE_CATEGORIES,
    PromptingConfig,
)
from .cove import (
    ChainOfVerification,
    CoveError,
    CoveResult,
    run_cove,
    verify_prompt,
)
from .memory_hook import (
    MemoryHook,
    MemoryHookError,
    get_memory_hook,
    reset_memory_hook,
)
from .pipeline import (
    PromptingPipeline,
    run_pipeline,
)
from .quality_checks import (
    QualityCheckResult,
    check_prompt_quality,
    revise_prompt_for_quality,
)
from .reshape import (
    PromptReshaper,
    ReshapeResult,
    get_reshaper,
    reset_reshaper,
    reshape_user_input,
)
from .types import (
    CoveFinding,
    CoveQuestion,
    FindingSeverity,
    InspectOutput,
    PipelineArtifacts,
    PipelineResult,
    PromptSpec,
    VerificationStatus,
)

__all__ = [
    # Pipeline
    "PromptingPipeline",
    "run_pipeline",
    # Config
    "PromptingConfig",
    "DEFAULT_RESHAPE_CATEGORIES",
    "DEFAULT_COVE_CATEGORIES",
    "EXCLUDED_RESHAPE_CATEGORIES",
    # CoVe
    "ChainOfVerification",
    "CoveError",
    "CoveResult",
    "run_cove",
    "verify_prompt",
    # Reshape
    "PromptReshaper",
    "ReshapeResult",
    "reshape_user_input",
    "get_reshaper",
    "reset_reshaper",
    # Types
    "PromptSpec",
    "CoveQuestion",
    "CoveFinding",
    "PipelineArtifacts",
    "PipelineResult",
    "VerificationStatus",
    "FindingSeverity",
    "InspectOutput",
    # Quality Checks
    "QualityCheckResult",
    "check_prompt_quality",
    "revise_prompt_for_quality",
    # Classifier
    "IntentClassifier",
    "HeuristicClassifier",
    "ClassificationResult",
    "classify_prompt",
    "get_classifier",
    "set_classifier",
    # Memory
    "MemoryHook",
    "MemoryHookError",
    "get_memory_hook",
    "reset_memory_hook",
]
