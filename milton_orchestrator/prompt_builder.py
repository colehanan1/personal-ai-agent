"""Build optimized prompts for Claude Code"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ClaudePromptBuilder:
    """Builds structured prompts for Claude Code"""

    def __init__(self, target_repo: Path):
        self.target_repo = target_repo

    def build_job_prompt(
        self,
        user_request: str,
        research_notes: Optional[str] = None,
    ) -> str:
        """
        Build a comprehensive job prompt for Claude Code.

        Args:
            user_request: The original user request
            research_notes: Optional research/specification from Perplexity

        Returns:
            A structured prompt for Claude Code
        """
        logger.info("Building Claude Code job prompt")

        sections = []

        # Header
        sections.append("# Code Implementation Request")
        sections.append("")

        # Context section
        sections.append("## Context")
        sections.append(f"Repository: {self.target_repo}")
        sections.append(f"Request: {user_request}")
        sections.append("")

        # Research/Specification section
        if research_notes:
            sections.append("## Research & Specification")
            sections.append(research_notes)
            sections.append("")

        # Requirements section
        sections.append("## Implementation Requirements")
        sections.append("")
        sections.append("### Code Quality")
        sections.append("- Follow existing code patterns and style in the repository")
        sections.append("- Write clean, maintainable, and well-documented code")
        sections.append("- Use type hints where applicable (Python 3.11+)")
        sections.append("- Handle errors gracefully with proper logging")
        sections.append("")

        sections.append("### Testing")
        sections.append("- Write unit tests for new functionality using pytest")
        sections.append("- Ensure all existing tests still pass")
        sections.append("- Run tests before considering the task complete")
        sections.append("")

        sections.append("### Security")
        sections.append("- Never commit secrets or credentials")
        sections.append("- Use environment variables for configuration")
        sections.append("- Validate inputs and handle edge cases")
        sections.append("")

        # Implementation plan
        sections.append("## Implementation Plan")
        sections.append("")
        sections.append("Follow these steps:")
        sections.append("1. **Explore** - Understand the existing codebase structure")
        sections.append("2. **Plan** - Identify files to modify or create")
        sections.append("3. **Implement** - Make the necessary code changes")
        sections.append("4. **Test** - Run tests and verify functionality")
        sections.append("5. **Report** - Provide a detailed summary (see below)")
        sections.append("")

        # Deliverables
        sections.append("## Required Deliverables")
        sections.append("")
        sections.append("Your implementation must include:")
        sections.append("- All modified or newly created files")
        sections.append("- Test results (if tests were run)")
        sections.append("- Any relevant command outputs")
        sections.append("")

        # Report section
        sections.append("## Final Report Format")
        sections.append("")
        sections.append("At the end of your work, provide a summary in this format:")
        sections.append("")
        sections.append("```")
        sections.append("=== IMPLEMENTATION SUMMARY ===")
        sections.append("")
        sections.append("FILES MODIFIED:")
        sections.append("- path/to/file1.py: description of changes")
        sections.append("- path/to/file2.py: description of changes")
        sections.append("")
        sections.append("FILES CREATED:")
        sections.append("- path/to/newfile.py: purpose")
        sections.append("")
        sections.append("TESTS RUN:")
        sections.append("- Command: pytest tests/")
        sections.append("- Result: [PASS/FAIL]")
        sections.append("- Details: [summary]")
        sections.append("")
        sections.append("NEXT STEPS:")
        sections.append("- [Any follow-up actions needed]")
        sections.append("```")
        sections.append("")

        sections.append("## Notes")
        sections.append("- Work within the repository boundaries")
        sections.append("- If you encounter blockers, document them clearly")
        sections.append("- Ask for clarification if requirements are ambiguous")
        sections.append("")

        prompt = "\n".join(sections)
        logger.debug(f"Built prompt with {len(prompt)} characters")

        return prompt

    def build_research_only_prompt(self, user_request: str) -> str:
        """
        Build a prompt for research-only requests.

        Args:
            user_request: The user's research request

        Returns:
            A structured prompt for research
        """
        logger.info("Building research-only prompt")

        sections = [
            "# Research Request",
            "",
            f"Repository: {self.target_repo}",
            "",
            "## Task",
            user_request,
            "",
            "## Instructions",
            "Please investigate and provide a detailed response without making any code changes.",
            "",
            "Include in your response:",
            "- Relevant files and code locations",
            "- Key findings",
            "- Recommendations or next steps",
            "",
        ]

        return "\n".join(sections)


def extract_command_type(message: str) -> tuple[str, str]:
    """
    Extract command type and actual content from message.

    Args:
        message: The raw message from ntfy

    Returns:
        Tuple of (command_type, content) where command_type is 'CODE', 'RESEARCH', or 'CODE' (default)
    """
    message = message.strip()

    # Check for explicit command prefixes
    if message.upper().startswith("CODE:"):
        return "CODE", message[5:].strip()
    elif message.upper().startswith("RESEARCH:"):
        return "RESEARCH", message[9:].strip()

    # Default to CODE for backward compatibility
    return "CODE", message
