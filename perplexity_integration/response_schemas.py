"""
Pydantic models for Perplexity API structured JSON responses

Based on Perplexity 2025 best practices:
- JSON Schema structured outputs for consistent, machine-readable data
- Token-efficient response formats
- Citation tracking and verification
- Chain-of-thought reasoning capture

References:
- https://docs.perplexity.ai/guides/structured-outputs
- https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Source(BaseModel):
    """Citation source metadata"""
    id: int = Field(..., description="Citation ID number (e.g., 1, 2, 3)")
    title: str = Field(..., description="Source title or page name")
    url: str = Field(..., description="Full URL to source")
    relevance: Optional[str] = Field(
        None,
        description="Why this source is relevant (optional)"
    )


class ResearchResponse(BaseModel):
    """
    Structured response format for research queries.

    Optimized for:
    - Token efficiency (concise fields)
    - Citation tracking (inline + list)
    - Quality verification (confidence levels)
    - Clarification handling (needs_clarification)

    Example:
        {
          "reasoning": "Searched Anthropic docs for Claude best practices...",
          "sources": [{"id": 1, "title": "Claude Docs", "url": "..."}],
          "answer": "Best practices: 1) Use chain-of-thought[1]...",
          "confidence": "high",
          "needs_clarification": null
        }
    """
    reasoning: str = Field(
        ...,
        max_length=800,
        description="Chain-of-thought reasoning process (bullet points, concise)"
    )
    sources: List[Source] = Field(
        ...,
        min_length=1,
        description="List of sources cited in answer (minimum 1 required)"
    )
    answer: str = Field(
        ...,
        max_length=1500,
        description="Final answer with inline citations [N]"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level based on source quality and consensus"
    )
    needs_clarification: Optional[str] = Field(
        None,
        description="If info incomplete, list 2-3 specific questions needed"
    )
    related_topics: Optional[List[str]] = Field(
        None,
        max_length=3,
        description="Related topics for follow-up (max 3)"
    )


class SpecificationResponse(BaseModel):
    """
    Structured response format for code specification generation.

    Optimized for Claude Code agent consumption with:
    - Clear objectives and context
    - Actionable technical constraints
    - Specific file/directory boundaries
    - Testable deliverables

    Example:
        {
          "objective": "Add user authentication to Flask app",
          "context": "Python Flask app with SQLite, no existing auth",
          "reasoning": "Analyzed Flask-Login docs[1], security best practices[2]...",
          "sources": [...],
          "technical_constraints": {
            "language": "Python 3.11+",
            "frameworks": ["Flask 3.0", "Flask-Login"],
            ...
          },
          ...
        }
    """
    objective: str = Field(
        ...,
        max_length=300,
        description="Clear, concise objective statement"
    )
    context: str = Field(
        ...,
        max_length=500,
        description="Repository context, tech stack, existing patterns"
    )
    reasoning: str = Field(
        ...,
        max_length=1000,
        description="Research process and architectural decision-making (chain-of-thought)"
    )
    sources: List[Source] = Field(
        ...,
        min_length=1,
        description="Official documentation and authoritative sources cited"
    )
    technical_constraints: dict = Field(
        ...,
        description="Language, frameworks, dependencies with versions"
    )
    file_boundaries: List[str] = Field(
        ...,
        description="Specific file paths to create/modify (e.g., 'src/auth.py')"
    )
    testing_requirements: dict = Field(
        ...,
        description="Test commands, coverage expectations, test files"
    )
    implementation_plan: List[str] = Field(
        ...,
        max_length=10,
        description="Step-by-step actionable tasks (max 10 steps)"
    )
    deliverables: List[str] = Field(
        ...,
        description="Concrete deliverables checklist"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence in specification based on source quality"
    )
    needs_clarification: Optional[str] = Field(
        None,
        description="If requirements unclear, specific questions to ask"
    )


class DocumentationSearchResponse(BaseModel):
    """
    Structured response for documentation-specific queries.

    Optimized for:
    - Official documentation sources only
    - Working code examples
    - Version-specific information

    Example:
        {
          "summary": "search_domain_filter restricts search to specified domains",
          "sources": [{"id": 1, "title": "Perplexity API Docs", ...}],
          "code_examples": ["params = {'search_domain_filter': [...]}"],
          "version_info": "Available in Perplexity API v1.0+",
          ...
        }
    """
    summary: str = Field(
        ...,
        max_length=500,
        description="Concise explanation from official docs"
    )
    sources: List[Source] = Field(
        ...,
        min_length=1,
        description="Official documentation sources only"
    )
    code_examples: Optional[List[str]] = Field(
        None,
        max_length=3,
        description="Working code examples from docs (max 3)"
    )
    version_info: Optional[str] = Field(
        None,
        description="Version information if applicable"
    )
    best_practices: Optional[List[str]] = Field(
        None,
        max_length=5,
        description="Key best practices from official docs (max 5)"
    )
    confidence: Literal["high", "medium", "low"] = Field(..., description="Source authority level")
    related_topics: Optional[List[str]] = Field(
        None,
        max_length=3,
        description="Related documentation topics"
    )


class QuickFactResponse(BaseModel):
    """
    Minimal structured response for simple factual queries.

    Token-optimized for quick lookups that don't need full research depth.

    Example:
        {
          "fact": "Perplexity sonar-pro uses search mode 'high' by default",
          "sources": [{"id": 1, ...}],
          "confidence": "high"
        }
    """
    fact: str = Field(
        ...,
        max_length=300,
        description="Concise factual answer with citation [N]"
    )
    sources: List[Source] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1-3 authoritative sources"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence based on source consensus"
    )


def get_schema_for_prompt_type(prompt_type: str) -> type[BaseModel]:
    """
    Get the appropriate Pydantic schema for a given prompt type.

    Args:
        prompt_type: One of 'research', 'specification', 'documentation', 'fact'

    Returns:
        Pydantic model class for JSON schema generation

    Example:
        schema_cls = get_schema_for_prompt_type('research')
        schema_dict = schema_cls.model_json_schema()
    """
    schemas = {
        "research": ResearchResponse,
        "specification": SpecificationResponse,
        "documentation": DocumentationSearchResponse,
        "fact": QuickFactResponse,
    }

    if prompt_type not in schemas:
        raise ValueError(
            f"Unknown prompt type: {prompt_type}. "
            f"Valid types: {list(schemas.keys())}"
        )

    return schemas[prompt_type]
