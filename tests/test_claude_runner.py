"""Tests for Claude runner"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from milton_orchestrator.claude_runner import (
    ClaudeRunner,
    ClaudeRunResult,
)


class TestClaudeRunResult:
    """Tests for ClaudeRunResult"""

    def test_get_summary_basic(self):
        result = ClaudeRunResult(
            exit_code=0,
            stdout="Output text",
            stderr="",
            duration=1.5,
            success=True,
        )

        summary = result.get_summary()
        assert "Exit Code: 0" in summary
        assert "SUCCESS" in summary
        assert "Duration: 1.5s" in summary
        assert "Output text" in summary

    def test_get_summary_with_failure(self):
        result = ClaudeRunResult(
            exit_code=1,
            stdout="",
            stderr="Error occurred",
            duration=0.5,
            success=False,
        )

        summary = result.get_summary()
        assert "Exit Code: 1" in summary
        assert "FAILED" in summary
        assert "Error occurred" in summary

    def test_get_summary_truncates_long_output(self):
        long_text = "x" * 10000
        result = ClaudeRunResult(
            exit_code=0,
            stdout=long_text,
            stderr="",
            duration=1.0,
            success=True,
        )

        summary = result.get_summary(max_length=1000)
        assert len(summary) <= 1000 + 100  # Allow some margin for structure
        assert "truncated" in summary


class TestClaudeRunner:
    """Tests for ClaudeRunner"""

    @pytest.fixture
    def runner(self, tmp_path):
        return ClaudeRunner(
            claude_bin="claude",
            target_repo=tmp_path,
        )

    @patch("milton_orchestrator.claude_runner.shutil.which")
    def test_check_available_found(self, mock_which, runner):
        mock_which.return_value = "/usr/bin/claude"
        assert runner.check_available() is True
        mock_which.assert_called_once_with("claude")

    @patch("milton_orchestrator.claude_runner.shutil.which")
    def test_check_available_not_found(self, mock_which, runner):
        mock_which.return_value = None
        assert runner.check_available() is False

    @patch("milton_orchestrator.claude_runner.subprocess.run")
    def test_detect_capabilities(self, mock_run, runner):
        mock_run.return_value = Mock(
            stdout="Usage: claude [OPTIONS]\n  -p, --prompt\n  --print\n  -y, --yes",
            stderr="",
        )

        caps = runner.detect_capabilities()

        assert caps["supports_prompt_flag"] is True
        assert caps["supports_print_mode"] is True
        assert caps["supports_yes_flag"] is True

    @patch("milton_orchestrator.claude_runner.subprocess.run")
    def test_detect_capabilities_minimal(self, mock_run, runner):
        mock_run.return_value = Mock(
            stdout="Usage: claude [OPTIONS]",
            stderr="",
        )

        caps = runner.detect_capabilities()

        assert caps["supports_prompt_flag"] is False
        assert caps["supports_print_mode"] is False

    def test_run_dry_run(self, runner):
        result = runner.run("test prompt", dry_run=True)

        assert result.exit_code == 0
        assert result.success is True
        assert "DRY RUN" in result.stdout

    @patch("milton_orchestrator.claude_runner.shutil.which")
    def test_run_binary_not_found(self, mock_which, runner):
        mock_which.return_value = None

        result = runner.run("test prompt")

        assert result.exit_code == 127
        assert result.success is False
        assert "not found" in result.stderr

    @patch("milton_orchestrator.claude_runner.subprocess.run")
    @patch.object(ClaudeRunner, "check_available")
    @patch.object(ClaudeRunner, "detect_capabilities")
    def test_run_success(self, mock_caps, mock_check, mock_run, runner):
        mock_check.return_value = True
        mock_caps.return_value = {
            "supports_prompt_flag": True,
            "supports_print_mode": False,
            "supports_yes_flag": True,
            "supports_auto_approve": False,
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Claude output",
            stderr="",
        )

        result = runner.run("test prompt", timeout=60)

        assert result.exit_code == 0
        assert result.success is True
        assert result.stdout == "Claude output"
        mock_run.assert_called_once()

    @patch("milton_orchestrator.claude_runner.subprocess.run")
    @patch.object(ClaudeRunner, "check_available")
    @patch.object(ClaudeRunner, "detect_capabilities")
    def test_run_timeout(self, mock_caps, mock_check, mock_run, runner):
        import subprocess

        mock_check.return_value = True
        mock_caps.return_value = {
            "supports_prompt_flag": True,
            "supports_print_mode": False,
            "supports_yes_flag": False,
            "supports_auto_approve": False,
        }
        mock_run.side_effect = subprocess.TimeoutExpired("claude", 60)

        result = runner.run("test prompt", timeout=60)

        assert result.exit_code == 124
        assert result.success is False
        assert "timed out" in result.stderr

    @patch("milton_orchestrator.claude_runner.subprocess.run")
    @patch.object(ClaudeRunner, "check_available")
    @patch.object(ClaudeRunner, "detect_capabilities")
    def test_run_uses_correct_flags(self, mock_caps, mock_check, mock_run, runner):
        mock_check.return_value = True
        mock_caps.return_value = {
            "supports_prompt_flag": True,
            "supports_print_mode": True,
            "supports_yes_flag": True,
            "supports_auto_approve": False,
        }
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        runner.run("test prompt")

        # Check command construction
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "-y" in cmd
        assert "--print" in cmd

    def test_save_output(self, runner, tmp_path):
        result = ClaudeRunResult(
            exit_code=0,
            stdout="Output",
            stderr="Errors",
            duration=1.0,
            success=True,
        )

        output_file = runner.save_output(result, tmp_path)

        assert output_file.exists()
        content = output_file.read_text()
        assert "Exit Code: 0" in content
        assert "Output" in content
        assert "Errors" in content
