"""
Git operations for self-upgrade workflow.

Provides branch management and diff generation.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .policy import is_protected_branch
from .runner import SafeCommandRunner

logger = logging.getLogger(__name__)


@dataclass
class GitStatus:
    """Git repository status."""
    current_branch: str
    is_protected: bool
    has_uncommitted: bool
    uncommitted_files: List[str]


class GitOperations:
    """Git operations for self-upgrade."""
    
    def __init__(self, repo_root: Path, runner: SafeCommandRunner):
        self.repo_root = Path(repo_root)
        self.runner = runner
    
    def get_current_branch(self) -> str:
        """Get current git branch name."""
        result = self.runner.run("git branch --show-current")
        if not result.success:
            raise RuntimeError(f"Failed to get current branch: {result.stderr}")
        return result.stdout.strip()
    
    def get_status(self) -> GitStatus:
        """Get detailed git status."""
        current_branch = self.get_current_branch()
        is_prot = is_protected_branch(current_branch)
        
        # Check for uncommitted changes
        result = self.runner.run("git status --porcelain")
        uncommitted_files = []
        if result.success and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    # Format: " M filename" or "?? filename"
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        uncommitted_files.append(parts[1])
        
        return GitStatus(
            current_branch=current_branch,
            is_protected=is_prot,
            has_uncommitted=bool(uncommitted_files),
            uncommitted_files=uncommitted_files,
        )
    
    def ensure_not_on_main(self) -> None:
        """
        Ensure we're not on a protected branch.
        
        Raises:
            RuntimeError: If on a protected branch
        """
        status = self.get_status()
        if status.is_protected:
            raise RuntimeError(
                f"BLOCKED: Currently on protected branch '{status.current_branch}'. "
                f"Self-upgrade cannot operate on protected branches."
            )
        logger.info(f"[GIT] Confirmed not on protected branch (current: {status.current_branch})")
    
    def create_branch(self, topic: str) -> str:
        """
        Create and checkout a new self-upgrade branch.
        
        Args:
            topic: Short topic slug for branch name
        
        Returns:
            Full branch name (e.g., "self-upgrade/add-logging")
        
        Raises:
            RuntimeError: If branch creation fails
        """
        # Sanitize topic
        topic_slug = re.sub(r"[^a-z0-9-]", "-", topic.lower()).strip("-")
        topic_slug = re.sub(r"-+", "-", topic_slug)[:50]  # Max 50 chars
        
        branch_name = f"self-upgrade/{topic_slug}"
        
        # Create and checkout branch
        self.runner.run_checked(f"git checkout -b {branch_name}")
        logger.info(f"[GIT] Created and checked out branch: {branch_name}")
        
        return branch_name
    
    def stage_files(self, file_paths: List[str]) -> None:
        """
        Stage files for commit.
        
        Args:
            file_paths: List of file paths to stage
        
        Raises:
            RuntimeError: If staging fails
        """
        if not file_paths:
            return
        
        for file_path in file_paths:
            self.runner.run_checked(f"git add {file_path}")
        
        logger.info(f"[GIT] Staged {len(file_paths)} file(s)")
    
    def commit_changes(self, message: str) -> None:
        """
        Commit staged changes.
        
        Args:
            message: Commit message
        
        Raises:
            RuntimeError: If commit fails
        """
        # Escape message for shell
        escaped_msg = message.replace('"', '\\"')
        self.runner.run_checked(f'git commit -m "{escaped_msg}"')
        logger.info(f"[GIT] Committed changes: {message[:50]}...")
    
    def generate_diff(self, base_branch: str = "main") -> str:
        """
        Generate diff against base branch.
        
        Args:
            base_branch: Base branch to diff against (default: main)
        
        Returns:
            Full diff text
        
        Raises:
            RuntimeError: If diff generation fails
        """
        # Use merge-base to find common ancestor
        result = self.runner.run(f"git merge-base {base_branch} HEAD")
        if result.success:
            merge_base = result.stdout.strip()
            diff_result = self.runner.run(f"git diff {merge_base}..HEAD")
        else:
            # Fallback to simple diff
            diff_result = self.runner.run(f"git diff {base_branch}...HEAD")
        
        if not diff_result.success:
            raise RuntimeError(f"Failed to generate diff: {diff_result.stderr}")
        
        return diff_result.stdout
    
    def get_changed_files(self) -> List[str]:
        """
        Get list of files changed in current branch vs main.
        
        Returns:
            List of changed file paths
        """
        result = self.runner.run("git diff --name-only main...HEAD")
        if not result.success:
            return []
        
        files = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return files
