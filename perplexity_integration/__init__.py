"""
Perplexity Integration Module (2025 Enhanced)

Provides structured prompting system for Perplexity API calls with:
- Token-optimized system messages with chain-of-thought
- JSON schema structured outputs (2025 feature)
- Repository context awareness (included in EVERY call)
- Search parameter optimization
- Citation verification (citations FREE in 2025)
- Pydantic model validation

References:
- https://docs.perplexity.ai/guides/structured-outputs
- https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought
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
from .response_schemas import (
    ResearchResponse,
    SpecificationResponse,
    DocumentationSearchResponse,
    QuickFactResponse,
    Source,
    get_schema_for_prompt_type,
)

__all__ = [
    # Prompt building
    "PerplexityPromptBuilder",
    "StructuredPrompt",
    "SearchMode",
    "RecencyFilter",
    "ContextSize",
    "validate_prompt_structure",
    # API client
    "PerplexityAPIClient",
    "PerplexityResponse",
    # Context management
    "RepositoryContextLoader",
    "RepositoryContext",
    # Response schemas (2025 JSON schema feature)
    "ResearchResponse",
    "SpecificationResponse",
    "DocumentationSearchResponse",
    "QuickFactResponse",
    "Source",
    "get_schema_for_prompt_type",
]
