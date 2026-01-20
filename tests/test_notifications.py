"""Tests for multi-channel notification system."""

from unittest.mock import Mock, patch, MagicMock
import pytest
import json

from milton_orchestrator.notifications import (
    DeliveryResult,
    NtfyProvider,
    VoiceProvider,
    DesktopPopupProvider,
    NotificationRouter,
    create_default_router,
)
from milton_orchestrator.reminders import Reminder, DEFAULT_ACTIONS


@pytest.fixture
def mock_reminder():
    """Create a mock reminder for testing."""
    return Reminder(
        id=42,
        kind="REMIND",
        message="Test reminder",
        due_at=1704067200,  # 2024-01-01 00:00:00 UTC
        created_at=1704060000,
        sent_at=None,
        canceled_at=None,
        timezone="America/New_York",
        channel='["ntfy"]',  # JSON list
        priority="high",
        status="scheduled",
        actions=["DONE", "SNOOZE_30"],
    )


def test_delivery_result_to_dict():
    """Test DeliveryResult serialization."""
    result = DeliveryResult(
        ok=True,
        provider="ntfy",
        message_id="msg123",
        timestamp=1704067200,
        metadata={"url": "https://ntfy.sh/topic"},
    )
    
    d = result.to_dict()
    assert d["ok"] is True
    assert d["provider"] == "ntfy"
    assert d["message_id"] == "msg123"
    assert d["timestamp"] == 1704067200
    assert d["metadata"]["url"] == "https://ntfy.sh/topic"


@patch("milton_orchestrator.notifications.requests.post")
def test_ntfy_provider_success(mock_post, mock_reminder):
    """Test successful ntfy delivery."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "msg123"}
    mock_post.return_value = mock_response
    
    provider = NtfyProvider(
        base_url="https://ntfy.sh",
        topic="test-topic",
        public_base_url="https://milton.example.com",
        action_token="secret123",
    )
    
    result = provider.send(
        mock_reminder,
        title="Test Title",
        body="Test Body",
        actions=["DONE", "SNOOZE_30"],
    )
    
    assert result.ok is True
    assert result.provider == "ntfy"
    assert result.message_id == "msg123"
    assert result.error is None
    
    # Verify request was made correctly
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://ntfy.sh/test-topic"
    
    # Verify headers include actions
    headers = call_args[1]["headers"]
    assert "Title" in headers
    assert "Actions" in headers
    assert "DONE" in headers["Actions"]
    assert "SNOOZE_30" in headers["Actions"]
    # Verify token is in action body
    assert "secret123" in headers["Actions"]


@patch("milton_orchestrator.notifications.requests.post")
def test_ntfy_provider_no_actions(mock_post, mock_reminder):
    """Test ntfy delivery without action buttons."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}
    mock_post.return_value = mock_response
    
    provider = NtfyProvider(
        base_url="https://ntfy.sh",
        topic="test-topic",
        public_base_url=None,  # No public URL = no action buttons
    )
    
    result = provider.send(
        mock_reminder,
        title="Test",
        body="Test",
        actions=["DONE"],
    )
    
    assert result.ok is True
    
    # Verify no Actions header when public_base_url is None
    headers = mock_post.call_args[1]["headers"]
    assert "Actions" not in headers


