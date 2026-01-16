"""Tests for gateway thread id resolution."""

import tempfile
from pathlib import Path

from milton_gateway.models import ChatCompletionRequest
from milton_gateway.server import _resolve_thread_id, _SESSION_COOKIE_NAME
from storage.chat_memory import ChatMemoryStore


def _make_request(first_message: str, **kwargs) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="milton",
        messages=[{"role": "user", "content": first_message}],
        **kwargs,
    )


def test_thread_id_prefers_conversation_id_over_cookie():
    chat_request = _make_request("Hello", conversation_id="conv-123")
    thread_id, new_session_id, source = _resolve_thread_id(
        chat_request,
        cookies={_SESSION_COOKIE_NAME: "session-abc"},
    )

    assert thread_id == "conv-123"
    assert new_session_id is None
    assert source == "body:conversation_id"


def test_thread_id_from_cookie_when_body_missing():
    chat_request = _make_request("Hello")
    thread_id, new_session_id, source = _resolve_thread_id(
        chat_request,
        cookies={_SESSION_COOKIE_NAME: "session-abc"},
    )

    assert thread_id == "session-abc"
    assert new_session_id is None
    assert source == "cookie"


def test_thread_id_generates_session_id_when_missing():
    chat_request = _make_request("Hello")
    thread_id, new_session_id, source = _resolve_thread_id(chat_request)

    assert thread_id
    assert new_session_id == thread_id
    assert source == "cookie:new"


def test_thread_id_stable_within_session_cookie():
    chat_request = _make_request("Hello")
    cookies = {_SESSION_COOKIE_NAME: "session-abc"}

    thread_id_1, _, _ = _resolve_thread_id(chat_request, cookies=cookies)
    thread_id_2, _, _ = _resolve_thread_id(chat_request, cookies=cookies)

    assert thread_id_1 == thread_id_2


def test_identical_first_message_different_sessions_no_leakage():
    chat_request_a = _make_request("Hello")
    chat_request_b = _make_request("Hello")

    thread_id_a, _, _ = _resolve_thread_id(
        chat_request_a,
        cookies={_SESSION_COOKIE_NAME: "session-a"},
    )
    thread_id_b, _, _ = _resolve_thread_id(
        chat_request_b,
        cookies={_SESSION_COOKIE_NAME: "session-b"},
    )

    assert thread_id_a != thread_id_b

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = Path(f.name)

    store = None
    try:
        store = ChatMemoryStore(db_path)
        store.append_turn(thread_id_a, "user", "Hello")
        store.append_turn(thread_id_a, "assistant", "Hi")

        turns_b = store.get_recent_turns(thread_id_b, limit=10)
        assert turns_b == []
    finally:
        if store is not None:
            store.close()
        if db_path.exists():
            db_path.unlink()
