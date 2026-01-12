"""LLM client for Milton Chat Gateway with streaming support."""

import logging
import os
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for the underlying LLM API (vLLM/Ollama compatible)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = (
            base_url or os.getenv("LLM_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "llama31-8b-instruct"
        )
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        stop: list[str] | None = None,
    ) -> dict | AsyncIterator[str]:
        """
        Send a chat completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            stop: Stop sequences to end generation

        Returns:
            Full response dict if stream=False, or async iterator of SSE lines if stream=True
        """
        # Default stop sequences to prevent runaway generation
        if stop is None:
            stop = ["assistant\n", "\nassistant", "<|eot_id|>", "<|end|>"]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "stop": stop,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        endpoint = f"{self.base_url}/v1/chat/completions"

        if stream:
            return self._stream_response(endpoint, payload)
        else:
            return await self._blocking_response(endpoint, payload)

    async def _blocking_response(self, endpoint: str, payload: dict) -> dict:
        """Make a non-streaming request."""
        client = await self.get_client()
        logger.debug(f"Making request to {endpoint}")
        response = await client.post(
            endpoint,
            json=payload,
            headers=self.headers,
        )
        if not response.is_success:
            error_text = response.text
            logger.error(f"LLM API error: {response.status_code} - {error_text}")
            raise httpx.HTTPStatusError(
                f"LLM API error: {response.status_code}",
                request=response.request,
                response=response,
            )
        return response.json()

    async def _stream_response(
        self, endpoint: str, payload: dict
    ) -> AsyncIterator[str]:
        """Stream SSE response from the LLM."""
        client = await self.get_client()
        logger.debug(f"Starting streaming request to {endpoint}")

        async with client.stream(
            "POST",
            endpoint,
            json=payload,
            headers=self.headers,
        ) as response:
            if not response.is_success:
                error_text = await response.aread()
                logger.error(
                    f"LLM API streaming error: {response.status_code} - {error_text}"
                )
                raise httpx.HTTPStatusError(
                    f"LLM API error: {response.status_code}",
                    request=response.request,
                    response=response,
                )

            async for line in response.aiter_lines():
                if line:
                    yield line

    async def check_health(self) -> bool:
        """Check if the LLM API is reachable."""
        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.base_url}/v1/models",
                headers=self.headers,
                timeout=5.0,
            )
            return response.is_success
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            return False
