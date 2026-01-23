"""Conversation summarization for managing context window limits.

When conversations approach the model's context limit, this module:
1. Summarizes older messages into a concise summary
2. Keeps recent messages intact for natural flow
3. Maintains conversation continuity without hitting token limits
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# Token estimation: ~4 chars per token (rough approximation)
CHARS_PER_TOKEN = 4

# Context management thresholds
DEFAULT_MAX_CONTEXT = 8192  # Model's max context window
SUMMARIZATION_TRIGGER = 0.70  # Summarize when 70% full
KEEP_RECENT_MESSAGES = 10  # Always keep last N messages unsummarized


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.
    
    Args:
        text: Text to estimate
    
    Returns:
        Estimated token count
    """
    return len(text) // CHARS_PER_TOKEN


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens in message list.
    
    Args:
        messages: List of message dicts with 'content' and 'role'
    
    Returns:
        Estimated total token count
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "")
        total += estimate_tokens(content) + estimate_tokens(role) + 4  # +4 for formatting
    return total


def should_summarize(
    messages: List[Dict[str, Any]],
    max_tokens: int = DEFAULT_MAX_CONTEXT,
    trigger_ratio: float = SUMMARIZATION_TRIGGER
) -> bool:
    """Check if conversation should be summarized.
    
    Args:
        messages: List of conversation messages
        max_tokens: Maximum context window size
        trigger_ratio: Trigger summarization at this % of max
    
    Returns:
        True if should summarize
    """
    if len(messages) <= KEEP_RECENT_MESSAGES:
        return False
    
    estimated = estimate_messages_tokens(messages)
    threshold = int(max_tokens * trigger_ratio)
    
    should_trigger = estimated > threshold
    
    if should_trigger:
        logger.info(f"Summarization triggered: {estimated} tokens > {threshold} threshold")
    
    return should_trigger


def create_summary_prompt(messages: List[Dict[str, Any]]) -> str:
    """Create a prompt to summarize conversation messages.
    
    Args:
        messages: Messages to summarize
    
    Returns:
        Prompt for LLM to create summary
    """
    # Format messages for summarization
    conversation_text = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        conversation_text.append(f"{role.upper()}: {content}")
    
    conv_str = "\n\n".join(conversation_text)
    
    prompt = f"""Summarize this conversation concisely, preserving key facts, decisions, and context. 
Focus on what's important to remember for future messages.

Conversation:
{conv_str}

Summary (2-4 sentences):"""
    
    return prompt


async def summarize_conversation(
    messages: List[Dict[str, Any]],
    llm_client,
    keep_recent: int = KEEP_RECENT_MESSAGES
) -> Tuple[List[Dict[str, Any]], str]:
    """Summarize old messages and keep recent ones.
    
    Args:
        messages: Full conversation history
        llm_client: LLM client for generating summary
        keep_recent: Number of recent messages to keep unsummarized
    
    Returns:
        Tuple of (new_messages, summary_text)
        new_messages = [summary_message] + recent_messages
    """
    if len(messages) <= keep_recent:
        logger.warning("Not enough messages to summarize")
        return messages, ""
    
    # Split: old messages to summarize, recent to keep
    messages_to_summarize = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]
    
    # Skip system messages in summarization
    non_system = [m for m in messages_to_summarize if m.get("role") != "system"]
    
    if not non_system:
        logger.info("Only system messages in old context, keeping all")
        return messages, ""
    
    # Create summary prompt
    summary_prompt = create_summary_prompt(non_system)
    
    try:
        # Generate summary using LLM
        summary_response = await llm_client.chat_completion(
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            max_tokens=300,
            stream=False
        )
        
        # Extract content from response (OpenAI format)
        if "choices" in summary_response and len(summary_response["choices"]) > 0:
            summary_text = summary_response["choices"][0]["message"]["content"]
        else:
            summary_text = summary_response.get("content", "Previous conversation context.")
        
        logger.info(f"Created summary of {len(non_system)} messages → {len(summary_text)} chars")
        
        # Build new message list: system + summary + recent
        new_messages = []
        
        # Keep system messages
        system_messages = [m for m in messages if m.get("role") == "system"]
        new_messages.extend(system_messages)
        
        # Add summary as system message
        new_messages.append({
            "role": "system",
            "content": f"**Previous Conversation Summary:**\n{summary_text}"
        })
        
        # Add recent messages
        new_messages.extend(recent_messages)
        
        return new_messages, summary_text
    
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        # Fallback: just keep recent messages
        return recent_messages, ""


def format_summary_message(summary: str, message_count: int) -> str:
    """Format a summary message for display.
    
    Args:
        summary: Summary text
        message_count: Number of messages summarized
    
    Returns:
        Formatted message
    """
    return f"""📋 **Conversation Summarized**

Summarized {message_count} earlier messages to manage context:

{summary}

_(Continuing conversation with recent messages...)_"""