@patch("milton_orchestrator.notifications.requests.post")
def test_ntfy_provider_http_error(mock_post, mock_reminder):
    """Test ntfy delivery with HTTP error."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_post.return_value = mock_response
    
    provider = NtfyProvider(
        base_url="https://ntfy.sh",
        topic="test-topic",
    )
    
    result = provider.send(
        mock_reminder,
        title="Test",
        body="Test",
        actions=[],
    )
    
    assert result.ok is False
    assert result.provider == "ntfy"
    assert "HTTP 500" in result.error


@patch("milton_orchestrator.notifications.requests.post")
def test_ntfy_provider_exception(mock_post, mock_reminder):
    """Test ntfy delivery with exception."""
    mock_post.side_effect = Exception("Network error")
    
    provider = NtfyProvider(
        base_url="https://ntfy.sh",
        topic="test-topic",
    )
    
    result = provider.send(
        mock_reminder,
        title="Test",
        body="Test",
        actions=[],
    )
    
    assert result.ok is False
    assert "Network error" in result.error


def test_voice_provider_stub(mock_reminder):
    """Test voice provider stub."""
    provider = VoiceProvider()
    
    result = provider.send(
        mock_reminder,
        title="Test",
        body="Test",
        actions=[],
    )
    
    assert result.ok is False
    assert result.provider == "voice"
    assert "not yet implemented" in result.error


def test_desktop_popup_provider_stub(mock_reminder):
    """Test desktop popup provider stub."""
    provider = DesktopPopupProvider()
    
    result = provider.send(
        mock_reminder,
        title="Test",
        body="Test",
        actions=[],
    )
    
    assert result.ok is False
    assert result.provider == "desktop_popup"
    assert "not yet implemented" in result.error


def test_notification_router_single_channel(mock_reminder):
    """Test router with single channel."""
    mock_provider = Mock()
    mock_provider.send.return_value = DeliveryResult(
        ok=True,
        provider="ntfy",
        message_id="msg1",
    )
    
    router = NotificationRouter()
    router.register_provider("ntfy", mock_provider)
    
    results = router.send_all(
        mock_reminder,
        channels=["ntfy"],
        title="Test",
        body="Test body",
    )
    
    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].provider == "ntfy"
    
    mock_provider.send.assert_called_once()


def test_notification_router_multi_channel(mock_reminder):
    """Test router with multiple channels."""
    mock_ntfy = Mock()
    mock_ntfy.send.return_value = DeliveryResult(ok=True, provider="ntfy")
    
    mock_voice = Mock()
    mock_voice.send.return_value = DeliveryResult(ok=False, provider="voice", error="not implemented")
    
    router = NotificationRouter()
    router.register_provider("ntfy", mock_ntfy)
    router.register_provider("voice", mock_voice)
    
    results = router.send_all(
        mock_reminder,
        channels=["ntfy", "voice"],
    )
    
    assert len(results) == 2
    assert results[0].ok is True
    assert results[0].provider == "ntfy"
    assert results[1].ok is False
    assert results[1].provider == "voice"


def test_notification_router_unknown_channel(mock_reminder):
    """Test router with unknown channel."""
    router = NotificationRouter()
    
    results = router.send_all(
        mock_reminder,
        channels=["unknown_channel"],
    )
    
    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].provider == "unknown_channel"
    assert "Unknown channel" in results[0].error


def test_notification_router_exception_handling(mock_reminder):
    """Test router handles provider exceptions gracefully."""
    mock_provider = Mock()
    mock_provider.send.side_effect = Exception("Provider crashed")
    
    router = NotificationRouter()
    router.register_provider("ntfy", mock_provider)
    
    results = router.send_all(
        mock_reminder,
        channels=["ntfy"],
    )
    
    assert len(results) == 1
    assert results[0].ok is False
    assert "Provider crashed" in results[0].error


@patch.dict("os.environ", {"NTFY_TOPIC": "my-topic"})
def test_create_default_router_with_ntfy():
    """Test default router creation with NTFY_TOPIC set."""
    router = create_default_router()
    
    assert "ntfy" in router.providers
    assert "voice" in router.providers
    assert "desktop_popup" in router.providers


@patch.dict("os.environ", {}, clear=True)
def test_create_default_router_without_ntfy():
    """Test default router creation without NTFY_TOPIC."""
    router = create_default_router()
    
    # ntfy provider should not be registered without topic
    assert "ntfy" not in router.providers
    assert "voice" in router.providers
    assert "desktop_popup" in router.providers


@patch.dict("os.environ", {
    "NTFY_TOPIC": "test",
    "MILTON_PUBLIC_BASE_URL": "https://milton.example.com",
    "MILTON_ACTION_TOKEN": "secret",
})
def test_create_default_router_with_actions():
    """Test default router with action button config."""
    router = create_default_router()
    
    assert "ntfy" in router.providers
    ntfy = router.providers["ntfy"]
    assert isinstance(ntfy, NtfyProvider)
    assert ntfy.public_base_url == "https://milton.example.com"
    assert ntfy.action_token == "secret"
