"""Claude Code subprocess wrapper and capability detection"""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClaudeRunResult:
    """Result of running Claude Code"""

    exit_code: int
    stdout: str
    stderr: str
    duration: float
    success: bool

    def get_summary(self, max_length: int = 4000) -> str:
        """Get a summary of the run suitable for ntfy"""
        lines = [
            "=== CLAUDE CODE EXECUTION ===",
            f"Exit Code: {self.exit_code}",
            f"Status: {'SUCCESS' if self.success else 'FAILED'}",
            f"Duration: {self.duration:.1f}s",
            "",
        ]

        if self.stdout:
            lines.append("STDOUT:")
            lines.append(self.stdout[:max_length // 2])
            if len(self.stdout) > max_length // 2:
                lines.append(f"\n... (truncated {len(self.stdout) - max_length // 2} chars)")

        if self.stderr:
            lines.append("")
            lines.append("STDERR:")
            lines.append(self.stderr[:max_length // 2])
            if len(self.stderr) > max_length // 2:
                lines.append(f"\n... (truncated {len(self.stderr) - max_length // 2} chars)")

        summary = "\n".join(lines)

        if len(summary) > max_length:
            summary = summary[:max_length] + "\n\n... (output truncated)"

        return summary


class ClaudeRunner:
    """Manages Claude Code subprocess execution"""

    def __init__(self, claude_bin: str = "claude", target_repo: Path = None):
        self.claude_bin = claude_bin
        self.target_repo = target_repo
        self._capabilities = None

    def check_available(self) -> bool:
        """Check if Claude Code is available"""
        return shutil.which(self.claude_bin) is not None

    def detect_capabilities(self) -> dict[str, bool]:
        """
        Detect Claude Code capabilities by checking help output.

        Returns:
            Dict of capability flags
        """
        if self._capabilities is not None:
            return self._capabilities

        logger.info("Detecting Claude Code capabilities")

        try:
            result = subprocess.run(
                [self.claude_bin, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            help_text = result.stdout + result.stderr

            # Check for various flags
            capabilities = {
                "supports_prompt_flag": "-p" in help_text or "--prompt" in help_text,
                "supports_print_mode": "--print" in help_text,
                "supports_yes_flag": "-y" in help_text or "--yes" in help_text,
                "supports_auto_approve": "--auto-approve" in help_text,
            }

            logger.info(f"Detected capabilities: {capabilities}")
            self._capabilities = capabilities
            return capabilities

        except Exception as e:
            logger.warning(f"Failed to detect Claude Code capabilities: {e}")
            # Assume basic capabilities
            return {
                "supports_prompt_flag": True,
                "supports_print_mode": False,
                "supports_yes_flag": False,
                "supports_auto_approve": False,
            }

    def run(
        self,
        prompt: str,
        timeout: int = 600,
        dry_run: bool = False,
    ) -> ClaudeRunResult:
        """
        Run Claude Code with the given prompt.

        Args:
            prompt: The prompt to send to Claude Code
            timeout: Maximum execution time in seconds
            dry_run: If True, don't actually run Claude, just simulate

        Returns:
            ClaudeRunResult with execution details
        """
        import time

        start_time = time.time()

        if dry_run:
            logger.info("DRY RUN: Would execute Claude Code")
            logger.info(f"Prompt preview: {prompt[:200]}...")
            return ClaudeRunResult(
                exit_code=0,
                stdout="[DRY RUN] Claude Code would execute here",
                stderr="",
                duration=0.1,
                success=True,
            )

        if not self.check_available():
            logger.error(f"Claude Code binary not found: {self.claude_bin}")
            return ClaudeRunResult(
                exit_code=127,
                stdout="",
                stderr=f"Claude Code binary not found: {self.claude_bin}",
                duration=0.0,
                success=False,
            )

        # Build command based on capabilities
        capabilities = self.detect_capabilities()
        cmd = [self.claude_bin]

        # Add prompt
        if capabilities["supports_prompt_flag"]:
            cmd.extend(["-p", prompt])
        else:
            # Write prompt to temp file and use stdin
            logger.warning("Claude doesn't support -p flag, using alternative method")

        # Add auto-approve flags to minimize interaction
        if capabilities["supports_yes_flag"]:
            cmd.append("-y")
        elif capabilities["supports_auto_approve"]:
            cmd.append("--auto-approve")

        # Add print mode if available
        if capabilities["supports_print_mode"]:
            cmd.append("--print")

        logger.info(f"Executing Claude Code: {' '.join(cmd[:3])}...")
        logger.debug(f"Full command: {cmd}")
        logger.debug(f"Working directory: {self.target_repo}")

        try:
            # If we don't support -p flag, use stdin
            stdin_input = None
            if not capabilities["supports_prompt_flag"]:
                stdin_input = prompt

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.target_repo) if self.target_repo else None,
                input=stdin_input,
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            logger.info(
                f"Claude Code finished: exit_code={result.returncode}, "
                f"duration={duration:.1f}s, success={success}"
            )

            return ClaudeRunResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
                success=success,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"Claude Code timed out after {timeout}s")
            return ClaudeRunResult(
                exit_code=124,
                stdout="",
                stderr=f"Claude Code execution timed out after {timeout}s",
                duration=duration,
                success=False,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Claude Code execution failed: {e}")
            return ClaudeRunResult(
                exit_code=1,
                stdout="",
                stderr=f"Claude Code execution error: {e}",
                duration=duration,
                success=False,
            )

    def save_output(self, result: ClaudeRunResult, output_dir: Path) -> Path:
        """
        Save full Claude Code output to a file.

        Args:
            result: The ClaudeRunResult to save
            output_dir: Directory to save the output

        Returns:
            Path to the saved output file
        """
        import datetime

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"claude_output_{timestamp}.txt"
        filepath = output_dir / filename

        content = [
            "=== CLAUDE CODE FULL OUTPUT ===",
            f"Exit Code: {result.exit_code}",
            f"Duration: {result.duration:.2f}s",
            f"Success: {result.success}",
            "",
            "=== STDOUT ===",
            result.stdout,
            "",
            "=== STDERR ===",
            result.stderr,
        ]

        filepath.write_text("\n".join(content))
        logger.info(f"Saved full output to {filepath}")

        return filepath
