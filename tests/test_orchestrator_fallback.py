"""Tests for orchestrator fallback logic"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from milton_orchestrator.config import Config
from milton_orchestrator.orchestrator import Orchestrator
from milton_orchestrator.claude_runner import ClaudeRunResult
from milton_orchestrator.codex_runner import CodexRunResult


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        ntfy_base_url="https://ntfy.sh",
        ntfy_max_chars=160,
        ask_topic="ask-topic",
        answer_topic="answer-topic",
        claude_topic="",
        codex_topic="",
        perplexity_api_key="test-key",
        perplexity_model="sonar-pro",
        perplexity_timeout=30,
        perplexity_max_retries=1,
        claude_bin="claude",
        claude_timeout=0,
        target_repo=tmp_path,
        codex_bin="codex",
        codex_model="default",
        codex_timeout=300,
        codex_extra_args=[],
        enable_codex_fallback=True,
        codex_fallback_on_any_failure=False,
        claude_fallback_on_limit=True,
        enable_prefix_routing=True,
        enable_claude_pipeline=True,
        enable_codex_pipeline=True,
        enable_research_mode=True,
        enable_reminders=False,
        perplexity_in_claude_mode=False,
        perplexity_in_codex_mode=False,
        perplexity_in_research_mode=False,
        log_dir=tmp_path / "logs",
        state_dir=tmp_path / "state",
        max_output_size=4000,
        output_dir=tmp_path / "outputs",
        output_base_url=None,
        output_share_url=None,
        output_share_host=None,
        output_share_name=None,
        ntfy_max_inline_chars=3000,
        always_file_attachments=False,
        output_filename_template="milton_{request_id}.txt",
        request_timeout=300,
        ntfy_reconnect_backoff_max=120,
    )


def setup_orchestrator(config: Config) -> Orchestrator:
    orchestrator = Orchestrator(config, dry_run=False)
    orchestrator.publish_status = MagicMock()
    orchestrator.ntfy_client = MagicMock()
    orchestrator.perplexity_client = MagicMock()
    orchestrator.perplexity_client.research_and_optimize.return_value = "notes"
    return orchestrator


def test_fallback_on_usage_limit(config, tmp_path):
    orchestrator = setup_orchestrator(config)

    orchestrator.claude_runner = MagicMock()
    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=1,
        stdout="",
        stderr="Usage limit reached",
        duration=1.0,
        success=False,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    orchestrator.codex_runner = MagicMock()
    orchestrator.codex_runner.check_available.return_value = True
    orchestrator.codex_runner.run.return_value = CodexRunResult(
        exit_code=0,
        stdout="Done",
        stderr="",
        duration=2.0,
        success=True,
    )
    orchestrator.codex_runner.last_plan_output_file = tmp_path / "plan.txt"
    orchestrator.codex_runner.last_execute_output_file = tmp_path / "exec.txt"

    orchestrator.process_claude_code_request("req-usage", "Do the thing")

    orchestrator.claude_runner.run.assert_called_once()
    orchestrator.codex_runner.run.assert_called_once()


def test_fallback_on_missing_claude(config, tmp_path):
    orchestrator = setup_orchestrator(config)

    orchestrator.claude_runner = MagicMock()
    orchestrator.claude_runner.check_available.return_value = False

    orchestrator.codex_runner = MagicMock()
    orchestrator.codex_runner.check_available.return_value = True
    orchestrator.codex_runner.run.return_value = CodexRunResult(
        exit_code=0,
        stdout="Done",
        stderr="",
        duration=2.0,
        success=True,
    )
    orchestrator.codex_runner.last_plan_output_file = tmp_path / "plan.txt"
    orchestrator.codex_runner.last_execute_output_file = tmp_path / "exec.txt"

    orchestrator.process_claude_code_request("req-missing", "Do the other thing")

    orchestrator.claude_runner.run.assert_not_called()
    orchestrator.codex_runner.run.assert_called_once()


def test_no_fallback_on_non_limit_error(config, tmp_path):
    orchestrator = setup_orchestrator(config)

    orchestrator.claude_runner = MagicMock()
    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=1,
        stdout="Tests failed",
        stderr="pytest failures",
        duration=1.0,
        success=False,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    orchestrator.codex_runner = MagicMock()
    orchestrator.codex_runner.check_available.return_value = True

    orchestrator.process_claude_code_request("req-fail", "Fix the tests")

    orchestrator.codex_runner.run.assert_not_called()
