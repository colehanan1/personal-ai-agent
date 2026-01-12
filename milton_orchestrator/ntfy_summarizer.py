"""Summarize and truncate ntfy messages for iPhone-friendly delivery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 160
DEFAULT_MAX_INLINE_CHARS = 3000
EMPTY_SUMMARY_MESSAGE = "No content to summarize"
MISSING_FILE_MESSAGE = "Summary unavailable (file missing)"


@dataclass
class NtfyFinalizedMessage:
    """Result of finalizing a message for ntfy delivery."""

    inline_text: str  # Text to send inline (always within limit)
    output_path: Optional[Path]  # Path to full output file (if created)
    output_url: Optional[str]  # URL to full output (if available)
    was_truncated: bool  # Whether full text was too long


def finalize_for_ntfy(
    full_text: str,
    request_id: str,
    max_inline_chars: int = DEFAULT_MAX_INLINE_CHARS,
    output_dir: Optional[Path] = None,
    output_base_url: Optional[str] = None,
    output_filename_template: str = "milton_{request_id}.txt",
) -> NtfyFinalizedMessage:
    """
    Finalize a response for ntfy delivery with hard size enforcement.

    If the full text exceeds max_inline_chars:
    1. Write full text to output_dir (if provided)
    2. Return a summary + link (or path) that fits within limit

    Args:
        full_text: Full response text to finalize
        request_id: Unique request identifier for filename
        max_inline_chars: Maximum characters for inline message
        output_dir: Directory to write output files (optional)
        output_base_url: Base URL for output links (optional)
        output_filename_template: Template for output filenames

    Returns:
        NtfyFinalizedMessage with inline text and optional file info
    """
    if not full_text:
        return NtfyFinalizedMessage(
            inline_text="No response generated.",
            output_path=None,
            output_url=None,
            was_truncated=False,
        )

    # If text fits, return as-is (with safety truncation)
    if len(full_text) <= max_inline_chars:
        return NtfyFinalizedMessage(
            inline_text=full_text,
            output_path=None,
            output_url=None,
            was_truncated=False,
        )

    # Text exceeds limit - need to truncate and optionally save to file
    output_path: Optional[Path] = None
    output_url: Optional[str] = None

    # Try to save to file if output_dir is provided
    if output_dir:
        try:
            output_path = _save_output_file(
                full_text, request_id, output_dir, output_filename_template
            )
            if output_base_url:
                output_url = f"{output_base_url.rstrip('/')}/{output_path.name}"
        except OSError as exc:
            logger.error(f"Failed to save output file: {exc}")
            output_path = None

    # Build inline message with summary + link/path
    inline_text = _build_truncated_message(
        full_text=full_text,
        max_chars=max_inline_chars,
        output_path=output_path,
        output_url=output_url,
    )

    return NtfyFinalizedMessage(
        inline_text=inline_text,
        output_path=output_path,
        output_url=output_url,
        was_truncated=True,
    )


def _save_output_file(
    text: str,
    request_id: str,
    output_dir: Path,
    filename_template: str,
) -> Path:
    """Save text to output file, returning the path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize request_id for filename
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", request_id.strip()) or "request"

    try:
        filename = filename_template.format(request_id=safe_id)
    except (KeyError, ValueError):
        filename = f"milton_{safe_id}.txt"

    # Sanitize filename
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    if not filename:
        filename = f"milton_{safe_id}.txt"

    filepath = output_dir / filename

    # Handle collisions
    if filepath.exists():
        stem = filepath.stem or "output"
        suffix = filepath.suffix or ".txt"
        for idx in range(1, 1000):
            candidate = output_dir / f"{stem}_{idx}{suffix}"
            if not candidate.exists():
                filepath = candidate
                break

    filepath.write_text(text, encoding="utf-8")
    logger.info(f"Saved full output to {filepath} ({len(text)} chars)")
    return filepath


