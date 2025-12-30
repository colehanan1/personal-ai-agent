"""Agent system package."""
from pathlib import Path


def load_agent_context(agent: str) -> str:
    """
    Load agent system prompt by concatenating SHARED_CONTEXT + agent-specific prompt.

    Args:
        agent: Agent name (NEXUS, CORTEX, or FRONTIER)

    Returns:
        Combined system prompt for the agent

    Example:
        >>> nexus_prompt = load_agent_context("NEXUS")
        >>> # Use nexus_prompt as system message for LLM
    """
    prompts_dir = Path(__file__).parent.parent / "Prompts"

    shared = (prompts_dir / "SHARED_CONTEXT.md").read_text()
    agent_specific = (prompts_dir / f"{agent}_v1.1.md").read_text()

    return f"{shared}\n\n---\n\n{agent_specific}"
