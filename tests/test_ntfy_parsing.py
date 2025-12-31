"""Tests for ntfy message parsing"""

import pytest
from milton_orchestrator.ntfy_client import NtfyMessage, NtfyClient


class TestNtfyMessage:
    """Tests for NtfyMessage parsing"""

    def test_parse_message_event(self):
        raw = {
            "event": "message",
            "id": "abc123",
            "time": 1234567890,
            "topic": "test-topic",
            "message": "Hello world",
        }

        msg = NtfyMessage(raw)

        assert msg.event == "message"
        assert msg.id == "abc123"
        assert msg.time == 1234567890
        assert msg.topic == "test-topic"
        assert msg.message == "Hello world"

    def test_is_message_event(self):
        msg = NtfyMessage({"event": "message", "message": "test"})
        assert msg.is_message_event() is True

    def test_is_not_message_event_keepalive(self):
        msg = NtfyMessage({"event": "keepalive"})
        assert msg.is_message_event() is False

    def test_is_not_message_event_open(self):
        msg = NtfyMessage({"event": "open"})
        assert msg.is_message_event() is False

    def test_handles_missing_fields(self):
        raw = {"event": "message"}
        msg = NtfyMessage(raw)

        assert msg.event == "message"
        assert msg.id == ""
        assert msg.message == ""
        assert msg.time == 0

    def test_repr(self):
        msg = NtfyMessage({
            "event": "message",
            "id": "123",
            "message": "x" * 100,
        })

        repr_str = repr(msg)
        assert "NtfyMessage" in repr_str
        assert "123" in repr_str


class TestNtfyClient:
    """Tests for NtfyClient"""

    def test_init(self):
        client = NtfyClient("https://ntfy.sh")
        assert client.base_url == "https://ntfy.sh"

    def test_init_strips_trailing_slash(self):
        client = NtfyClient("https://ntfy.sh/")
        assert client.base_url == "https://ntfy.sh"

    def test_publish_url_construction(self):
        from unittest.mock import Mock, patch

        client = NtfyClient("https://ntfy.sh")

        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = Mock(raise_for_status=Mock())

            client.publish("test-topic", "Hello")

            # Check URL
            call_args = mock_post.call_args
            url = call_args[0][0]
            assert url == "https://ntfy.sh/test-topic"

    def test_publish_with_title(self):
        from unittest.mock import Mock, patch

        client = NtfyClient("https://ntfy.sh")

        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = Mock(raise_for_status=Mock())

            client.publish("test-topic", "Body", title="Title")

            # Check headers
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert headers["Title"] == "Title"

    def test_publish_with_priority(self):
        from unittest.mock import Mock, patch

        client = NtfyClient("https://ntfy.sh")

        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = Mock(raise_for_status=Mock())

            client.publish("test-topic", "Body", priority=5)

            # Check headers
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert headers["Priority"] == "5"

    def test_publish_failure(self):
        from unittest.mock import Mock, patch
        import requests

        client = NtfyClient("https://ntfy.sh")

        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.RequestException("Error")

            result = client.publish("test-topic", "Body")
            assert result is False
