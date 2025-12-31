"""
Token-optimized structured prompting system for Perplexity API

Based on Perplexity API best practices (2025):
- Concise system messages to reduce token usage
- Structured user prompts with clear directives
- Search parameters separated from reasoning
- Citation verification requirements
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search depth modes for Perplexity API"""
    PRO = "sonar-pro"  # Deep research with comprehensive sources
    STANDARD = "sonar"  # Standard search for quick facts
    REASONING = "sonar-reasoning"  # With chain-of-thought reasoning


class RecencyFilter(Enum):
    """Time-based recency filters for search results"""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ContextSize(Enum):
    """Search context size settings"""
    LOW = "low"  # Simple factual queries
    MEDIUM = "medium"  # Default, balanced
    HIGH = "high"  # Comprehensive research


@dataclass
class StructuredPrompt:
    """Container for structured Perplexity prompt components"""
    system_message: str
    user_prompt: str
    api_parameters: Dict[str, Any]


class PerplexityPromptBuilder:
    """
    Builds token-optimized structured prompts for Perplexity API.

    Features:
    - Reusable system message template
    - Structured user prompt with context injection
    - API parameter generation for search optimization
    - Citation verification requirements

    Example:
        builder = PerplexityPromptBuilder()
        prompt = builder.build_research_prompt(
            query="How to optimize Claude prompts?",
            context="Milton voice command system",
            mode=SearchMode.PRO
        )
    """

    # Token-optimized system message (reusable across calls)
    # Based on 2025 best practices:
    # - Perplexity structured outputs (docs.perplexity.ai/guides/structured-outputs)
    # - Claude chain-of-thought prompting (docs.anthropic.com/prompt-engineering/chain-of-thought)
    # - Citation tokens are FREE in 2025 (encourage comprehensive sourcing)
    RESEARCH_SYSTEM_MESSAGE = """You are Perplexity in RESEARCH MODE. Return ONLY valid JSON matching the schema provided.

MANDATORY REQUIREMENTS:
1. SEARCH WEB for latest official documentation (prefer last 30 days)
2. CITE SOURCES: Every factual claim must have inline citation [N]
3. JSON OUTPUT ONLY: No markdown, no prose outside the JSON structure
4. REPOSITORY CONTEXT: Milton voice AI system - use provided repo context to ground answers
5. CHAIN-OF-THOUGHT: Show reasoning field with step-by-step research process
6. ASK IF UNCLEAR: If repo context insufficient or requirements ambiguous, set needs_clarification field

RESEARCH PROCESS (Chain-of-Thought in 'reasoning' field):
• Analyze query + repository context provided
• Search authoritative sources (official docs, GitHub, peer-reviewed)
• Evaluate source recency and authority
• Cross-verify claims (min 2 sources per factual claim)
• Synthesize: Analysis → Evidence → Conclusion

JSON STRUCTURE REQUIREMENTS:
{
  "reasoning": "Concise chain-of-thought (max 800 chars, bullet format)",
  "sources": [{"id": 1, "title": "...", "url": "...", "relevance": "..."}],
  "answer": "Final answer with inline citations[1][2] (max 1500 chars)",
  "confidence": "high|medium|low",
  "needs_clarification": null or "Specific questions needed",
  "related_topics": ["topic1", "topic2"] (optional, max 3)
}

TOKEN OPTIMIZATION (citations are FREE in 2025):
• Concise bullet-point reasoning (not paragraphs)
• Rich citations (cite generously, no cost)
• Structured JSON only (no extra text)
• Max 800 chars reasoning, 1500 chars answer"""

    # Alternative system message for Claude-optimized specifications
    # Optimized for Claude Code agent system prompts (Anthropic 2025 best practices)
    # References:
    # - docs.anthropic.com/prompt-engineering/chain-of-thought
    # - www.anthropic.com/engineering/claude-code-best-practices
    SPECIFICATION_SYSTEM_MESSAGE = """You are Perplexity in SPECIFICATION MODE. Return ONLY valid JSON matching the schema provided.

Your task: Research coding requests and produce detailed, actionable specifications for Claude Code AI agent.

MANDATORY REQUIREMENTS:
1. SEARCH official documentation for latest 2025 best practices
2. CITE SOURCES: Every technical recommendation needs citation [N]
3. JSON OUTPUT ONLY: No markdown, no prose outside JSON
4. REPO CONTEXT: Use provided Milton repository context to ground recommendations
5. CHAIN-OF-THOUGHT: Show reasoning field with architectural decision-making process
6. CLAUDE CODE FOCUS: Consider file editing, testing, git workflow capabilities
7. ASK IF UNCLEAR: Set needs_clarification if requirements ambiguous

RESEARCH PROCESS (Chain-of-Thought in 'reasoning' field):
• Analyze user request + repository context
• Search official docs (Anthropic, framework-specific, language-specific)
• Evaluate architectural patterns and trade-offs
• Cross-reference best practices (security, testing, performance)
• Synthesize: Requirements → Design → Implementation → Testing → Delivery

JSON STRUCTURE REQUIREMENTS:
{
  "objective": "Clear objective statement (max 300 chars)",
  "context": "Repository + tech stack context (max 500 chars)",
  "reasoning": "Architectural decision chain-of-thought (max 1000 chars, bullets)",
  "sources": [{"id": 1, "title": "...", "url": "...", "relevance": "..."}],
  "technical_constraints": {"language": "...", "frameworks": [...], "dependencies": {...}},
  "file_boundaries": ["path/to/file1.py", "path/to/file2.py"],
  "testing_requirements": {"commands": [...], "coverage": "...", "test_files": [...]},
  "implementation_plan": ["Step 1: ...", "Step 2: ...", ...],
  "deliverables": ["Deliverable 1", "Deliverable 2", ...],
  "confidence": "high|medium|low",
  "needs_clarification": null or "Specific questions"
}

TOKEN OPTIMIZATION:
• Bullet-point reasoning (not paragraphs)
• Specific file paths and versions
• Cite generously (citations FREE in 2025)
• Structured JSON only"""

    def __init__(self, default_mode: SearchMode = SearchMode.PRO):
        """
        Initialize the prompt builder.

        Args:
            default_mode: Default search mode to use
        """
        self.default_mode = default_mode
        logger.info(f"PerplexityPromptBuilder initialized with mode: {default_mode.value}")

    def build_system_message(self, prompt_type: str = "research") -> str:
        """
        Build system message based on prompt type.

        Args:
            prompt_type: Type of prompt ('research' or 'specification')

        Returns:
            Token-optimized system message
        """
        if prompt_type == "specification":
            return self.SPECIFICATION_SYSTEM_MESSAGE
        return self.RESEARCH_SYSTEM_MESSAGE

    def build_search_parameters(
        self,
        mode: Optional[SearchMode] = None,
        recency_filter: Optional[RecencyFilter] = None,
        domain_filter: Optional[List[str]] = None,
        context_size: Optional[ContextSize] = None,
        return_citations: bool = True,
        return_related_questions: bool = False,
    ) -> Dict[str, Any]:
        """
        Build API parameters for Perplexity search optimization.

        Args:
            mode: Search mode (pro, standard, reasoning)
            recency_filter: Time-based filter for sources (defaults to MONTH for freshness)
            domain_filter: List of domains to include/exclude (prefix with - to exclude)
            context_size: Search context depth (defaults to HIGH for comprehensive research)
            return_citations: Whether to return citation URLs (default True)
            return_related_questions: Whether to return follow-up questions

        Returns:
            Dictionary of API parameters optimized for research quality
        """
        params: Dict[str, Any] = {
            "model": (mode or self.default_mode).value,
            "temperature": 0.2,  # Low temperature for consistent, factual responses
        }

        # Default to MONTH recency for fresh information (best practice 2025)
        if recency_filter is None:
            recency_filter = RecencyFilter.MONTH

        # Default to HIGH context for comprehensive research
        if context_size is None:
            context_size = ContextSize.HIGH

        if recency_filter:
            params["search_recency_filter"] = recency_filter.value

        if domain_filter:
            params["search_domain_filter"] = domain_filter

        if context_size:
            params["search_context_size"] = context_size.value

        if return_citations:
            params["return_citations"] = True

        if return_related_questions:
            params["return_related_questions"] = True

        logger.debug(f"Built search parameters: {params}")
        return params

    def structure_user_prompt(
        self,
        query: str,
        context: Optional[str] = None,
        output_format: Optional[str] = None,
        additional_constraints: Optional[List[str]] = None,
    ) -> str:
        """
        Structure user prompt with context injection and output formatting.

        Args:
            query: The main user query
            context: Repository or domain context
            output_format: Desired output structure
            additional_constraints: List of additional requirements

        Returns:
            Structured user prompt optimized for token efficiency
        """
        sections = []

        # Add context if provided (helps Perplexity synthesize better)
        if context:
            sections.append(f"[CONTEXT]: {context}")

        # Main query
        sections.append(f"[QUERY]: {query}")

        # Output format specification
        if output_format:
            sections.append(f"[OUTPUT FORMAT]: {output_format}")

        # Additional constraints
        if additional_constraints:
            constraints_str = " | ".join(additional_constraints)
            sections.append(f"[CONSTRAINTS]: {constraints_str}")

        # Verification requirement (reduces hallucinations)
        sections.append("[VERIFICATION]: Cite all sources. If information is incomplete, state what's missing.")

        prompt = "\n".join(sections)
        logger.debug(f"Structured prompt: {len(prompt)} chars")
        return prompt

    def build_research_prompt(
        self,
        query: str,
        context: Optional[str] = None,
        mode: Optional[SearchMode] = None,
        recency_filter: Optional[RecencyFilter] = RecencyFilter.MONTH,
        domain_filter: Optional[List[str]] = None,
        output_format: Optional[str] = None,
    ) -> StructuredPrompt:
        """
        Build complete structured prompt for research queries.

        Args:
            query: Research question
            context: Repository or domain context
            mode: Search mode (defaults to PRO for research)
            recency_filter: Time filter for sources (defaults to last month)
            domain_filter: Domains to search (e.g., ["perplexity.ai", "docs.anthropic.com"])
            output_format: Desired output structure

        Returns:
            StructuredPrompt with system message, user prompt, and API parameters

        Example:
            prompt = builder.build_research_prompt(
                query="What are Claude API best practices for 2025?",
                context="Milton AI assistant integration",
                domain_filter=["docs.anthropic.com", "anthropic.com"],
                output_format="Numbered list with actionable items"
            )
        """
        system_msg = self.build_system_message("research")

        user_prompt = self.structure_user_prompt(
            query=query,
            context=context,
            output_format=output_format,
            additional_constraints=[
                "Focus on official documentation and authoritative sources",
                "Include practical examples where applicable",
            ],
        )

        api_params = self.build_search_parameters(
            mode=mode or SearchMode.PRO,
            recency_filter=recency_filter,
            domain_filter=domain_filter,
            context_size=ContextSize.HIGH,
            return_citations=True,
        )

        logger.info(f"Built research prompt: query_len={len(query)}, context={bool(context)}")
        return StructuredPrompt(
            system_message=system_msg,
            user_prompt=user_prompt,
            api_parameters=api_params,
        )

    def build_specification_prompt(
        self,
        user_request: str,
        target_repo: str,
        repo_context: Optional[str] = None,
        mode: Optional[SearchMode] = None,
    ) -> StructuredPrompt:
        """
        Build structured prompt for generating code specifications.

        Args:
            user_request: User's coding request
            target_repo: Path to target repository
            repo_context: Summary of repository structure/technologies
            mode: Search mode (defaults to PRO)

        Returns:
            StructuredPrompt optimized for specification generation

        Example:
            prompt = builder.build_specification_prompt(
                user_request="Add user authentication to the app",
                target_repo="/home/user/myapp",
                repo_context="Python Flask app with SQLite database"
            )
        """
        system_msg = self.build_system_message("specification")

        # Build comprehensive context
        full_context = f"Repository: {target_repo}"
        if repo_context:
            full_context += f" | Tech Stack: {repo_context}"

        user_prompt = self.structure_user_prompt(
            query=f"Analyze this request and produce a detailed implementation specification:\n\n{user_request}",
            context=full_context,
            output_format=(
                "Structured specification with: "
                "1) Objective, 2) Technical constraints, 3) File boundaries, "
                "4) Testing requirements, 5) Implementation plan, 6) Deliverables"
            ),
            additional_constraints=[
                "Search for best practices and official documentation",
                "Include specific file paths and code patterns",
                "Provide testing commands to run",
                "Consider security implications",
            ],
        )

        # Focus on authoritative technical sources
        api_params = self.build_search_parameters(
            mode=mode or SearchMode.PRO,
            recency_filter=RecencyFilter.MONTH,
            domain_filter=[
                "docs.python.org",
                "docs.anthropic.com",
                "github.com",
                "stackoverflow.com",
            ],
            context_size=ContextSize.HIGH,
            return_citations=True,
        )

        logger.info(f"Built specification prompt for repo: {target_repo}")
        return StructuredPrompt(
            system_message=system_msg,
            user_prompt=user_prompt,
            api_parameters=api_params,
        )

    def build_documentation_search_prompt(
        self,
        topic: str,
        technology: str,
        specific_question: Optional[str] = None,
    ) -> StructuredPrompt:
        """
        Build prompt optimized for searching official documentation.

        Args:
            topic: Documentation topic (e.g., "API authentication")
            technology: Technology name (e.g., "Perplexity API", "Claude")
            specific_question: Specific question about the topic

        Returns:
            StructuredPrompt optimized for documentation search

        Example:
            prompt = builder.build_documentation_search_prompt(
                topic="structured prompting",
                technology="Perplexity API",
                specific_question="How to use search_domain_filter parameter?"
            )
        """
        query = f"{technology}: {topic}"
        if specific_question:
            query += f" - {specific_question}"

        system_msg = self.build_system_message("research")

        user_prompt = self.structure_user_prompt(
            query=query,
            context=f"Searching official {technology} documentation",
            output_format="Concise explanation with code examples and links to official docs",
            additional_constraints=[
                "Only use official documentation sources",
                "Include version information if applicable",
                "Provide working code examples",
            ],
        )

        # Restrict to official documentation domains
        tech_domains = {
            "Perplexity API": ["docs.perplexity.ai", "perplexity.ai"],
            "Claude": ["docs.anthropic.com", "anthropic.com"],
            "Python": ["docs.python.org", "python.org"],
        }

        domain_filter = tech_domains.get(technology, [])

        api_params = self.build_search_parameters(
            mode=SearchMode.PRO,
            recency_filter=RecencyFilter.MONTH,
            domain_filter=domain_filter if domain_filter else None,
            context_size=ContextSize.HIGH,
            return_citations=True,
        )

        logger.info(f"Built documentation search for: {technology} - {topic}")
        return StructuredPrompt(
            system_message=system_msg,
            user_prompt=user_prompt,
            api_parameters=api_params,
        )


def validate_prompt_structure(prompt: StructuredPrompt) -> bool:
    """
    Validate that a structured prompt has all required components.

    Args:
        prompt: StructuredPrompt to validate

    Returns:
        True if valid, False otherwise
    """
    if not prompt.system_message or len(prompt.system_message) < 10:
        logger.error("Invalid system message")
        return False

    if not prompt.user_prompt or len(prompt.user_prompt) < 5:
        logger.error("Invalid user prompt")
        return False

    if not prompt.api_parameters or "model" not in prompt.api_parameters:
        logger.error("Invalid API parameters - missing model")
        return False

    logger.debug("Prompt structure validated successfully")
    return True
