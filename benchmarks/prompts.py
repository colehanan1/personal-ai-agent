"""
Fixed prompt set for benchmarking.

Provides a curated set of prompts for consistent benchmarking across
different models and configurations. No network required.
"""
from typing import List, Dict, Any


BENCHMARK_PROMPTS = [
    {
        "id": "simple_qa",
        "prompt": "What is the capital of France?",
        "category": "factual",
        "expected_tokens": 10,
    },
    {
        "id": "reasoning",
        "prompt": "If a train travels 120 miles in 2 hours, what is its average speed in miles per hour?",
        "category": "reasoning",
        "expected_tokens": 30,
    },
    {
        "id": "code_gen",
        "prompt": "Write a Python function to calculate the factorial of a number.",
        "category": "code",
        "expected_tokens": 100,
    },
    {
        "id": "summarization",
        "prompt": "Summarize the main benefits of regular exercise in 3-4 sentences.",
        "category": "summarization",
        "expected_tokens": 80,
    },
    {
        "id": "creative",
        "prompt": "Write a short poem about artificial intelligence.",
        "category": "creative",
        "expected_tokens": 60,
    },
    {
        "id": "instruction",
        "prompt": "Explain how to make a cup of tea in simple steps.",
        "category": "instruction",
        "expected_tokens": 100,
    },
    {
        "id": "analysis",
        "prompt": "What are the pros and cons of remote work?",
        "category": "analysis",
        "expected_tokens": 120,
    },
    {
        "id": "conversation",
        "prompt": "Hi! Can you help me understand what machine learning is?",
        "category": "conversation",
        "expected_tokens": 100,
    },
]


def get_all_prompts() -> List[Dict[str, Any]]:
    """
    Get all benchmark prompts.
    
    Returns:
        List of prompt dictionaries with id, prompt, category, expected_tokens
    """
    return BENCHMARK_PROMPTS.copy()


def get_prompts_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Get prompts filtered by category.
    
    Args:
        category: Category to filter by (factual, reasoning, code, etc.)
    
    Returns:
        List of matching prompts
    """
    return [p for p in BENCHMARK_PROMPTS if p["category"] == category]


def get_prompt_by_id(prompt_id: str) -> Dict[str, Any]:
    """
    Get a specific prompt by ID.
    
    Args:
        prompt_id: Prompt ID
    
    Returns:
        Prompt dictionary
    
    Raises:
        ValueError: If prompt ID not found
    """
    for prompt in BENCHMARK_PROMPTS:
        if prompt["id"] == prompt_id:
            return prompt.copy()
    raise ValueError(f"Prompt ID not found: {prompt_id}")


def get_quick_prompts(count: int = 3) -> List[Dict[str, Any]]:
    """
    Get a quick subset of prompts for fast testing.
    
    Args:
        count: Number of prompts to return
    
    Returns:
        List of prompt dictionaries
    """
    return BENCHMARK_PROMPTS[:count]


def get_categories() -> List[str]:
    """
    Get all available prompt categories.
    
    Returns:
        List of category names
    """
    return sorted(set(p["category"] for p in BENCHMARK_PROMPTS))
