"""Base agent class with LLM interface."""
import os
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

from agents.memory_hooks import (
    build_memory_context,
    record_memory,
    should_store_responses,
)

load_dotenv()


class BaseAgent:
    """Base class for all agents (NEXUS, CORTEX, FRONTIER)."""

    def __init__(self, agent_name: str):
        """
        Initialize base agent.

        Args:
            agent_name: Name of the agent (NEXUS, CORTEX, FRONTIER)
        """
        self.agent_name = agent_name
        self.llm_url = os.getenv("LLM_API_URL", "http://localhost:8000")
        self.model_name = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load agent system prompt from Prompts folder."""
        from . import load_agent_context
        return load_agent_context(self.agent_name)

    def _call_llm(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        """
        Call local LLM (vLLM) via OpenAI-compatible API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            LLM response text

        Raises:
            RuntimeError: If LLM call fails
        """
        url = f"{self.llm_url}/v1/chat/completions"
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = requests.post(url, json=payload, timeout=120, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to LLM at {self.llm_url}. "
                "Is vLLM server running? Start with: python scripts/start_vllm.py"
            )
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def generate(
        self,
        user_message: str,
        context: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """
        Generate response to user message.

        Args:
            user_message: User's input message
            context: Optional conversation history
            **kwargs: Additional arguments for LLM call

        Returns:
            Agent's response
        """
        memory_type = kwargs.pop("memory_type", "crumb")
        memory_tags = kwargs.pop("memory_tags", None)
        memory_importance = kwargs.pop("memory_importance", None)
        memory_request_id = kwargs.pop("memory_request_id", None)
        store_response = kwargs.pop("memory_store_response", None)

        messages = []

        # Add system prompt
        messages.append({"role": "system", "content": self.system_prompt})

        memory_context = build_memory_context(self.agent_name, user_message)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        # Add context if provided
        if context:
            messages.extend(context)

        # Add user message
        messages.append({"role": "user", "content": user_message})

        response = self._call_llm(messages, **kwargs)

        record_memory(
            self.agent_name,
            user_message,
            memory_type=memory_type,
            tags=memory_tags,
            importance=memory_importance,
            source="user",
            request_id=memory_request_id,
        )
        if store_response is True or (store_response is None and should_store_responses()):
            record_memory(
                self.agent_name,
                response,
                memory_type="crumb",
                tags=["response"],
                importance=0.1,
                source="assistant",
                request_id=memory_request_id,
            )

        return response
