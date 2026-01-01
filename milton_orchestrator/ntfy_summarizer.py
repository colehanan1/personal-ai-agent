"""Summarize and truncate ntfy messages for iPhone-friendly delivery."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 160
EMPTY_SUMMARY_MESSAGE = "No content to summarize"
MISSING_FILE_MESSAGE = "Summary unavailable (file missing)"


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
