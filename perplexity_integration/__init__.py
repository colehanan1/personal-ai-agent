"""
Perplexity Integration Module

Provides structured prompting system for Perplexity API calls with:
- Token-optimized system messages
- Repository context awareness
- Search parameter optimization
- Citation verification
"""

from .prompting_system import (
    PerplexityPromptBuilder,
    StructuredPrompt,
    SearchMode,
    RecencyFilter,
    ContextSize,
    validate_prompt_structure,
)
from .api_client import (
    PerplexityAPIClient,
    PerplexityResponse,
)
from .context_manager import (
    RepositoryContextLoader,
    RepositoryContext,
)

__all__ = [
    "PerplexityPromptBuilder",
    "StructuredPrompt",
    "SearchMode",
    "RecencyFilter",
    "ContextSize",
    "validate_prompt_structure",
    "PerplexityAPIClient",
    "PerplexityResponse",
    "RepositoryContextLoader",
    "RepositoryContext",
]
