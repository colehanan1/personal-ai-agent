"""Codex CLI subprocess wrapper and capability detection"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CodexRunResult:
    """Result of running Codex CLI"""

    exit_code: int
    stdout: str
    stderr: str
    duration: float
    success: bool

    def get_summary(self, max_length: int = 4000) -> str:
        """Get a summary of the run suitable for ntfy"""
        lines = [
            "=== CODEX EXECUTION ===",
            f"Exit Code: {self.exit_code}",
            f"Status: {'SUCCESS' if self.success else 'FAILED'}",
            f"Duration: {self.duration:.1f}s",
            "",
        ]

        if self.stdout:
            lines.append("STDOUT:")
            lines.append(self.stdout[: max_length // 2])
            if len(self.stdout) > max_length // 2:
                lines.append(
                    f"\n... (truncated {len(self.stdout) - max_length // 2} chars)"
                )

        if self.stderr:
            lines.append("")
            lines.append("STDERR:")
            lines.append(self.stderr[: max_length // 2])
            if len(self.stderr) > max_length // 2:
                lines.append(
                    f"\n... (truncated {len(self.stderr) - max_length // 2} chars)"
                )

        summary = "\n".join(lines)

        if len(summary) > max_length:
            summary = summary[:max_length] + "\n\n... (output truncated)"

        return summary


class CodexRunner:
    """Manages Codex CLI subprocess execution"""

    def __init__(
        self,
        codex_bin: str = "codex",
        target_repo: Optional[Path] = None,
        model: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
        state_dir: Optional[Path] = None,
    ):
        self.codex_bin = codex_bin
        self.target_repo = target_repo
        self.model = model
        self.extra_args = extra_args or []
        self.state_dir = state_dir
        self._capabilities = None
        self._prompt_flag: Optional[str] = None
        self._path_flag: Optional[str] = None
        self._yes_flag: Optional[str] = None
        self._model_flag: Optional[str] = None
        self._non_interactive_flag: Optional[str] = None
        self._sandbox_flag: Optional[str] = None
        self._bypass_sandbox_flag: Optional[str] = None
        self._exec_supported: bool = False
        self._read_only_flag: Optional[str] = None
        self._auto_approve_flag: Optional[str] = None
        self._skip_permissions_flag: Optional[str] = None
        self.last_plan_result: Optional[CodexRunResult] = None
        self.last_execute_result: Optional[CodexRunResult] = None
        self.last_plan_output_file: Optional[Path] = None
        self.last_execute_output_file: Optional[Path] = None

    def check_available(self) -> bool:
        """Check if Codex CLI is available"""
        return shutil.which(self.codex_bin) is not None

    def detect_capabilities(self) -> dict[str, bool]:
        """
        Detect Codex CLI capabilities by checking help output.

        Returns:
            Dict of capability flags
        """
        if self._capabilities is not None:
            return self._capabilities

        logger.info("Detecting Codex CLI capabilities")

        try:
            result = subprocess.run(
                [self.codex_bin, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            help_text = result.stdout + result.stderr
            help_lower = help_text.lower()

            self._prompt_flag = None
            if "--prompt" in help_lower:
                self._prompt_flag = "--prompt"
            elif "--message" in help_lower:
                self._prompt_flag = "--message"

            self._path_flag = None
            if "--path" in help_lower:
                self._path_flag = "--path"
            elif "--cwd" in help_lower:
                self._path_flag = "--cwd"
            elif "--repo" in help_lower:
                self._path_flag = "--repo"
            elif "--cd" in help_lower:
                self._path_flag = "--cd"

            self._yes_flag = None
            if "-y" in help_lower:
                self._yes_flag = "-y"
            elif "--yes" in help_lower:
                self._yes_flag = "--yes"

            self._model_flag = None
            if "--model" in help_lower:
                self._model_flag = "--model"
            elif "-m" in help_lower:
                self._model_flag = "-m"

            self._non_interactive_flag = None
            if "--non-interactive" in help_lower:
                self._non_interactive_flag = "--non-interactive"
            elif "--noninteractive" in help_lower:
                self._non_interactive_flag = "--noninteractive"

            self._read_only_flag = None
            if "--read-only" in help_lower:
                self._read_only_flag = "--read-only"
            elif "--readonly" in help_lower:
                self._read_only_flag = "--readonly"

            self._auto_approve_flag = None
            if "--auto-approve" in help_lower:
                self._auto_approve_flag = "--auto-approve"
            elif "--auto-apply" in help_lower:
                self._auto_approve_flag = "--auto-apply"

            self._skip_permissions_flag = None
            if "--dangerously-skip-permissions" in help_lower:
                self._skip_permissions_flag = "--dangerously-skip-permissions"
            elif "--skip-permissions" in help_lower:
                self._skip_permissions_flag = "--skip-permissions"

            self._sandbox_flag = None
            if "--sandbox" in help_lower:
                self._sandbox_flag = "--sandbox"

            self._bypass_sandbox_flag = None
            if "--dangerously-bypass-approvals-and-sandbox" in help_lower:
                self._bypass_sandbox_flag = "--dangerously-bypass-approvals-and-sandbox"

            self._exec_supported = bool(re.search(r"^\s*exec\s", help_text, re.MULTILINE))

            capabilities = {
                "supports_prompt_flag": self._prompt_flag is not None,
                "supports_path_flag": self._path_flag is not None,
                "supports_model_flag": self._model_flag is not None,
                "supports_plan_flag": "--plan" in help_lower,
                "supports_read_only_flag": self._read_only_flag is not None,
                "supports_dry_run_flag": "--dry-run" in help_lower,
                "supports_print_flag": "--print" in help_lower,
                "supports_yes_flag": self._yes_flag is not None,
                "supports_auto_approve": self._auto_approve_flag is not None,
                "supports_skip_permissions": self._skip_permissions_flag is not None,
                "supports_non_interactive": self._non_interactive_flag is not None,
                "supports_sandbox_flag": self._sandbox_flag is not None,
                "supports_bypass_sandbox": self._bypass_sandbox_flag is not None,
                "supports_exec_command": self._exec_supported,
            }

            logger.info(f"Detected capabilities: {capabilities}")
            self._capabilities = capabilities
            return capabilities

        except Exception as e:
            logger.warning(f"Failed to detect Codex CLI capabilities: {e}")
            self._prompt_flag = None
            self._path_flag = None
            self._yes_flag = None
            self._model_flag = None
            self._non_interactive_flag = None
            self._sandbox_flag = None
            self._bypass_sandbox_flag = None
            self._exec_supported = False
            self._read_only_flag = None
            self._auto_approve_flag = None
            self._skip_permissions_flag = None
            return {
                "supports_prompt_flag": False,
                "supports_path_flag": False,
                "supports_model_flag": False,
                "supports_plan_flag": False,
                "supports_read_only_flag": False,
                "supports_dry_run_flag": False,
                "supports_print_flag": False,
                "supports_yes_flag": False,
                "supports_auto_approve": False,
                "supports_skip_permissions": False,
                "supports_non_interactive": False,
                "supports_sandbox_flag": False,
                "supports_bypass_sandbox": False,
                "supports_exec_command": False,
            }

    def run_plan(
        self,
        prompt: str,
        timeout: int = 600,
        dry_run: bool = False,
    ) -> str:
        """
        Run Codex in plan/read-only mode.

        Returns:
            Plan text
        """
        plan_prompt = self._wrap_plan_prompt(prompt)
        result = self._run_codex(
            prompt=plan_prompt,
            timeout=timeout,
            dry_run=dry_run,
            mode="plan",
        )
        self.last_plan_result = result
        self.last_plan_output_file = self._save_output(result, label="plan")
        return result.stdout

    def run_execute(
        self,
        prompt: str,
        timeout: int = 600,
        dry_run: bool = False,
    ) -> CodexRunResult:
        """
        Run Codex in execution mode to apply changes and run tests.
        """
        result = self._run_codex(
            prompt=prompt,
            timeout=timeout,
            dry_run=dry_run,
            mode="execute",
        )
        self.last_execute_result = result
        self.last_execute_output_file = self._save_output(result, label="execute")
        return result

    def run(
        self,
        prompt: str,
        timeout: int = 600,
        dry_run: bool = False,
    ) -> CodexRunResult:
        """
        Run Codex with plan-first execution.
        """
        self.run_plan(prompt=prompt, timeout=timeout, dry_run=dry_run)

        if not self.last_plan_result or not self.last_plan_result.success:
            logger.error("Codex plan step failed; skipping execution")
            return self.last_plan_result or CodexRunResult(
                exit_code=1,
                stdout="",
                stderr="Codex plan step failed",
                duration=0.0,
                success=False,
            )

        return self.run_execute(prompt=prompt, timeout=timeout, dry_run=dry_run)

    def _wrap_plan_prompt(self, prompt: str) -> str:
        """Add an explicit plan-only instruction wrapper."""
        return (
            "PLAN-ONLY MODE:\n"
            "- Produce a clear, step-by-step plan.\n"
            "- Do NOT modify files or run tests.\n"
            "- Wait for execution step to apply changes.\n\n"
            f"{prompt}"
        )

    def _build_command(self, prompt: str, capabilities: dict[str, bool], mode: str) -> tuple[list[str], Optional[str]]:
        cmd = [self.codex_bin]
        stdin_input = None

        if capabilities.get("supports_exec_command"):
            cmd.append("exec")

        if capabilities.get("supports_path_flag") and self.target_repo and self._path_flag:
            cmd.extend([self._path_flag, str(self.target_repo)])

        if capabilities.get("supports_model_flag") and self._model_flag:
            model = self._normalized_model()
            if model:
                cmd.extend([self._model_flag, model])

        if self.extra_args:
            cmd.extend(self.extra_args)

        if mode == "plan":
            if capabilities.get("supports_plan_flag"):
                cmd.append("--plan")
            elif capabilities.get("supports_read_only_flag") and self._read_only_flag:
                cmd.append(self._read_only_flag)
            elif capabilities.get("supports_dry_run_flag"):
                cmd.append("--dry-run")
            elif capabilities.get("supports_sandbox_flag") and self._sandbox_flag:
                cmd.extend([self._sandbox_flag, "read-only"])

            if capabilities.get("supports_print_flag"):
                cmd.append("--print")
        else:
            if capabilities.get("supports_yes_flag") and self._yes_flag:
                cmd.append(self._yes_flag)
            elif capabilities.get("supports_auto_approve") and self._auto_approve_flag:
                cmd.append(self._auto_approve_flag)

            if capabilities.get("supports_skip_permissions") and self._skip_permissions_flag:
                cmd.append(self._skip_permissions_flag)

            if capabilities.get("supports_non_interactive") and self._non_interactive_flag:
                cmd.append(self._non_interactive_flag)
            elif capabilities.get("supports_bypass_sandbox") and self._bypass_sandbox_flag:
                cmd.append(self._bypass_sandbox_flag)
            elif capabilities.get("supports_sandbox_flag") and self._sandbox_flag:
                cmd.extend([self._sandbox_flag, "danger-full-access"])

        if capabilities.get("supports_prompt_flag") and self._prompt_flag:
            cmd.extend([self._prompt_flag, prompt])
        else:
            stdin_input = prompt

        return cmd, stdin_input

    def _run_codex(
        self,
        prompt: str,
        timeout: int,
        dry_run: bool,
        mode: str,
    ) -> CodexRunResult:
        import time

        start_time = time.time()

        if dry_run:
            logger.info(f"DRY RUN: Would execute Codex ({mode})")
            return CodexRunResult(
                exit_code=0,
                stdout=f"[DRY RUN] Codex would execute in {mode} mode",
                stderr="",
                duration=0.1,
                success=True,
            )

        if not self.check_available():
            logger.error(f"Codex CLI binary not found: {self.codex_bin}")
            return CodexRunResult(
                exit_code=127,
                stdout="",
                stderr=f"Codex CLI binary not found: {self.codex_bin}",
                duration=0.0,
                success=False,
            )

        capabilities = self.detect_capabilities()
        cmd, stdin_input = self._build_command(prompt, capabilities, mode)

        logger.info(f"Executing Codex CLI ({mode})")
        logger.debug(f"Command: {self._redact_prompt(cmd)}")
        logger.debug(f"Working directory: {self.target_repo}")

        try:
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
                f"Codex CLI finished ({mode}): exit_code={result.returncode}, "
                f"duration={duration:.1f}s, success={success}"
            )

            return CodexRunResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
                success=success,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"Codex CLI timed out after {timeout}s ({mode})")
            return CodexRunResult(
                exit_code=124,
                stdout="",
                stderr=f"Codex CLI execution timed out after {timeout}s",
                duration=duration,
                success=False,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Codex CLI execution failed ({mode}): {e}")
            return CodexRunResult(
                exit_code=1,
                stdout="",
                stderr=f"Codex CLI execution error: {e}",
                duration=duration,
                success=False,
            )

    def _save_output(self, result: CodexRunResult, label: str) -> Optional[Path]:
        """
        Save full Codex CLI output to a file.
        """
        if not self.state_dir:
            logger.warning("State directory not configured; skipping Codex output save")
            return None

        import datetime

        output_dir = self.state_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"codex_{label}_output_{timestamp}.txt"
        filepath = output_dir / filename

        content = [
            "=== CODEX CLI FULL OUTPUT ===",
            f"Mode: {label}",
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
        logger.info(f"Saved Codex output to {filepath}")
        return filepath

    def _normalized_model(self) -> Optional[str]:
        if not self.model:
            return None
        model = self.model.strip()
        if not model:
            return None
        if model.lower() in {"default", "auto", "none"}:
            return None
        return model

    @staticmethod
    def _redact_prompt(cmd: list[str]) -> list[str]:
        redacted = []
        skip_next = False
        for arg in cmd:
            if skip_next:
                redacted.append("[REDACTED]")
                skip_next = False
                continue
            if arg in {"-p", "--prompt", "--message"}:
                redacted.append(arg)
                skip_next = True
                continue
            redacted.append(arg)
        return redacted
