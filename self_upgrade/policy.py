"""
Policy enforcement for self-upgrade operations.

Defines allow/deny lists and validation logic.
"""
import fnmatch
import os
import re
from pathlib import Path
from typing import List, Tuple

# Protected branches - Milton cannot operate on these
PROTECTED_BRANCHES = [
    "main",
    "master",
    "production",
    "prod",
    "deploy",
]

# Denied file patterns (globs)
DENIED_FILE_PATTERNS = [
    "**/.env",
    "**/.env.*",
    "**/secrets/*",
    "**/*key*",
    "**/*token*",
    "**/id_rsa*",
    "**/credentials/*",
    "**/config/prod*",
    "**/production/*",
]

# Denied directories (no editing)
DENIED_DIRECTORIES = [
    ".git",
    "logs",
    "outputs",
    "cache",
    "__pycache__",
    ".pytest_cache",
    "milton_outputs",
    "shared_outputs",
]

# Self-upgrade directories (require override to edit)
SELF_UPGRADE_PROTECTED = [
    "self_upgrade",
    "docs/SELF_UPGRADE_POLICY.md",
]

# Denied command patterns (regex)
DENIED_COMMANDS = [
    r"git\s+push",
    r"git\s+merge",
    r"git\s+rebase",
    r"git\s+commit\s+--amend",
    r"git\s+checkout\s+(main|master|production|prod|deploy)",
    r"systemctl",
    r"docker-compose\s+(up|restart)",
    r"service\s+",
    r"ufw\s+",
    r"iptables",
    r"rm\s+-rf\s+/",
    r"chmod\s+777",
]

# Allowed commands (must match one of these patterns)
ALLOWED_COMMANDS = [
    r"git\s+status",
    r"git\s+checkout\s+-b\s+self-upgrade/[\w-]+",
    r"git\s+add\s+",
    r"git\s+commit\s+-m\s+",
    r"git\s+diff",
    r"git\s+branch",
    r"git\s+log",
    r"pytest\s+",
    r"python\s+-m\s+pytest",
    r"rg\s+",
    r"find\s+",
    r"cat\s+",
    r"ls\s+",
    r"echo\s+",
]

# Operational limits
DEFAULT_MAX_FILES_CHANGED = 10
DEFAULT_MAX_LOC_CHANGED = 400
DEFAULT_COMMAND_TIMEOUT = 300  # 5 minutes


def is_protected_branch(branch_name: str) -> bool:
    """Check if branch is protected."""
    return branch_name.lower() in PROTECTED_BRANCHES


def is_denied_file(file_path: str) -> bool:
    """Check if file matches denied patterns."""
    p = Path(file_path)
    path_str = str(p)
    
    # Check denied directories
    for denied_dir in DENIED_DIRECTORIES:
        if denied_dir in p.parts:
            return True
    
    # Check denied patterns using fnmatch
    for pattern in DENIED_FILE_PATTERNS:
        # fnmatch handles glob patterns like **/config/prod*
        if fnmatch.fnmatch(path_str, pattern):
            return True
        # Also try without leading **/ for relative paths
        if pattern.startswith("**/"):
            simple_pattern = pattern[3:]
            if fnmatch.fnmatch(path_str, simple_pattern):
                return True
    
    return False


def is_self_upgrade_protected(file_path: str) -> bool:
    """Check if file is part of self-upgrade system (requires override)."""
    p = Path(file_path)
    for protected in SELF_UPGRADE_PROTECTED:
        if str(p).startswith(protected):
            return True
    return False


def allow_self_upgrade_edits() -> bool:
    """Check if self-upgrade edits are allowed via override."""
    return os.getenv("MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS", "0") == "1"


def is_denied_command(command: str) -> Tuple[bool, str]:
    """
    Check if command matches denied patterns.
    
    Returns:
        (is_denied, reason)
    """
    for pattern in DENIED_COMMANDS:
        if re.search(pattern, command):
            return True, f"Command matches denied pattern: {pattern}"
    return False, ""


def is_allowed_command(command: str) -> Tuple[bool, str]:
    """
    Check if command matches allowed patterns.
    
    Returns:
        (is_allowed, reason)
    """
    for pattern in ALLOWED_COMMANDS:
        if re.search(pattern, command):
            return True, f"Command matches allowed pattern: {pattern}"
    return False, "Command does not match any allowed pattern"


def validate_command(command: str) -> Tuple[bool, str]:
    """
    Validate command against policy.
    
    Returns:
        (is_valid, reason)
    """
    # Check denied first (takes precedence)
    is_denied, deny_reason = is_denied_command(command)
    if is_denied:
        return False, deny_reason
    
    # Check allowed
    is_allowed, allow_reason = is_allowed_command(command)
    if not is_allowed:
        return False, allow_reason
    
    return True, "Command allowed"


def validate_files(file_paths: List[str]) -> Tuple[bool, str, List[str]]:
    """
    Validate list of files against policy.
    
    Returns:
        (all_valid, reason, denied_files)
    """
    denied_files = []
    protected_files = []
    
    for file_path in file_paths:
        if is_denied_file(file_path):
            denied_files.append(file_path)
        elif is_self_upgrade_protected(file_path):
            protected_files.append(file_path)
    
    if denied_files:
        return False, f"Denied files: {', '.join(denied_files)}", denied_files
    
    if protected_files and not allow_self_upgrade_edits():
        return (
            False,
            f"Self-upgrade protected files (require MILTON_SELF_UPGRADE_ALLOW_POLICY_EDITS=1): {', '.join(protected_files)}",
            protected_files,
        )
    
    return True, "All files allowed", []


def get_max_files_changed() -> int:
    """Get max files changed limit."""
    return int(os.getenv("MILTON_SELF_UPGRADE_MAX_FILES", str(DEFAULT_MAX_FILES_CHANGED)))


def get_max_loc_changed() -> int:
    """Get max LOC changed limit."""
    return int(os.getenv("MILTON_SELF_UPGRADE_MAX_LOC", str(DEFAULT_MAX_LOC_CHANGED)))


def get_command_timeout() -> int:
    """Get command timeout in seconds."""
    return int(os.getenv("MILTON_SELF_UPGRADE_TIMEOUT", str(DEFAULT_COMMAND_TIMEOUT)))


def skip_tests() -> bool:
    """Check if tests should be skipped (dangerous override)."""
    return os.getenv("MILTON_SELF_UPGRADE_SKIP_TESTS", "0") == "1"
