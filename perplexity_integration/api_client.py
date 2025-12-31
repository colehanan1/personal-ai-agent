"""
Enhanced Perplexity API client with structured prompting support

Features:
- Structured prompt handling with JSON schema (2025)
- Citation verification
- Response validation
- Token usage tracking
- Error handling with retries
- Pydantic model integration for structured outputs

References:
- https://docs.perplexity.ai/guides/structured-outputs
- Citation tokens are FREE in Perplexity 2025 (except Deep Research)
"""

import logging
import time
import json
from typing import Optional, Dict, Any, List, Type
from dataclasses import dataclass

import requests
from pydantic import BaseModel, ValidationError

from .prompting_system import StructuredPrompt, validate_prompt_structure
from .response_schemas import (
    ResearchResponse,
    SpecificationResponse,
    DocumentationSearchResponse,
    QuickFactResponse,
    get_schema_for_prompt_type,
)

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
        response_schema: Optional[Type[BaseModel]] = None,
        use_json_schema: bool = True,
    ) -> Optional[PerplexityResponse]:
        """
        Execute a structured prompt with Perplexity API.

        Args:
            prompt: StructuredPrompt containing system message, user prompt, and API params
            max_tokens: Maximum tokens to generate (optional)
            response_schema: Pydantic model for JSON schema validation (2025 feature)
            use_json_schema: Enable JSON schema structured outputs (default: True)

        Returns:
            PerplexityResponse with content and metadata, or None on failure

        Example:
            response = client.execute_structured_prompt(
                prompt,
                response_schema=ResearchResponse,
                use_json_schema=True
            )
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

        # Add JSON schema response_format if requested (2025 feature)
        if use_json_schema and response_schema:
            try:
                schema = response_schema.model_json_schema()
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": schema
                }
                logger.info(f"Using JSON schema for response: {response_schema.__name__}")
            except Exception as e:
                logger.warning(f"Failed to add JSON schema: {e}. Continuing without schema.")

        logger.info(
            f"Executing structured prompt: model={payload.get('model')}, "
            f"user_prompt_len={len(prompt.user_prompt)} chars, "
            f"json_schema={'enabled' if use_json_schema and response_schema else 'disabled'}"
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

                # If using JSON schema, validate and parse the structured response
                if use_json_schema and response_schema:
                    return self._parse_json_schema_response(
                        data,
                        response_schema,
                        prompt.api_parameters
                    )
                else:
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

    def _parse_json_schema_response(
        self,
        data: Dict[str, Any],
        schema_model: Type[BaseModel],
        api_params: Dict[str, Any],
    ) -> Optional[PerplexityResponse]:
        """
        Parse Perplexity API response with JSON schema validation.

        Args:
            data: Raw API response data
            schema_model: Pydantic model for validation
            api_params: Original API parameters used

        Returns:
            PerplexityResponse with validated structured content
        """
        try:
            # Extract raw content
            raw_content = data["choices"][0]["message"]["content"]

            # Parse JSON content
            try:
                json_content = json.loads(raw_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Raw content: {raw_content[:500]}")
                # Fallback to regular parsing
                return self._parse_response(data, api_params)

            # Validate against Pydantic schema
            try:
                validated_data = schema_model.model_validate(json_content)
                logger.info(f"JSON schema validation successful: {schema_model.__name__}")
            except ValidationError as e:
                logger.warning(f"JSON schema validation failed: {e}")
                logger.debug(f"JSON content: {json_content}")
                # Still return the content, but log validation issues
                validated_data = None

            # Extract model
            model = data.get("model", api_params.get("model", "unknown"))

            # Extract citations from API response (not from JSON structure)
            api_citations = data.get("citations", [])

            # Also extract citations from JSON structure if available
            json_citations = []
            if validated_data and hasattr(validated_data, 'sources'):
                json_citations = [s.url for s in validated_data.sources]

            # Merge citations (prefer API citations, add JSON citations)
            all_citations = api_citations + [c for c in json_citations if c not in api_citations]

            # Extract token usage
            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens")

            # Extract related questions if available
            related_questions = data.get("related_questions")

            # Verify citations presence
            has_citations = len(all_citations) > 0
            if self.verify_citations and not has_citations:
                logger.warning("Response has no citations - may be unreliable")

            # Check if response is complete
            finish_reason = data["choices"][0].get("finish_reason")
            is_complete = finish_reason == "stop"

            if not is_complete:
                logger.warning(f"Response incomplete: finish_reason={finish_reason}")

            # Format content for PerplexityResponse
            if validated_data:
                # Use the answer field from validated data
                if hasattr(validated_data, 'answer'):
                    content = validated_data.answer
                elif hasattr(validated_data, 'summary'):
                    content = validated_data.summary
                elif hasattr(validated_data, 'fact'):
                    content = validated_data.fact
                else:
                    content = json.dumps(json_content, indent=2)
            else:
                content = json.dumps(json_content, indent=2)

            response = PerplexityResponse(
                content=content,
                citations=all_citations,
                model=model,
                tokens_used=tokens_used,
                has_citations=has_citations,
                is_complete=is_complete,
                related_questions=related_questions,
            )

            logger.info(
                f"JSON schema response parsed: {len(content)} chars, "
                f"{len(all_citations)} citations, {tokens_used} tokens"
            )

            return response

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse JSON schema response: {e}", exc_info=True)
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
