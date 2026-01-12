"""Tests for ntfy summary helpers."""

from pathlib import Path

import pytest

from milton_orchestrator.ntfy_summarizer import (
    EMPTY_SUMMARY_MESSAGE,
    MISSING_FILE_MESSAGE,
    summarize_file,
    summarize_text,
    finalize_for_ntfy,
    NtfyFinalizedMessage,
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


# ==============================================================================
# finalize_for_ntfy Tests
# ==============================================================================

def test_finalize_for_ntfy_short_text_unchanged():
    """Short text should pass through unchanged."""
    short_text = "This is a short response."
    result = finalize_for_ntfy(
        full_text=short_text,
        request_id="test_123",
        max_inline_chars=1000,
    )

    assert result.inline_text == short_text
    assert result.output_path is None
    assert result.output_url is None
    assert result.was_truncated is False


def test_finalize_for_ntfy_long_text_truncated():
    """Long text should be truncated and indicate it was cut."""
    long_text = "This is a very long response. " * 200  # ~6000 chars
    max_chars = 500

    result = finalize_for_ntfy(
        full_text=long_text,
        request_id="test_long",
        max_inline_chars=max_chars,
    )

    assert len(result.inline_text) <= max_chars
    assert result.was_truncated is True
    # Should indicate output was too long
    assert "too long" in result.inline_text or "Full output" in result.inline_text


def test_finalize_for_ntfy_long_text_saves_file(tmp_path: Path):
    """Long text should be saved to file when output_dir provided."""
    long_text = "This is a very long response with important content. " * 100
    max_chars = 300

    result = finalize_for_ntfy(
        full_text=long_text,
        request_id="test_save",
        max_inline_chars=max_chars,
        output_dir=tmp_path,
    )

    # Should have saved file
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.read_text() == long_text

    # Inline text should be within limit
    assert len(result.inline_text) <= max_chars
    assert result.was_truncated is True

    # Should reference the file path
    assert str(result.output_path) in result.inline_text or "Full output" in result.inline_text


def test_finalize_for_ntfy_includes_url_when_configured(tmp_path: Path):
    """Should include URL when output_base_url is configured."""
    long_text = "Long content here " * 100
    max_chars = 300
    base_url = "https://example.com/outputs"

    result = finalize_for_ntfy(
        full_text=long_text,
        request_id="test_url",
        max_inline_chars=max_chars,
        output_dir=tmp_path,
        output_base_url=base_url,
    )

    assert result.output_url is not None
    assert result.output_url.startswith(base_url)
    assert result.output_path is not None
    assert result.output_path.name in result.output_url


def test_finalize_for_ntfy_empty_text():
    """Empty text should return default message."""
    result = finalize_for_ntfy(
        full_text="",
        request_id="test_empty",
        max_inline_chars=1000,
    )

    assert "No response" in result.inline_text
    assert result.was_truncated is False


def test_finalize_for_ntfy_respects_filename_template(tmp_path: Path):
    """Should use the filename template for output files."""
    long_text = "Content " * 100
    request_id = "my_request_123"
    template = "output_{request_id}.md"

    result = finalize_for_ntfy(
        full_text=long_text,
        request_id=request_id,
        max_inline_chars=100,
        output_dir=tmp_path,
        output_filename_template=template,
    )

    assert result.output_path is not None
    assert "my_request_123" in result.output_path.name
    assert result.output_path.suffix == ".md"


def test_finalize_for_ntfy_inline_text_never_exceeds_limit(tmp_path: Path):
    """Inline text must NEVER exceed max_inline_chars."""
    # Test with various sizes
    for text_len in [100, 500, 1000, 5000, 10000]:
        for max_chars in [50, 100, 200, 500, 1000]:
            long_text = "x" * text_len
            result = finalize_for_ntfy(
                full_text=long_text,
                request_id=f"test_{text_len}_{max_chars}",
                max_inline_chars=max_chars,
                output_dir=tmp_path,
            )

            assert len(result.inline_text) <= max_chars, \
                f"Inline text exceeded limit: {len(result.inline_text)} > {max_chars}"


def test_finalize_for_ntfy_with_url_inline_text_fits(tmp_path: Path):
    """When URL is included, total inline text still fits within limit."""
    long_text = "Detailed output content here " * 200
    max_chars = 400
    long_base_url = "https://very-long-domain-name.example.com/outputs/directory/subdirectory"

    result = finalize_for_ntfy(
        full_text=long_text,
        request_id="test_long_url",
        max_inline_chars=max_chars,
        output_dir=tmp_path,
        output_base_url=long_base_url,
    )

    # Must still fit
    assert len(result.inline_text) <= max_chars
    # But should include reference to full output
    assert "Full output" in result.inline_text or "📄" in result.inline_text


def test_finalize_for_ntfy_collision_handling(tmp_path: Path):
    """Should handle filename collisions."""
    long_text = "Content " * 100
    request_id = "same_id"

    # Create first file
    result1 = finalize_for_ntfy(
        full_text=long_text,
        request_id=request_id,
        max_inline_chars=100,
        output_dir=tmp_path,
    )

    # Create second file with same request_id
    result2 = finalize_for_ntfy(
        full_text=long_text + " extra",
        request_id=request_id,
        max_inline_chars=100,
        output_dir=tmp_path,
    )

    # Should have different paths
    assert result1.output_path != result2.output_path
    assert result1.output_path.exists()
    assert result2.output_path.exists()
