"""
Safe command runner for self-upgrade operations.

Executes commands with policy enforcement, timeouts, and logging.
"""
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .policy import validate_command, get_command_timeout

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of command execution."""
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    success: bool


class SafeCommandRunner:
    """Runs commands with policy enforcement and logging."""
    
    def __init__(self, repo_root: Path, log_prefix: str = "SELF_UPGRADE"):
        self.repo_root = Path(repo_root)
        self.log_prefix = log_prefix
    
    def run(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Run command with policy enforcement.
        
        Args:
            command: Shell command to execute
            cwd: Working directory (defaults to repo_root)
            timeout: Command timeout in seconds (defaults to policy setting)
        
        Returns:
            CommandResult with execution details
        
        Raises:
            ValueError: If command violates policy
        """
        # Validate command
        is_valid, reason = validate_command(command)
        if not is_valid:
            logger.error(f"[{self.log_prefix}] COMMAND DENIED: {command} | Reason: {reason}")
            raise ValueError(f"Command denied by policy: {reason}")
        
        # Set defaults
        if cwd is None:
            cwd = self.repo_root
        if timeout is None:
            timeout = get_command_timeout()
        
        # Log command
        logger.info(f"[{self.log_prefix}] COMMAND: {command}")
        logger.info(f"[{self.log_prefix}] CWD: {cwd}")
        
        # Execute
        start_time = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.time() - start_time
            
            # Log result
            logger.info(f"[{self.log_prefix}] EXIT_CODE: {result.returncode}")
            logger.info(f"[{self.log_prefix}] DURATION: {duration:.2f}s")
            
            if result.stdout:
                logger.debug(f"[{self.log_prefix}] STDOUT: {result.stdout[:500]}")
            if result.stderr:
                logger.debug(f"[{self.log_prefix}] STDERR: {result.stderr[:500]}")
            
            return CommandResult(
                command=command,
                cwd=str(cwd),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
                success=(result.returncode == 0),
            )
        
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            logger.error(f"[{self.log_prefix}] TIMEOUT after {duration:.2f}s")
            return CommandResult(
                command=command,
                cwd=str(cwd),
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration=duration,
                success=False,
            )
        
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{self.log_prefix}] ERROR: {e}", exc_info=True)
            return CommandResult(
                command=command,
                cwd=str(cwd),
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
                success=False,
            )
    
    def run_checked(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Run command and raise exception if it fails.
        
        Args:
            command: Shell command to execute
            cwd: Working directory (defaults to repo_root)
            timeout: Command timeout in seconds
        
        Returns:
            CommandResult with execution details
        
        Raises:
            RuntimeError: If command fails (non-zero exit code)
            ValueError: If command violates policy
        """
        result = self.run(command, cwd=cwd, timeout=timeout)
        if not result.success:
            raise RuntimeError(
                f"Command failed (exit {result.exit_code}): {command}\n"
                f"STDERR: {result.stderr}"
            )
        return result
