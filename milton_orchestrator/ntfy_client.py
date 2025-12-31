"""ntfy client for subscribing and publishing messages"""

import json
import logging
import time
from typing import Iterator, Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class NtfyMessage:
    """Represents a parsed ntfy message"""

    def __init__(self, raw_data: Dict[str, Any]):
        self.raw = raw_data
        self.event = raw_data.get("event", "")
        self.message = raw_data.get("message", "")
        self.id = raw_data.get("id", "")
        self.time = raw_data.get("time", 0)
        self.topic = raw_data.get("topic", "")

    def is_message_event(self) -> bool:
        """Check if this is a message event (not keepalive or open)"""
        return self.event == "message"

    def __repr__(self) -> str:
        return f"NtfyMessage(id={self.id}, event={self.event}, message={self.message[:50]}...)"


class NtfyClient:
    """Client for ntfy.sh service"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "milton-orchestrator/1.0"})

    def subscribe(
        self, topic: str, timeout: int = 300
    ) -> Iterator[NtfyMessage]:
        """
        Subscribe to a topic and yield messages.

        Args:
            topic: The topic to subscribe to
            timeout: Timeout for each streaming chunk read

        Yields:
            NtfyMessage objects for each event
        """
        url = f"{self.base_url}/{topic}/json"
        logger.info(f"Subscribing to ntfy topic: {topic} at {url}")

        try:
            response = self.session.get(url, stream=True, timeout=timeout)
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    msg = NtfyMessage(data)
                    logger.debug(f"Received ntfy event: {msg}")
                    yield msg
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse ntfy message: {line[:100]}... Error: {e}")
                    continue

        except requests.exceptions.RequestException as e:
            logger.error(f"ntfy subscription error: {e}")
            raise

    def publish(self, topic: str, message: str, title: Optional[str] = None, priority: int = 3) -> bool:
        """
        Publish a message to a topic.

        Args:
            topic: The topic to publish to
            message: The message body
            title: Optional message title
            priority: Message priority (1-5, default 3)

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/{topic}"

        headers = {
            "Priority": str(priority),
        }
        if title:
            headers["Title"] = title

        try:
            response = self.session.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            logger.info(f"Published to {topic}: {message[:100]}...")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    def close(self):
        """Close the session"""
        self.session.close()


def subscribe_with_reconnect(
    client: NtfyClient,
    topic: str,
    max_backoff: int = 300,
) -> Iterator[NtfyMessage]:
    """
    Subscribe with automatic reconnection and exponential backoff.

    Args:
        client: NtfyClient instance
        topic: Topic to subscribe to
        max_backoff: Maximum backoff time in seconds

    Yields:
        NtfyMessage objects
    """
    backoff = 1
    consecutive_errors = 0

    while True:
        try:
            for msg in client.subscribe(topic):
                yield msg
                # Reset backoff on successful message
                backoff = 1
                consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            logger.warning(
                f"ntfy subscription interrupted (error #{consecutive_errors}): {e}. "
                f"Reconnecting in {backoff}s..."
            )
            time.sleep(backoff)

            # Exponential backoff with max
            backoff = min(backoff * 2, max_backoff)

            # If too many consecutive errors, something might be seriously wrong
            if consecutive_errors >= 10:
                logger.error("Too many consecutive ntfy errors. Raising exception.")
                raise
