"""Perplexity API client for research and prompt optimization"""

import logging
import time
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class PerplexityClient:
    """Client for Perplexity API"""

    API_ENDPOINT = "https://api.perplexity.ai/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "sonar-pro",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def chat(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """
        Send a chat completion request to Perplexity.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            The assistant's response text, or None on failure
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Calling Perplexity API (attempt {attempt + 1}/{self.max_retries})")
                response = self.session.post(
                    self.API_ENDPOINT,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"Perplexity API call successful. Response length: {len(content)} chars")
                return content

            except requests.exceptions.Timeout:
                logger.warning(f"Perplexity API timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                logger.error("Perplexity API timeout after all retries")
                return None

            except requests.exceptions.RequestException as e:
                logger.warning(f"Perplexity API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Perplexity API failed after all retries: {e}")
                return None

            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse Perplexity response: {e}")
                return None

        return None

    def research_and_optimize(self, user_request: str, target_repo: str) -> Optional[str]:
        """
        Research a coding request and produce an optimized specification.

        Args:
            user_request: The user's original request
            target_repo: Path to the target repository

        Returns:
            Optimized specification as a string, or None on failure
        """
        system_prompt = """You are an expert software architect and prompt engineer.
Your task is to analyze coding requests and produce detailed, actionable specifications
optimized for an AI coding assistant (Claude Code).

Given a user request, produce a structured specification that includes:
1. Clear objective and context
2. Technical constraints (language, frameworks, dependencies)
3. File and directory boundaries
4. Testing requirements (commands to run)
5. Code style and best practices
6. Deliverables summary
7. Step-by-step implementation plan

Be specific, concrete, and thorough. Focus on what needs to be built, not how to build it.
"""

        user_prompt = f"""Repository: {target_repo}

User Request: {user_request}

Please analyze this request and produce a detailed specification for implementing it.
Structure your response as a clear, actionable specification that a coding AI can follow."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return self.chat(messages, temperature=0.2)

    def close(self):
        """Close the session"""
        self.session.close()


def fallback_prompt_optimizer(user_request: str, target_repo: str) -> str:
    """
    Simple local fallback when Perplexity is unavailable.

    Args:
        user_request: The user's original request
        target_repo: Path to the target repository

    Returns:
        A basic optimized prompt
    """
    logger.info("Using fallback prompt optimizer (Perplexity unavailable)")

    # Extract key components
    is_test_request = any(word in user_request.lower() for word in ["test", "pytest", "unittest"])
    is_bug_fix = any(word in user_request.lower() for word in ["fix", "bug", "error", "issue"])
    is_feature = any(word in user_request.lower() for word in ["add", "implement", "create", "new"])

    spec_parts = [
        f"# Specification",
        f"",
        f"## Objective",
        f"{user_request}",
        f"",
        f"## Context",
        f"- Target Repository: {target_repo}",
        f"- Request Type: {'Bug Fix' if is_bug_fix else 'Feature' if is_feature else 'Task'}",
        f"",
        f"## Requirements",
        f"- Follow existing code style and patterns in the repository",
        f"- Ensure code is well-tested and production-ready",
    ]

    if is_test_request:
        spec_parts.append("- Write comprehensive tests using pytest")
        spec_parts.append("- Ensure all tests pass before completion")

    spec_parts.extend([
        "",
        "## Implementation Plan",
        "1. Analyze existing code structure",
        "2. Implement required changes",
    ])

    if is_test_request:
        spec_parts.append("3. Write and run tests")

    spec_parts.extend([
        f"{'4' if is_test_request else '3'}. Verify the solution works as expected",
        "",
        "## Deliverables",
        "- Modified/new files with implementation",
        "- Test results (if applicable)",
        "- Summary of changes made",
    ])

    return "\n".join(spec_parts)
