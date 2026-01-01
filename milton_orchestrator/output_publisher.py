"""Helpers for publishing Milton outputs with ntfy Click URLs."""

from __future__ import annotations

import logging
import re
import sys
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
    output_path: Optional[Path] = None,
    mode_tag: Optional[str] = None,
) -> None:
    text = full_text or ""
    inline_limit = config.ntfy_max_inline_chars
    use_file = (
        config.always_file_attachments
        or force_file
        or len(text) > inline_limit
    )

    persisted_path = output_path
    if persisted_path is None and text:
        try:
            persisted_path = save_output_text(
                text=text,
                request_id=request_id,
                output_dir=config.output_dir,
                filename_template=config.output_filename_template,
            )
        except OSError as exc:
            logger.error(f"Failed to save output file: {exc}")
            persisted_path = None

    if not use_file:
        body = inline_body if inline_body is not None else text
        body = _build_inline_body(request_id, body, inline_limit)
        ntfy_client.publish(topic, body, title=title)
        _record_result_memory(
            request_id=request_id,
            mode_tag=mode_tag,
            content=text,
            evidence=_build_evidence(persisted_path, None, None),
            repo_root=config.target_repo,
            max_chars=config.max_output_size,
        )
        return

    try:
        if persisted_path is None and text:
            persisted_path = save_output_text(
                text=text,
                request_id=request_id,
                output_dir=config.output_dir,
                filename_template=config.output_filename_template,
            )
    except OSError as exc:
        logger.error(f"Failed to save output file: {exc}")
        body = _build_inline_body(request_id, text, inline_limit)
        ntfy_client.publish(topic, body, title=title)
        _record_result_memory(
            request_id=request_id,
            mode_tag=mode_tag,
            content=text,
            evidence=_build_evidence(None, None, None),
            repo_root=config.target_repo,
            max_chars=config.max_output_size,
        )
        return

    if not persisted_path:
        body = _build_inline_body(request_id, text, inline_limit)
        ntfy_client.publish(topic, body, title=title)
        _record_result_memory(
            request_id=request_id,
            mode_tag=mode_tag,
            content=text,
            evidence=_build_evidence(None, None, None),
            repo_root=config.target_repo,
            max_chars=config.max_output_size,
        )
        return

    click_url = None
    if config.output_base_url and persisted_path:
        click_url = build_output_url(config.output_base_url, persisted_path)
        body = _build_link_body(request_id, "Full output", click_url)
        publish_with_click(ntfy_client, topic, title, body, click_url)
        _record_result_memory(
            request_id=request_id,
            mode_tag=mode_tag,
            content=text,
            evidence=_build_evidence(persisted_path, click_url, None),
            repo_root=config.target_repo,
            max_chars=config.max_output_size,
        )
        logger.info(
            "Published click-to-open output: request_id=%s path=%s url=%s",
            request_id,
            persisted_path,
            click_url,
        )
        return

    share_url = build_share_url(
        config.output_share_url,
        config.output_share_host,
        config.output_share_name,
        persisted_path,
    )
    if share_url:
        filename = persisted_path.name if persisted_path else "output.txt"
        body = _build_link_body(request_id, "SMB share", share_url)
        body = f"{body}\nFile: {filename}"
        ntfy_client.publish(topic, body, title=title)
        _record_result_memory(
            request_id=request_id,
            mode_tag=mode_tag,
            content=text,
            evidence=_build_evidence(persisted_path, None, share_url),
            repo_root=config.target_repo,
            max_chars=config.max_output_size,
        )
        return

    logger.warning(
        "No OUTPUT_BASE_URL or SMB share configured; publishing inline fallback"
    )
    prefix = (
        f"Output saved locally: {persisted_path}"
        if persisted_path
        else "Output saved locally."
    )
    detail = inline_body if inline_body else text
    combined = f"{prefix}\n\n{detail}" if detail else prefix
    body = _build_inline_body(request_id, combined, inline_limit)
    ntfy_client.publish(topic, body, title=title)
    _record_result_memory(
        request_id=request_id,
        mode_tag=mode_tag,
        content=text,
        evidence=_build_evidence(persisted_path, None, None),
        repo_root=config.target_repo,
        max_chars=config.max_output_size,
    )


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


def _build_inline_body(request_id: str, body: str, max_chars: int) -> str:
    prefix = f"[{request_id}] "
    content = body or "No output produced."
    available = max_chars - len(prefix)
    if available <= 0:
        return prefix.strip()
    trimmed = truncate_text(content, max_chars=available)
    return f"{prefix}{trimmed}"


def _build_link_body(request_id: str, label: str, link: str) -> str:
    return f"[{request_id}] {label}: {link}"


def _build_evidence(
    output_path: Optional[Path],
    click_url: Optional[str],
    share_url: Optional[str],
) -> list[str]:
    evidence: list[str] = []
    if output_path:
        evidence.append(str(output_path))
    if click_url:
        evidence.append(click_url)
    if share_url:
        evidence.append(share_url)
    return evidence


def _record_result_memory(
    *,
    request_id: str,
    mode_tag: Optional[str],
    content: str,
    evidence: list[str],
    repo_root: Path,
    max_chars: int,
) -> None:
    try:
        MemoryItem, add_memory = _get_memory_modules()
    except Exception as exc:
        logger.warning("Failed to load memory modules: %s", exc)
        return

    if not content.strip():
        content = "No output produced."

    tags = []
    if mode_tag:
        tags.append(mode_tag)

    memory_item = MemoryItem(
        agent="orchestrator",
        type="result",
        content=truncate_text(content, max_chars=max_chars),
        tags=tags,
        importance=0.4,
        source="orchestrator",
        request_id=request_id,
        evidence=evidence,
    )

    try:
        add_memory(memory_item, repo_root=repo_root)
    except Exception as exc:
        logger.warning("Failed to record result memory: %s", exc)


_MEMORY_CACHE = None


def _get_memory_modules():
    global _MEMORY_CACHE
    if _MEMORY_CACHE is not None:
        return _MEMORY_CACHE
    try:
        from memory.schema import MemoryItem
        from memory.store import add_memory
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[1]
        repo_str = str(repo_root)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)
        from memory.schema import MemoryItem
        from memory.store import add_memory
    _MEMORY_CACHE = (MemoryItem, add_memory)
    return _MEMORY_CACHE
