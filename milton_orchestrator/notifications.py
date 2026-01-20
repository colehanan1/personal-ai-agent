"""Multi-channel notification delivery system for Milton reminders.

Provides a provider-based architecture for sending reminders through different
channels (ntfy, voice, desktop popups, etc.) with unified delivery tracking.
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

import requests

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    """Result of a notification delivery attempt."""
    
    ok: bool
    provider: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time()))
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dict for audit logging."""
        return {
            "ok": self.ok,
            "provider": self.provider,
            "message_id": self.message_id,
            "error": self.error,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class NotificationProvider(Protocol):
    """Protocol for notification delivery providers."""
    
    @property
    def name(self) -> str:
        """Provider identifier (e.g., 'ntfy', 'voice')."""
        ...
    
    def send(
        self,
        reminder,  # Reminder type from reminders.py
        *,
        title: str,
        body: str,
        actions: list[str],
        context: Optional[dict] = None,
    ) -> DeliveryResult:
        """Send a notification through this provider.
        
        Args:
            reminder: The Reminder object being sent
            title: Notification title
            body: Notification body/message
            actions: List of action button labels (e.g., ["DONE", "SNOOZE_30"])
            context: Additional context for rendering (optional)
            
        Returns:
            DeliveryResult with outcome and metadata
        """
        ...


class NtfyProvider:
    """Ntfy.sh notification provider with action button support."""
    
    def __init__(
        self,
        base_url: str,
        topic: str,
        public_base_url: Optional[str] = None,
        action_token: Optional[str] = None,
    ):
        """Initialize ntfy provider.
        
        Args:
            base_url: Ntfy server base URL (e.g., https://ntfy.sh)
            topic: Topic to publish to
            public_base_url: Public URL for action callbacks (e.g., https://milton.example.com)
            action_token: Optional bearer token for action authentication
        """
        self.base_url = base_url.rstrip('/')
        self.topic = topic
        self.public_base_url = public_base_url.rstrip('/') if public_base_url else None
        self.action_token = action_token
    
    @property
    def name(self) -> str:
        return "ntfy"
    
    def send(
        self,
        reminder,
        *,
        title: str,
        body: str,
        actions: list[str],
        context: Optional[dict] = None,
    ) -> DeliveryResult:
        """Send notification via ntfy with action buttons."""
        from milton_orchestrator.reminders import format_timestamp_local
        
        # Format timestamp in reminder's timezone
        due_str = format_timestamp_local(reminder.due_at, reminder.timezone)
        
        # Build message body
        action_labels = " | ".join(actions)
        full_body = f"""{body}

Due: {due_str}
ID: {reminder.id}
Actions: {action_labels}"""
        
        # Priority mapping: high→5, med→3, low→2
        priority_map = {"high": 5, "med": 3, "low": 2}
        priority = priority_map.get(reminder.priority, 3)
        
        # Build headers
        headers = {
            "Title": title,
            "Priority": str(priority),
        }
        
        # Add action buttons if public_base_url is configured
        if self.public_base_url and actions:
            action_parts = []
            for action in actions:
                action_url = f"{self.public_base_url}/api/reminders/{reminder.id}/action"
                action_body_dict = {"action": action}
                
                # Add auth token to request body if configured
                if self.action_token:
                    action_body_dict["token"] = self.action_token
                
                action_body = json.dumps(action_body_dict)
                # ntfy action format: http, Label, POST, URL, body='{"key":"value"}'
                action_parts.append(f"http, {action}, POST, {action_url}, body='{action_body}'")
            
            headers["Actions"] = "; ".join(action_parts)
        
        # Publish to ntfy
        url = f"{self.base_url}/{self.topic}"
        
        try:
            response = requests.post(
                url,
                data=full_body.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
            
            message_id = None
            # Try to extract message ID from response
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    message_id = response_data.get("id")
                except Exception:
                    pass
            
            return DeliveryResult(
                ok=response.status_code == 200,
                provider=self.name,
                message_id=message_id,
                error=None if response.status_code == 200 else f"HTTP {response.status_code}",
                metadata={
                    "status_code": response.status_code,
                    "url": url,
                    "has_actions": bool(self.public_base_url and actions),
                },
            )
        
        except Exception as exc:
            error_msg = str(exc)[:200]
            logger.error(f"Ntfy delivery failed: {exc}")
            return DeliveryResult(
                ok=False,
                provider=self.name,
                error=error_msg,
                metadata={"url": url, "exception_type": type(exc).__name__},
            )


class VoiceProvider:
    """Voice notification provider (stub implementation)."""
    
    @property
    def name(self) -> str:
        return "voice"
    
    def send(
        self,
        reminder,
        *,
        title: str,
        body: str,
        actions: list[str],
        context: Optional[dict] = None,
    ) -> DeliveryResult:
        """Voice delivery not yet implemented."""
        logger.info(f"Voice notification stub called for reminder {reminder.id}")
        return DeliveryResult(
            ok=False,
            provider=self.name,
            error="Voice notifications not yet implemented",
            metadata={"stub": True},
        )


class DesktopPopupProvider:
    """Desktop popup notification provider (stub implementation)."""
    
    @property
    def name(self) -> str:
        return "desktop_popup"
    
    def send(
        self,
        reminder,
        *,
        title: str,
        body: str,
        actions: list[str],
        context: Optional[dict] = None,
    ) -> DeliveryResult:
        """Desktop popup delivery not yet implemented."""
        logger.info(f"Desktop popup notification stub called for reminder {reminder.id}")
        return DeliveryResult(
            ok=False,
            provider=self.name,
            error="Desktop popup notifications not yet implemented",
            metadata={"stub": True},
        )


class NotificationRouter:
    """Routes reminders to multiple notification providers."""
    
    def __init__(self, providers: Optional[dict[str, NotificationProvider]] = None):
        """Initialize router with provider registry.
        
        Args:
            providers: Dict mapping channel name to provider instance
        """
        self.providers = providers or {}
    
    def register_provider(self, channel: str, provider: NotificationProvider) -> None:
        """Register a provider for a channel."""
        self.providers[channel] = provider
    
    def send_all(
        self,
        reminder,
        channels: list[str],
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> list[DeliveryResult]:
        """Send notification through all specified channels.
        
        Args:
            reminder: Reminder object to send
            channels: List of channel names (e.g., ["ntfy", "voice"])
            title: Optional title override
            body: Optional body override
            
        Returns:
            List of DeliveryResult for each channel attempt
        """
        if not title:
            title = f"Milton Reminder ({reminder.kind})"
        if not body:
            body = reminder.message
        
        # Get actions from reminder
        actions = reminder.actions if hasattr(reminder, 'actions') else []
        
        results = []
        
        for channel in channels:
            provider = self.providers.get(channel)
            
            if provider is None:
                # Unknown channel - log and skip
                logger.warning(f"No provider registered for channel '{channel}' (reminder {reminder.id})")
                results.append(DeliveryResult(
                    ok=False,
                    provider=channel,
                    error=f"Unknown channel '{channel}'",
                    metadata={"skipped": True},
                ))
                continue
            
            try:
                result = provider.send(
                    reminder,
                    title=title,
                    body=body,
                    actions=actions,
                )
                results.append(result)
                
                if result.ok:
                    logger.info(f"Delivered reminder {reminder.id} via {channel}")
                else:
                    logger.warning(f"Failed to deliver reminder {reminder.id} via {channel}: {result.error}")
            
            except Exception as exc:
                logger.error(f"Exception delivering reminder {reminder.id} via {channel}: {exc}", exc_info=True)
                results.append(DeliveryResult(
                    ok=False,
                    provider=channel,
                    error=f"Exception: {str(exc)[:200]}",
                    metadata={"exception_type": type(exc).__name__},
                ))
        
        return results


def create_default_router(
    ntfy_base_url: Optional[str] = None,
    ntfy_topic: Optional[str] = None,
    public_base_url: Optional[str] = None,
    action_token: Optional[str] = None,
) -> NotificationRouter:
    """Create a router with default providers configured from environment.
    
    Args:
        ntfy_base_url: Override for NTFY_BASE_URL env var
        ntfy_topic: Override for NTFY_TOPIC env var
        public_base_url: Override for MILTON_PUBLIC_BASE_URL env var
        action_token: Override for MILTON_ACTION_TOKEN env var
        
    Returns:
        Configured NotificationRouter instance
    """
    router = NotificationRouter()
    
    # Configure ntfy provider if we have required settings
    base_url = ntfy_base_url or os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
    topic = ntfy_topic or os.getenv("NTFY_TOPIC")
    public_url = public_base_url or os.getenv("MILTON_PUBLIC_BASE_URL")
    token = action_token or os.getenv("MILTON_ACTION_TOKEN")
    
    if topic:
        ntfy_provider = NtfyProvider(
            base_url=base_url,
            topic=topic,
            public_base_url=public_url,
            action_token=token,
        )
        router.register_provider("ntfy", ntfy_provider)
        logger.info(f"Registered ntfy provider (topic={topic}, actions={'enabled' if public_url else 'disabled'})")
    else:
        logger.warning("NTFY_TOPIC not set, ntfy notifications will not be available")
    
    # Register stub providers
    router.register_provider("voice", VoiceProvider())
    router.register_provider("desktop_popup", DesktopPopupProvider())
    
    # "both" is a legacy alias for ["ntfy", "voice"]
    # We handle this at the channel parsing level in reminders.py
    
    return router
