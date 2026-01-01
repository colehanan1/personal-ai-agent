from pathlib import Path
from unittest.mock import MagicMock

import pytest

from milton_orchestrator.config import Config
from milton_orchestrator import orchestrator as orchestrator_module
from milton_orchestrator.orchestrator import Orchestrator


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


def test_request_memory_captured_once(config, monkeypatch):
    orchestrator = Orchestrator(config, dry_run=True)
    orchestrator.publish_status = MagicMock()
    orchestrator.ntfy_client = MagicMock()
    orchestrator.perplexity_client = MagicMock()
    orchestrator.claude_runner = MagicMock()
    orchestrator.codex_runner = MagicMock()

    calls = []

    def fake_add_memory(item, repo_root=None):
        calls.append((item, repo_root))
        return item.id

    monkeypatch.setattr(orchestrator_module, "add_memory", fake_add_memory)
    monkeypatch.setenv("MILTON_MEMORY_ENABLED", "true")

    orchestrator.process_incoming_message("msg-1", config.ask_topic, "hello there")

    assert len(calls) == 1
    item, repo_root = calls[0]
    assert item.type == "request"
    assert item.request_id == "req_msg-1"
    assert "chat" in item.tags
    assert "source:ntfy" in item.tags
    assert repo_root == config.target_repo
