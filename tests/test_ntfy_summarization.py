"""Tests for ntfy summary helpers."""

from pathlib import Path

import pytest

from milton_orchestrator.ntfy_summarizer import (
    EMPTY_SUMMARY_MESSAGE,
    MISSING_FILE_MESSAGE,
    summarize_file,
    summarize_text,
)


def test_summarize_long_text_truncates():
    long_text = "word " * 500
    summary = summarize_text(long_text, max_chars=160)
    assert len(summary) <= 160


def test_summarize_short_text_passthrough():
    text = "Short summary line."
    summary = summarize_text(text, max_chars=160)
    assert summary == text


def test_summarize_empty_text():
    summary = summarize_text("   ", max_chars=160)
    assert summary == EMPTY_SUMMARY_MESSAGE


def test_summarize_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.txt"
    summary = summarize_file(missing, max_chars=160)
    assert summary == MISSING_FILE_MESSAGE
