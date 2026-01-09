"""Normalize incoming user inputs across text and attachments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import json
import logging
import re

logger = logging.getLogger(__name__)

_MODE_ALIASES = {
    "claude": "CLAUDE",
    "claude_code": "CLAUDE",
    "codex": "CODEX",
    "codex_code": "CODEX",
    "research": "RESEARCH",
    "chat": "CHAT",
    "remind": "REMIND",
    "alarm": "ALARM",
}

_PRIMARY_KEYS = (
    "providedinput",
    "input",
    "message",
    "text",
    "prompt",
    "query",
    "request",
    "instruction",
    "instructions",
    "task",
    "content",
)

_SECTION_KEYS = (
    "goals",
    "goal",
    "summary",
    "summaries",
    "notes",
    "context",
    "details",
    "requirements",
    "constraints",
    "plan",
    "steps",
    "background",
    "logs",
)

_GOAL_KEYS = {
    "goal",
    "goals",
    "objective",
    "objectives",
    "aim",
    "aims",
    "todo",
    "todos",
}

_SUMMARY_KEYS = {
    "summary",
    "summaries",
    "daily_summary",
    "day_summary",
    "dailyreport",
}

_MODE_KEYS = {"mode", "intent", "pipeline", "route", "routing", "target"}


@dataclass
class ExtractedText:
    primary: str = ""
    sections: list[tuple[str, str]] = field(default_factory=list)
    structured_fields: dict[str, list[str]] = field(default_factory=dict)
    mode_hint: Optional[str] = None

    def as_text(self) -> str:
        parts: list[str] = []
        if self.primary.strip():
            parts.append(self.primary.strip())
        for label, content in self.sections:
            content = content.strip()
            if not content:
                continue
            parts.append(f"{_labelize(label)}:\n{content}")
        return "\n\n".join(parts).strip()


@dataclass
class AttachmentPayload:
    name: Optional[str]
    content_type: Optional[str]
    size: Optional[int]
    url: Optional[str]
    raw: dict[str, Any]
    text: Optional[str] = None
    semantic_text: Optional[str] = None
    structured_fields: dict[str, list[str]] = field(default_factory=dict)
    mode_hint: Optional[str] = None
    parse_error: Optional[str] = None


@dataclass
class NormalizedInput:
    semantic_input: str
    input_type: str
    normalized_length: int
    attachments: list[AttachmentPayload] = field(default_factory=list)
    structured_fields: dict[str, list[str]] = field(default_factory=dict)
    mode_hint: Optional[str] = None


def normalize_incoming_input(
    message: str,
    *,
    raw_data: Optional[dict[str, Any]] = None,
    attachment_fetcher: Optional[Callable[[str], Optional[str]]] = None,
) -> NormalizedInput:
    message_text = _clean_text(message)
    message_extracted = _extract_semantic_text(message_text)
    structured_fields = _merge_structured_fields({}, message_extracted.structured_fields)
    mode_hint = message_extracted.mode_hint

    attachments: list[AttachmentPayload] = []
    for payload in _extract_attachments(raw_data):
        attachment = _process_attachment(payload, attachment_fetcher=attachment_fetcher)
        attachments.append(attachment)
        structured_fields = _merge_structured_fields(
            structured_fields, attachment.structured_fields
        )
        if not mode_hint and attachment.mode_hint:
            mode_hint = attachment.mode_hint

    semantic_input = _assemble_semantic_input(message_extracted, attachments)
    if mode_hint and semantic_input and not _has_mode_prefix(semantic_input):
        prefix = _MODE_ALIASES.get(mode_hint.lower())
        if prefix:
            semantic_input = f"{prefix}: {semantic_input}"

    input_type = _infer_input_type(message_extracted, attachments)
    return NormalizedInput(
        semantic_input=semantic_input,
        input_type=input_type,
        normalized_length=len(semantic_input),
        attachments=attachments,
        structured_fields=structured_fields,
        mode_hint=mode_hint,
    )


def _infer_input_type(
    message_extracted: ExtractedText, attachments: list[AttachmentPayload]
) -> str:
    has_text = bool(message_extracted.as_text())
    has_attachments = any(att.semantic_text for att in attachments)
    if has_text and has_attachments:
        return "mixed"
    if has_attachments:
        return "attachment"
    if has_text:
        return "text"
    return "empty"


def _assemble_semantic_input(
    message_extracted: ExtractedText,
    attachments: list[AttachmentPayload],
) -> str:
    parts: list[str] = []
    message_text = message_extracted.as_text()
    if message_text:
        parts.append(message_text)

    for idx, attachment in enumerate(attachments):
        if not attachment.semantic_text:
            continue
        block = attachment.semantic_text.strip()
        if parts or idx > 0:
            label = attachment.name or "attachment"
            block = f"Attachment ({label}):\n{block}"
        parts.append(block)

    return "\n\n".join(part for part in parts if part).strip()


def _extract_attachments(raw_data: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not raw_data:
        return []
    attachments: list[dict[str, Any]] = []
    payload = raw_data.get("attachment")
    if isinstance(payload, dict):
        attachments.append(payload)
    payloads = raw_data.get("attachments")
    if isinstance(payloads, list):
        attachments.extend([item for item in payloads if isinstance(item, dict)])
    payload = raw_data.get("file")
    if isinstance(payload, dict):
        attachments.append(payload)
    payloads = raw_data.get("files")
    if isinstance(payloads, list):
        attachments.extend([item for item in payloads if isinstance(item, dict)])
    return attachments


def _process_attachment(
    payload: dict[str, Any],
    *,
    attachment_fetcher: Optional[Callable[[str], Optional[str]]] = None,
) -> AttachmentPayload:
    raw_text, parse_error = _extract_attachment_text(
        payload, attachment_fetcher=attachment_fetcher
    )
    extracted = _extract_semantic_text(raw_text or "")
    return AttachmentPayload(
        name=_coerce_str(payload.get("name") or payload.get("filename")),
        content_type=_coerce_str(payload.get("type") or payload.get("content_type")),
        size=_coerce_int(payload.get("size")),
        url=_coerce_str(payload.get("url") or payload.get("link")),
        raw=payload,
        text=raw_text,
        semantic_text=extracted.as_text() if raw_text else "",
        structured_fields=extracted.structured_fields,
        mode_hint=extracted.mode_hint,
        parse_error=parse_error,
    )


def _extract_attachment_text(
    payload: dict[str, Any],
    *,
    attachment_fetcher: Optional[Callable[[str], Optional[str]]] = None,
) -> tuple[Optional[str], Optional[str]]:
    for key in ("content", "text", "body", "data"):
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True), None
        if value is not None:
            return str(value), None

    url = payload.get("url") or payload.get("link")
    if not url:
        return None, "attachment missing content and url"

    fetcher = attachment_fetcher or _default_attachment_fetcher
    try:
        text = fetcher(str(url))
        if text is None:
            return None, "attachment fetch returned no content"
        return text, None
    except Exception as exc:
        logger.warning("Failed to fetch attachment %s: %s", url, exc)
        return None, f"attachment fetch failed: {exc}"


def _default_attachment_fetcher(url: str) -> Optional[str]:
    import requests

    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.text


def _extract_semantic_text(text: str) -> ExtractedText:
    text = _clean_text(text)
    if not text:
        return ExtractedText()

    candidate = _unwrap_json_string(text)
    if isinstance(candidate, str) and candidate != text:
        text = candidate.strip()

    parsed = _maybe_parse_json(text)
    if parsed is None:
        extracted = _extract_provided_input_from_raw(text)
        if extracted:
            return ExtractedText(primary=_strip_leading_labels(extracted))
        return ExtractedText(primary=_strip_leading_labels(text))

    if isinstance(parsed, str):
        return ExtractedText(primary=_strip_leading_labels(parsed.strip()))
    return _extract_from_structured(parsed)


def _extract_from_structured(data: Any) -> ExtractedText:
    structured_fields = _collect_structured_fields(data)
    mode_hint = _extract_mode_hint(data)

    if isinstance(data, list):
        return ExtractedText(
            primary=_stringify_value(data),
            structured_fields=structured_fields,
            mode_hint=mode_hint,
        )

    if not isinstance(data, dict):
        return ExtractedText(
            primary=_stringify_value(data),
            structured_fields=structured_fields,
            mode_hint=mode_hint,
        )

    normalized_keys = {_normalize_key(key): key for key in data.keys()}

    primary = ""
    used_keys: set[str] = set()
    for candidate in _PRIMARY_KEYS:
        if candidate in normalized_keys:
            raw_key = normalized_keys[candidate]
            value = data.get(raw_key)
            primary = _stringify_value(value)
            used_keys.add(raw_key)
            if primary:
                break

    sections: list[tuple[str, str]] = []
    ordered = _ordered_section_keys(data.keys(), used_keys)
    for key in ordered:
        value = data.get(key)
        rendered = _stringify_value(value)
        if rendered:
            sections.append((str(key), rendered))

    if not primary and sections:
        primary = sections.pop(0)[1]

    return ExtractedText(
        primary=_strip_leading_labels(primary),
        sections=sections,
        structured_fields=structured_fields,
        mode_hint=mode_hint,
    )


def _ordered_section_keys(keys: Any, used_keys: set[str]) -> list[str]:
    normalized_map = {_normalize_key(key): str(key) for key in keys}
    ordered: list[str] = []
    for candidate in _SECTION_KEYS:
        raw = normalized_map.get(candidate)
        if raw and raw not in used_keys and raw not in ordered:
            ordered.append(raw)
    for key in sorted([str(k) for k in keys], key=str):
        if key in used_keys or key in ordered:
            continue
        ordered.append(key)
    return ordered


def _collect_structured_fields(data: Any) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {"goals": [], "summaries": []}

    def _add(field: str, value: str) -> None:
        cleaned = value.strip()
        if not cleaned or cleaned in fields[field]:
            return
        fields[field].append(cleaned)

    def _extract_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                values.extend(_extract_values(item))
            return values
        if isinstance(value, dict):
            for key in ("text", "value", "goal", "summary", "content", "description"):
                if key in value and isinstance(value[key], str):
                    return [value[key]]
            return []
        return [str(value)]

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = _normalize_key(key)
                if normalized in _GOAL_KEYS:
                    for text in _extract_values(item):
                        _add("goals", text)
                if normalized in _SUMMARY_KEYS:
                    for text in _extract_values(item):
                        _add("summaries", text)
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(data)
    return fields


def _extract_mode_hint(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = _normalize_key(key)
            if normalized in _MODE_KEYS and isinstance(value, str):
                alias = _MODE_ALIASES.get(value.strip().lower())
                if alias:
                    return value.strip().lower()
    return None


def _maybe_parse_json(text: str) -> Optional[Any]:
    stripped = text.strip()
    if not stripped:
        return None

    if stripped[0] in ("'", "\""):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


def _unwrap_json_string(text: str) -> Optional[str]:
    if not text or text[0] not in ("\"", "'"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, str):
        return parsed
    return None


def _stringify_value(value: Any, *, depth: int = 0, max_depth: int = 3) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                summary = _summarize_dict(item)
                if summary:
                    lines.append(summary)
                    continue
            rendered = _stringify_value(item, depth=depth + 1, max_depth=max_depth)
            if not rendered:
                continue
            if "\n" in rendered:
                lines.append(rendered)
            else:
                lines.append(f"- {rendered}")
        return "\n".join(lines).strip()
    if isinstance(value, dict):
        if depth >= max_depth:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        title = _coerce_str(value.get("title") or value.get("heading") or value.get("name"))
        body = _coerce_str(
            value.get("content")
            or value.get("text")
            or value.get("summary")
            or value.get("details")
            or value.get("body")
        )
        if title and body:
            return f"{title}: {body}"
        lines: list[str] = []
        for key in sorted(value.keys(), key=str):
            rendered = _stringify_value(value[key], depth=depth + 1, max_depth=max_depth)
            if rendered:
                lines.append(f"{_labelize(key)}: {rendered}")
        return "\n".join(lines).strip()
    return str(value).strip()


def _summarize_dict(value: dict[str, Any]) -> str:
    title = _coerce_str(value.get("title") or value.get("name") or value.get("heading"))
    if title:
        detail = _coerce_str(value.get("summary") or value.get("text") or value.get("content"))
        if detail:
            return f"{title}: {detail}"
        return title
    return ""


def _labelize(value: Any) -> str:
    text = str(value).strip().replace("_", " ")
    return re.sub(r"\s+", " ", text)


def _normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(key).lower())


def _clean_text(text: str) -> str:
    return str(text or "").lstrip("\ufeff").strip()


def _merge_structured_fields(
    existing: dict[str, list[str]], incoming: dict[str, list[str]]
) -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in existing.items()}
    for key, values in incoming.items():
        if key not in merged:
            merged[key] = []
        for value in values:
            if value not in merged[key]:
                merged[key].append(value)
    return merged


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_mode_prefix(text: str) -> bool:
    return bool(re.match(r"^\s*\[?\s*(CLAUDE|CODEX|RESEARCH|REMIND|ALARM)\b", text, re.IGNORECASE))


def _strip_leading_labels(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"^provided input\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\[[^\]]+\]\s*[:\-]\s*", "", cleaned)
    return cleaned.strip()


def _extract_provided_input_from_raw(text: str) -> Optional[str]:
    if "provided" not in text.lower():
        return None

    match = re.search(
        r"provided\s*input[^:]*:\s*(.+)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    value = match.group(1).strip()
    if not value:
        return None

    quote_chars = ('"', "'", "\u201c", "\u201d", "\u2018", "\u2019")
    if value[0] in quote_chars:
        quote = value[0]
        remainder = value[1:]
        if quote in ('"', "'"):
            closing = re.search(rf"(?<!\\\\){re.escape(quote)}", remainder)
        else:
            closing = re.search(re.escape(quote), remainder)
        if closing:
            value = remainder[: closing.start()]
        else:
            value = remainder
    else:
        for sep in ('","', '"}', '",', "\n", "\r"):
            idx = value.find(sep)
            if idx != -1:
                value = value[:idx]
                break
        if "}" in value:
            value = value.split("}")[0]

    return value.strip(" \t\"'\u201c\u201d")