def _build_truncated_message(
    full_text: str,
    max_chars: int,
    output_path: Optional[Path],
    output_url: Optional[str],
) -> str:
    """Build a truncated message with summary and link/path reference."""
    # Extract a summary from the full text
    summary = summarize_text(full_text, max_chars=min(max_chars // 2, 500))

    # Build the reference line
    if output_url:
        ref_line = f"\n\n📄 Full output: {output_url}"
    elif output_path:
        ref_line = f"\n\n📄 Full output saved: {output_path}"
    else:
        ref_line = "\n\n(Full output was too long and could not be saved)"

    # Calculate available space for summary
    available = max_chars - len(ref_line) - 20  # Buffer for safety
    if available < 50:
        # Not enough space for summary, just show reference
        return truncate_text(ref_line.strip(), max_chars)

    # Truncate summary to fit
    truncated_summary = truncate_text(summary, max_chars=available)

    result = f"{truncated_summary}{ref_line}"

    # Final safety truncation
    return truncate_text(result, max_chars)


def truncate_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Truncate text to max_chars, adding '...' when shortened."""
    if max_chars <= 0:
        return ""

    if len(text) <= max_chars:
        return text

    if max_chars <= 3:
        return text[:max_chars]

    return f"{text[: max_chars - 3]}..."


def summarize_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Summarize text into a compact, single-line message."""
    if not text or not text.strip():
        return EMPTY_SUMMARY_MESSAGE

    lines = [line.strip() for line in text.splitlines()]
    summary = (
        _extract_summary_block(lines)
        or _extract_status_summary(lines)
        or _extract_first_content_line(lines)
    )

    if not summary:
        summary = EMPTY_SUMMARY_MESSAGE

    summary = _collapse_whitespace(summary)
    return truncate_text(summary, max_chars=max_chars)


def summarize_file(file_path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Summarize a text file, handling missing or unreadable files."""
    try:
        content = file_path.read_text()
    except FileNotFoundError:
        logger.warning(f"Summary file missing: {file_path}")
        return truncate_text(MISSING_FILE_MESSAGE, max_chars=max_chars)
    except OSError as exc:
        logger.warning(f"Failed to read summary file {file_path}: {exc}")
        return truncate_text(MISSING_FILE_MESSAGE, max_chars=max_chars)

    return summarize_text(content, max_chars=max_chars)


def compose_summary(prefix: str, text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Compose a prefix + summarized text, keeping within max_chars."""
    prefix = prefix.strip()
    if not prefix:
        return summarize_text(text, max_chars=max_chars)

    separator = ": "
    available = max_chars - len(prefix) - len(separator)
    if available <= 0:
        return truncate_text(prefix, max_chars=max_chars)

    summary = summarize_text(text, max_chars=available)
    combined = f"{prefix}{separator}{summary}"
    return truncate_text(combined, max_chars=max_chars)


def _extract_summary_block(lines: list[str]) -> Optional[str]:
    for matcher in (_is_impl_summary_header, _is_summary_header):
        start = _find_line_index(lines, matcher)
        if start is None:
            continue
        collected = _collect_section(lines[start + 1 :])
        if collected:
            return " ".join(collected)
    return None


def _extract_status_summary(lines: list[str]) -> Optional[str]:
    parts: list[str] = []

    status = _find_label_value(lines, "Status:")
    success = _find_label_value(lines, "Success:")
    exit_code = _find_label_value(lines, "Exit Code:")
    duration = _find_label_value(lines, "Duration:")
    mode = _find_label_value(lines, "Mode:")

    if status:
        parts.append(f"Status {status}")
    elif success:
        parts.append(f"Success {success}")

    if exit_code:
        parts.append(f"Exit {exit_code}")
    if duration:
        parts.append(f"Duration {duration}")
    if mode:
        parts.append(f"Mode {mode}")

    stderr_line = _first_line_in_section(lines, "=== STDERR ===")
    if not stderr_line:
        stderr_line = _first_line_in_section(lines, "STDERR:")
    if stderr_line:
        parts.append(f"Error {stderr_line}")

    stdout_line = _first_line_in_section(lines, "=== STDOUT ===")
    if not stdout_line:
        stdout_line = _first_line_in_section(lines, "STDOUT:")
    if stdout_line and not parts:
        parts.append(stdout_line)

    if not parts:
        return None

    return "; ".join(parts)


def _extract_first_content_line(lines: list[str]) -> Optional[str]:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_section_header(stripped):
            continue
        return stripped
    return None


def _collect_section(lines: list[str]) -> list[str]:
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if collected:
                break
            continue
        if _is_section_header(stripped):
            break
        cleaned = _clean_line(stripped)
        if cleaned:
            collected.append(cleaned)
    return collected


def _clean_line(line: str) -> str:
    line = re.sub(r"^[-*]\s+", "", line)
    line = re.sub(r"^\d+\.\s+", "", line)
    return line.strip()


def _find_line_index(lines: list[str], matcher) -> Optional[int]:
    for idx, line in enumerate(lines):
        if matcher(line):
            return idx
    return None


def _is_impl_summary_header(line: str) -> bool:
    return line.strip().upper() == "=== IMPLEMENTATION SUMMARY ==="


def _is_summary_header(line: str) -> bool:
    stripped = line.strip()
    upper = stripped.upper()
    return upper == "SUMMARY:" or upper == "SUMMARY"


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("==="):
        return True
    if re.match(r"^[A-Z][A-Z0-9 _-]+:$", stripped):
        return True
    return False


def _find_label_value(lines: list[str], label: str) -> Optional[str]:
    for line in lines:
        if line.startswith(label):
            return line[len(label) :].strip()
    return None


def _first_line_in_section(lines: list[str], header: str) -> Optional[str]:
    for idx, line in enumerate(lines):
        if line.strip() == header:
            for next_line in lines[idx + 1 :]:
                stripped = next_line.strip()
                if not stripped:
                    continue
                if _is_section_header(stripped):
                    return None
                return stripped
    return None


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
