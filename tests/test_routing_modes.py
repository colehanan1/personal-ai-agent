"""Tests for routing modes in the orchestrator."""

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
        ask_topic="ask-topic",
        answer_topic="answer-topic",
        claude_topic="claude-topic",
        codex_topic="codex-topic",
        perplexity_api_key="test-key",
        perplexity_model="sonar-pro",
        perplexity_timeout=30,
        perplexity_max_retries=1,
        claude_bin="claude",
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
        perplexity_in_research_mode=True,
        log_dir=tmp_path / "logs",
        state_dir=tmp_path / "state",
        max_output_size=4000,
        request_timeout=300,
        ntfy_reconnect_backoff_max=120,
    )


def make_orchestrator(config: Config) -> Orchestrator:
    orchestrator = Orchestrator(config, dry_run=False)
    orchestrator.publish_status = MagicMock()
    orchestrator.perplexity_client = MagicMock()
    orchestrator.perplexity_client.research_and_optimize.return_value = "notes"
    return orchestrator


def test_chat_mode_no_prefix(config):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.process_incoming_message("msg-1", config.ask_topic, "hello there")

    orchestrator.perplexity_client.research_and_optimize.assert_not_called()
    orchestrator.claude_runner.run.assert_not_called()
    orchestrator.codex_runner.run.assert_not_called()


def test_research_mode(config):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.process_incoming_message("msg-2", config.ask_topic, "RESEARCH: do thing")

    orchestrator.perplexity_client.research_and_optimize.assert_called_once()
    orchestrator.claude_runner.run.assert_not_called()
    orchestrator.codex_runner.run.assert_not_called()


def test_claude_mode_prefix(config, tmp_path):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    orchestrator.process_incoming_message("msg-3", config.ask_topic, "CLAUDE: do it")

    orchestrator.claude_runner.run.assert_called_once()
    orchestrator.codex_runner.run.assert_not_called()


def test_codex_mode_prefix(config):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.codex_runner.check_available.return_value = True
    orchestrator.codex_runner.run.return_value = CodexRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )

    orchestrator.process_incoming_message("msg-4", config.ask_topic, "CODEX: do it")

    orchestrator.codex_runner.run.assert_called_once()
    orchestrator.claude_runner.run.assert_not_called()


def test_claude_topic_without_prefix(config, tmp_path):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    orchestrator.process_incoming_message("msg-5", config.claude_topic, "do it")

    orchestrator.claude_runner.run.assert_called_once()


def test_codex_topic_without_prefix(config):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.codex_runner.check_available.return_value = True
    orchestrator.codex_runner.run.return_value = CodexRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )

    orchestrator.process_incoming_message("msg-6", config.codex_topic, "do it")

    orchestrator.codex_runner.run.assert_called_once()


def test_claude_usage_limit_fallback_only_in_claude_mode(config, tmp_path):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=1,
        stdout="",
        stderr="rate limit exceeded",
        duration=1.0,
        success=False,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"
    orchestrator.codex_runner.check_available.return_value = True
    orchestrator.codex_runner.run.return_value = CodexRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )

    orchestrator.process_incoming_message("msg-7", config.ask_topic, "CLAUDE: do it")

    orchestrator.codex_runner.run.assert_called_once()


def test_json_payload_routes_claude(config, tmp_path):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    message = (
        '{"Date":"Dec 31, 2025 at 3:30 PM",'
        '"Provided Input":"[Cole Phone - Dec 31, 2025]:  claude : do it"}'
    )

    orchestrator.process_incoming_message("msg-json", config.ask_topic, message)

    orchestrator.claude_runner.run.assert_called_once()


def test_json_payload_with_trailing_text_routes_claude(config, tmp_path):
    orchestrator = make_orchestrator(config)
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    orchestrator.claude_runner.check_available.return_value = True
    orchestrator.claude_runner.run.return_value = ClaudeRunResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration=1.0,
        success=True,
    )
    orchestrator.claude_runner.save_output.return_value = tmp_path / "claude.txt"

    message = (
        '{"Date":"Dec 31, 2025 at 3:30 PM",'
        '"Provided Input":"claude : do it"} trailing'
    )

    orchestrator.process_incoming_message("msg-json-trailing", config.ask_topic, message)

    orchestrator.claude_runner.run.assert_called_once()
