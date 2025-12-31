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

        sections.append("### Git Workflow - CRITICAL")
        sections.append("**NEVER commit directly to main branch!**")
        sections.append("")
        sections.append("Before making any changes:")
        sections.append("1. Check current branch: `git branch --show-current`")
        sections.append("2. If on 'main', create a new feature branch:")
        sections.append(f"   `git checkout -b milton-ai-<task-description>-$(date +%Y%m%d)`")
        sections.append("3. Make all changes on the feature branch")
        sections.append("4. Commit with descriptive messages")
        sections.append("5. Do NOT merge to main - the user will review and merge later")
        sections.append("")
        sections.append("Branch naming convention: `milton-ai-<feature-name>-<YYYYMMDD>`")
        sections.append("Example: `milton-ai-add-auth-tests-20251231`")
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
        sections.append("1. **Git Branch Setup** - Check current branch and create new feature branch if needed")
        sections.append("2. **Explore** - Understand the existing codebase structure")
        sections.append("3. **Plan** - Identify files to modify or create")
        sections.append("4. **Implement** - Make the necessary code changes")
        sections.append("5. **Test** - Run tests and verify functionality")
        sections.append("6. **Commit** - Commit changes to the feature branch with clear messages")
        sections.append("7. **Report** - Provide a detailed summary (see below)")
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
        sections.append("GIT BRANCH:")
        sections.append("- Branch name: milton-ai-<feature>-<date>")
        sections.append("- Based on: main")
        sections.append("- Status: Changes committed (NOT merged to main)")
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
        sections.append("GIT COMMITS:")
        sections.append("- Commit hash: [git commit SHA]")
        sections.append("- Commit message: [description]")
        sections.append("")
        sections.append("NEXT STEPS:")
        sections.append("- Review the changes on branch milton-ai-<feature>-<date>")
        sections.append("- Run `git diff main` to see all changes")
        sections.append("- Merge to main when ready with `git checkout main && git merge <branch-name>`")
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

    def build_agent_prompt(
        self,
        user_request: str,
        research_notes: Optional[str] = None,
    ) -> str:
        """
        Build a tool-agnostic prompt for coding agents.

        Args:
            user_request: The original user request
            research_notes: Optional research/specification from Perplexity

        Returns:
            A structured, tool-agnostic prompt
        """
        logger.info("Building agent-agnostic job prompt")

        sections = []

        sections.append("# Code Agent Instructions")
        sections.append("")

        sections.append("## Context")
        sections.append(f"Repository: {self.target_repo}")
        sections.append(f"Request: {user_request}")
        sections.append("")

        if research_notes:
            sections.append("## Research & Specification")
            sections.append(research_notes)
            sections.append("")

        sections.append("## Execution Requirements")
        sections.append("- Read repository context before making changes")
        sections.append("- Propose a clear, step-by-step plan first")
        sections.append("- After the plan, implement the changes")
        sections.append("- Run unit tests with pytest and ensure they pass")
        sections.append("- Summarize changes: files changed, key decisions, and how to run tests")
        sections.append("")

        sections.append("## Security")
        sections.append("- Never commit secrets or credentials")
        sections.append("- Use environment variables for configuration")
        sections.append("- Validate inputs and handle edge cases")
        sections.append("")

        sections.append("## Notes")
        sections.append("- Work within the repository boundaries")
        sections.append("- If you encounter blockers, document them clearly")
        sections.append("")

        prompt = "\n".join(sections)
        logger.debug(f"Built agent prompt with {len(prompt)} characters")

        return prompt


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
