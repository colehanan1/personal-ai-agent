"""Tests for output publisher helpers."""

from pathlib import Path
from unittest.mock import MagicMock

from milton_orchestrator.config import Config
from milton_orchestrator import output_publisher
from milton_orchestrator.output_publisher import (
    build_output_url,
    build_share_url,
    publish_response,
    save_output_text,
)


def make_config(tmp_path: Path, **overrides) -> Config:
    defaults = dict(
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
        ntfy_max_inline_chars=50,
        always_file_attachments=False,
        output_filename_template="milton_{request_id}.txt",
        request_timeout=300,
        ntfy_reconnect_backoff_max=120,
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_short_text_publishes_inline(tmp_path: Path):
    config = make_config(tmp_path, ntfy_max_inline_chars=100)
    ntfy_client = MagicMock()

    publish_response(
        ntfy_client,
        topic="topic",
        title="Short",
        full_text="short output",
        request_id="req-1",
        config=config,
    )

    ntfy_client.publish.assert_called_once()
    files = list(config.output_dir.iterdir())
    assert len(files) == 1


def test_long_text_publishes_click_and_saves_file(tmp_path: Path):
    config = make_config(
        tmp_path,
        ntfy_max_inline_chars=10,
        output_base_url="https://node.tailnet.ts.net",
    )
    ntfy_client = MagicMock()
    full_text = "x" * 50

    publish_response(
        ntfy_client,
        topic="topic",
        title="Long",
        full_text=full_text,
        request_id="req-2",
        config=config,
    )

    files = list(config.output_dir.iterdir())
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == full_text

    _, kwargs = ntfy_client.publish.call_args
    assert "click_url" in kwargs
    assert kwargs["click_url"] == build_output_url(config.output_base_url, files[0])


def test_missing_base_url_falls_back_inline(tmp_path: Path):
    config = make_config(tmp_path, ntfy_max_inline_chars=20, output_base_url=None)
    ntfy_client = MagicMock()
    full_text = "x" * 100

    publish_response(
        ntfy_client,
        topic="topic",
        title="Fallback",
        full_text=full_text,
        request_id="req-3",
        config=config,
    )

    files = list(config.output_dir.iterdir())
    assert len(files) == 1

    _, kwargs = ntfy_client.publish.call_args
    assert "click_url" not in kwargs or kwargs["click_url"] is None
    body = ntfy_client.publish.call_args.args[1]
    assert body.startswith("[req-3]")


def test_long_text_uses_share_url_when_configured(tmp_path: Path):
    config = make_config(
        tmp_path,
        ntfy_max_inline_chars=10,
        output_base_url=None,
        output_share_url="smb://milton.local/milton_outputs",
    )
    ntfy_client = MagicMock()
    full_text = "x" * 50

    publish_response(
        ntfy_client,
        topic="topic",
        title="Share",
        full_text=full_text,
        request_id="req-4",
        config=config,
    )

    files = list(config.output_dir.iterdir())
    assert len(files) == 1

    _, kwargs = ntfy_client.publish.call_args
    assert "click_url" not in kwargs or kwargs["click_url"] is None
    body = ntfy_client.publish.call_args.args[1]
    expected_url = build_share_url(
        config.output_share_url,
        None,
        None,
        files[0],
    )
    assert expected_url
    assert expected_url in body
    assert files[0].name in body


def test_save_output_text_sanitizes_request_id(tmp_path: Path):
    output_dir = tmp_path / "outputs"
    output_path = save_output_text(
        text="payload",
        request_id="../../etc/passwd",
        output_dir=output_dir,
        filename_template="milton_{request_id}.txt",
    )

    assert output_path.parent == output_dir
    assert ".." not in output_path.name
    assert "/" not in output_path.name


def test_output_link_uses_filename_template(tmp_path: Path):
    config = make_config(
        tmp_path,
        ntfy_max_inline_chars=10,
        output_base_url="https://node.tailnet.ts.net",
        output_filename_template="custom_{request_id}.log",
    )
    ntfy_client = MagicMock()
    full_text = "y" * 80

    publish_response(
        ntfy_client,
        topic="topic",
        title="Template",
        full_text=full_text,
        request_id="req-template",
        config=config,
    )

    files = list(config.output_dir.iterdir())
    assert len(files) == 1
    assert files[0].name == "custom_req-template.log"

    _, kwargs = ntfy_client.publish.call_args
    assert kwargs["click_url"] == build_output_url(config.output_base_url, files[0])


def test_result_memory_capture_once(tmp_path: Path, monkeypatch):
    config = make_config(
        tmp_path,
        ntfy_max_inline_chars=10,
        output_base_url="https://node.tailnet.ts.net",
    )
    ntfy_client = MagicMock()
    calls = []

    def fake_add_memory(item, repo_root=None):
        calls.append((item, repo_root))
        return item.id

    monkeypatch.setattr(output_publisher, "add_memory", fake_add_memory)

    full_text = "x" * 80
    publish_response(
        ntfy_client,
        topic="topic",
        title="Memory",
        full_text=full_text,
        request_id="req-mem",
        config=config,
        mode_tag="claude",
    )

    assert len(calls) == 1
    item, repo_root = calls[0]
    assert item.type == "result"
    assert item.request_id == "req-mem"
    assert "claude" in item.tags
    assert repo_root == config.target_repo
    assert item.evidence
    assert any("req-mem" in entry or entry.endswith(".txt") for entry in item.evidence)


def test_long_output_records_click_evidence(tmp_path: Path, monkeypatch):
    config = make_config(
        tmp_path,
        ntfy_max_inline_chars=5,
        output_base_url="https://node.tailnet.ts.net",
    )
    ntfy_client = MagicMock()
    captured = []

    def fake_add_memory(item, repo_root=None):
        captured.append(item)
        return item.id

    monkeypatch.setattr(output_publisher, "add_memory", fake_add_memory)

    publish_response(
        ntfy_client,
        topic="topic",
        title="Long",
        full_text="z" * 100,
        request_id="req-long",
        config=config,
        mode_tag="codex",
    )

    _, kwargs = ntfy_client.publish.call_args
    assert kwargs["click_url"].startswith(config.output_base_url)

    assert len(captured) == 1
    item = captured[0]
    assert item.request_id == "req-long"
    assert any(entry.startswith(config.output_base_url) for entry in item.evidence)
    assert any(entry.endswith(".txt") for entry in item.evidence)
