"""
Enhanced Perplexity API client with structured prompting support

Features:
- Structured prompt handling
- Citation verification
- Response validation
- Token usage tracking
- Error handling with retries
"""

import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import requests

from .prompting_system import StructuredPrompt, validate_prompt_structure

logger = logging.getLogger(__name__)


@dataclass
class PerplexityResponse:
    """Container for Perplexity API response with metadata"""
    content: str
    citations: List[str]
    model: str
    tokens_used: Optional[int] = None
    has_citations: bool = False
    is_complete: bool = True
    related_questions: Optional[List[str]] = None


class PerplexityAPIClient:
    """
    Enhanced Perplexity API client with structured prompting support.

    Features:
    - Structured prompt execution
    - Automatic citation verification
    - Token usage tracking
    - Response validation
    - Retry logic with exponential backoff

    Example:
        client = PerplexityAPIClient(api_key="your-key")
        prompt = builder.build_research_prompt(...)
        response = client.execute_structured_prompt(prompt)
        if response.has_citations:
            print(f"Found {len(response.citations)} sources")
    """

    API_ENDPOINT = "https://api.perplexity.ai/chat/completions"

    def __init__(
        self,
        api_key: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_citations: bool = True,
    ):
        """
        Initialize the Perplexity API client.

        Args:
            api_key: Perplexity API key
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            verify_citations: Whether to verify citation presence
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_citations = verify_citations

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

        logger.info(
            f"PerplexityAPIClient initialized: timeout={timeout}s, "
            f"max_retries={max_retries}, verify_citations={verify_citations}"
        )

    def execute_structured_prompt(
        self,
        prompt: StructuredPrompt,
        max_tokens: Optional[int] = None,
    ) -> Optional[PerplexityResponse]:
        """
        Execute a structured prompt with Perplexity API.

        Args:
            prompt: StructuredPrompt containing system message, user prompt, and API params
            max_tokens: Maximum tokens to generate (optional)

        Returns:
            PerplexityResponse with content and metadata, or None on failure

        Example:
            response = client.execute_structured_prompt(prompt)
            if response and response.has_citations:
                print(f"Answer: {response.content}")
                print(f"Sources: {response.citations}")
        """
        # Validate prompt structure
        if not validate_prompt_structure(prompt):
            logger.error("Invalid prompt structure")
            return None

        # Build messages
        messages = [
            {"role": "system", "content": prompt.system_message},
            {"role": "user", "content": prompt.user_prompt},
        ]

        # Build payload with API parameters
        payload = {
            "messages": messages,
            **prompt.api_parameters,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        logger.info(
            f"Executing structured prompt: model={payload.get('model')}, "
            f"user_prompt_len={len(prompt.user_prompt)} chars"
        )

        # Execute with retry logic
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    self.API_ENDPOINT,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()
                return self._parse_response(data, prompt.api_parameters)

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error("Request timeout after all retries")
                return None

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Request failed after all retries: {e}")
                return None

            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                return None

        return None

    def _parse_response(
        self,
        data: Dict[str, Any],
        api_params: Dict[str, Any],
    ) -> Optional[PerplexityResponse]:
        """
        Parse Perplexity API response and extract metadata.

        Args:
            data: Raw API response data
            api_params: Original API parameters used

        Returns:
            PerplexityResponse with parsed content and metadata
        """
        try:
            # Extract content
            content = data["choices"][0]["message"]["content"]

            # Extract model
            model = data.get("model", api_params.get("model", "unknown"))

            # Extract citations if available
            citations = data.get("citations", [])

            # Extract token usage
            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens")

            # Extract related questions if requested
            related_questions = data.get("related_questions")

            # Verify citations presence
            has_citations = len(citations) > 0
            if self.verify_citations and not has_citations:
                logger.warning("Response has no citations - may be unreliable")

            # Check if response is complete
            finish_reason = data["choices"][0].get("finish_reason")
            is_complete = finish_reason == "stop"

            if not is_complete:
                logger.warning(f"Response incomplete: finish_reason={finish_reason}")

            response = PerplexityResponse(
                content=content,
                citations=citations,
                model=model,
                tokens_used=tokens_used,
                has_citations=has_citations,
                is_complete=is_complete,
                related_questions=related_questions,
            )

            logger.info(
                f"Response parsed: {len(content)} chars, "
                f"{len(citations)} citations, {tokens_used} tokens"
            )

            return response

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse response: {e}", exc_info=True)
            return None

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "sonar-pro",
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Direct chat interface (backward compatible with existing code).

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional API parameters

        Returns:
            Response content as string, or None on failure
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Chat API call (attempt {attempt + 1}/{self.max_retries})")
                response = self.session.post(
                    self.API_ENDPOINT,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"Chat response: {len(content)} chars")
                return content

            except requests.exceptions.Timeout:
                logger.warning(f"Chat timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error("Chat timeout after all retries")
                return None

            except requests.exceptions.RequestException as e:
                logger.warning(f"Chat error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Chat failed after all retries: {e}")
                return None

            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse chat response: {e}")
                return None

        return None

    def validate_response_quality(self, response: PerplexityResponse) -> Dict[str, Any]:
        """
        Validate response quality based on citations and completeness.

        Args:
            response: PerplexityResponse to validate

        Returns:
            Dictionary with validation results and recommendations

        Example:
            validation = client.validate_response_quality(response)
            if not validation["is_reliable"]:
                print(f"Warning: {validation['issues']}")
        """
        issues = []
        warnings = []

        # Check citations
        if not response.has_citations:
            issues.append("No citations found - answer may be unreliable")
        elif len(response.citations) == 1:
            warnings.append("Only one citation - consider requesting more sources")

        # Check completeness
        if not response.is_complete:
            issues.append("Response was truncated - increase max_tokens or simplify query")

        # Check content length
        if len(response.content) < 50:
            warnings.append("Very short response - query may be too narrow")

        is_reliable = len(issues) == 0 and response.has_citations
        needs_clarification = not response.is_complete or len(response.content) < 50

        validation = {
            "is_reliable": is_reliable,
            "needs_clarification": needs_clarification,
            "has_citations": response.has_citations,
            "citation_count": len(response.citations),
            "is_complete": response.is_complete,
            "issues": issues,
            "warnings": warnings,
        }

        if issues:
            logger.warning(f"Response quality issues: {issues}")
        if warnings:
            logger.info(f"Response quality warnings: {warnings}")

        return validation

    def close(self):
        """Close the session"""
        self.session.close()
        logger.info("PerplexityAPIClient session closed")
