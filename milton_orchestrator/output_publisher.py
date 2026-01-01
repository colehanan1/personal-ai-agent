"""Helpers for publishing Milton outputs with ntfy Click URLs."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .config import Config
from .ntfy_summarizer import truncate_text

logger = logging.getLogger(__name__)


def save_output_text(
    text: str,
    request_id: str,
    output_dir: Path,
    filename_template: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = _sanitize_request_id(request_id)

    try:
        filename = filename_template.format(request_id=safe_request_id)
    except (KeyError, ValueError) as exc:
        logger.warning(
            f"Invalid OUTPUT_FILENAME_TEMPLATE '{filename_template}': {exc}. Using fallback."
        )
        filename = f"milton_{safe_request_id}.txt"

    filename = Path(filename).name
    filename = _sanitize_filename(filename)
    if not filename:
        filename = f"milton_{safe_request_id}.txt"

    filepath = _resolve_collision(output_dir / filename)
    filepath.write_text(text, encoding="utf-8")
    logger.info(f"Saved output to {filepath}")
    return filepath


def build_output_url(base_url: str, file_path: Path) -> str:
    base = base_url.rstrip("/")
    return f"{base}/{file_path.name}"


def build_share_url(
    share_url: Optional[str],
    share_host: Optional[str],
    share_name: Optional[str],
    file_path: Path,
) -> Optional[str]:
    base = None
    if share_url:
        base = share_url.strip()
    elif share_host and share_name:
        host = share_host.strip().strip("/")
        name = share_name.strip().strip("/")
        if host and name:
            base = f"smb://{host}/{name}"

    if not base:
        return None

    if "://" not in base:
        base = f"smb://{base.lstrip('/')}"

    base = base.rstrip("/")
    return f"{base}/{file_path.name}"


def publish_with_click(
    ntfy_client,
    topic: str,
    title: str,
    body: str,
    click_url: str,
) -> None:
    ntfy_client.publish(topic, body, title=title, click_url=click_url)


def publish_response(
    ntfy_client,
    topic: str,
    title: str,
    full_text: str,
    request_id: str,
    config: Config,
    inline_body: Optional[str] = None,
    force_file: bool = False,
) -> None:
    text = full_text or ""
    inline_limit = config.ntfy_max_inline_chars
    use_file = (
        config.always_file_attachments
        or force_file
        or len(text) > inline_limit
    )

    if not use_file:
        body = inline_body if inline_body is not None else text
        if not body:
            body = "No output produced."
        body = truncate_text(body, max_chars=inline_limit)
        ntfy_client.publish(topic, body, title=title)
        return

    try:
        output_path = save_output_text(
            text=text,
            request_id=request_id,
            output_dir=config.output_dir,
            filename_template=config.output_filename_template,
        )
    except OSError as exc:
        logger.error(f"Failed to save output file: {exc}")
        body = truncate_text(text, max_chars=inline_limit) or "No output produced."
        ntfy_client.publish(topic, body, title=title)
        return

    if config.output_base_url:
        click_url = build_output_url(config.output_base_url, output_path)
        body = f"Tap to open full output. Saved on server: {output_path.name}"
        publish_with_click(ntfy_client, topic, title, body, click_url)
        return

    share_url = build_share_url(
        config.output_share_url,
        config.output_share_host,
        config.output_share_name,
        output_path,
    )
    if share_url:
        body = (
            "Full output saved to SMB share.\n"
            f"File: {output_path.name}\n"
            f"Share: {share_url}"
        )
        ntfy_client.publish(topic, body, title=title)
        return

    logger.warning(
        "No OUTPUT_BASE_URL or SMB share configured; publishing inline fallback"
    )
    prefix = f"Output saved locally: {output_path}"
    detail = inline_body if inline_body else text
    combined = f"{prefix}\n\n{detail}" if detail else prefix
    combined = truncate_text(combined, max_chars=inline_limit)
    ntfy_client.publish(topic, combined, title=title)


def _sanitize_request_id(request_id: str) -> str:
    normalized = request_id.strip()
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", normalized)
    return safe or "request"


def _sanitize_filename(filename: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return sanitized.strip("._-") or "output.txt"


def _resolve_collision(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem or "output"
    suffix = path.suffix or ".txt"
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate

    logger.warning(f"Too many collisions for {path}; overwriting")
    return path
