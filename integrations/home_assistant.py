"""
Home Assistant Integration
Provides API access to Home Assistant for device control and state queries.
"""
import requests
from typing import Dict, Any, Optional, List
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)


class HomeAssistantAPI:
    """Interface to Home Assistant REST API."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        """
        Initialize Home Assistant API client.

        Args:
            url: Home Assistant URL (defaults to env var)
            token: Long-lived access token (defaults to env var)
        """
        self.url = (url or os.getenv("HOME_ASSISTANT_URL", "")).rstrip("/")
        self.token = token or os.getenv("HOME_ASSISTANT_TOKEN", "")

        if not self.url or not self.token:
            logger.warning(
                "Home Assistant URL or token not configured. "
                "Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN environment variables."
            )

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Home Assistant API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request payload (optional)

        Returns:
            Response data

        Raises:
            requests.RequestException: On API error
        """
        url = f"{self.url}/api/{endpoint}"

        try:
            response = requests.request(
                method, url, headers=self.headers, json=data, timeout=10
            )
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.RequestException as e:
            logger.error(f"Home Assistant API error: {e}")
            raise

    def get_state(self, entity_id: str) -> Dict[str, Any]:
        """
        Get state of an entity.

        Args:
            entity_id: Entity ID (e.g., "light.living_room")

        Returns:
            Entity state data including attributes

        Example:
            >>> ha = HomeAssistantAPI()
            >>> state = ha.get_state("light.living_room")
            >>> print(state["state"])  # "on" or "off"
        """
        return self._request("GET", f"states/{entity_id}")

    def get_all_states(self) -> List[Dict[str, Any]]:
        """
        Get states of all entities.

        Returns:
            List of all entity states
        """
        return self._request("GET", "states")

    def call_service(
        self, domain: str, service: str, service_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a Home Assistant service.

        Args:
            domain: Service domain (e.g., "light", "switch")
            service: Service name (e.g., "turn_on", "toggle")
            service_data: Service data including entity_id

        Returns:
            Response data

        Example:
            >>> ha = HomeAssistantAPI()
            >>> ha.call_service("light", "turn_on", {
            ...     "entity_id": "light.living_room",
            ...     "brightness": 200
            ... })
        """
        return self._request("POST", f"services/{domain}/{service}", service_data)

    # === Convenience Methods ===

    def turn_on_light(
        self,
        entity_id: str,
        brightness: Optional[int] = None,
        color_temp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Turn on a light with optional brightness and color temperature.

        Args:
            entity_id: Light entity ID
            brightness: Brightness (0-255)
            color_temp: Color temperature in mireds

        Returns:
            Response data
        """
        data = {"entity_id": entity_id}

        if brightness is not None:
            data["brightness"] = brightness

        if color_temp is not None:
            data["color_temp"] = color_temp

        return self.call_service("light", "turn_on", data)

    def turn_off_light(self, entity_id: str) -> Dict[str, Any]:
        """
        Turn off a light.

        Args:
            entity_id: Light entity ID

        Returns:
            Response data
        """
        return self.call_service("light", "turn_off", {"entity_id": entity_id})

    def turn_on_switch(self, entity_id: str) -> Dict[str, Any]:
        """
        Turn on a switch or plug.

        Args:
            entity_id: Switch entity ID

        Returns:
            Response data
        """
        return self.call_service("switch", "turn_on", {"entity_id": entity_id})

    def turn_off_switch(self, entity_id: str) -> Dict[str, Any]:
        """
        Turn off a switch or plug.

        Args:
            entity_id: Switch entity ID

        Returns:
            Response data
        """
        return self.call_service("switch", "turn_off", {"entity_id": entity_id})

    def set_thermostat(
        self,
        entity_id: str,
        temperature: float,
        hvac_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Set thermostat temperature and mode.

        Args:
            entity_id: Climate entity ID
            temperature: Target temperature
            hvac_mode: HVAC mode (heat, cool, auto, off)

        Returns:
            Response data
        """
        data = {"entity_id": entity_id, "temperature": temperature}

        if hvac_mode:
            self.call_service(
                "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": hvac_mode}
            )

        return self.call_service("climate", "set_temperature", data)

    def get_temperature(self, entity_id: str) -> Optional[float]:
        """
        Get current temperature from a sensor.

        Args:
            entity_id: Temperature sensor entity ID

        Returns:
            Current temperature or None
        """
        try:
            state = self.get_state(entity_id)
            return float(state["state"])
        except (ValueError, KeyError):
            return None

    def is_on(self, entity_id: str) -> bool:
        """
        Check if a device is on.

        Args:
            entity_id: Entity ID

        Returns:
            True if device is on, False otherwise
        """
        try:
            state = self.get_state(entity_id)
            return state["state"].lower() == "on"
        except Exception:
            return False

    def get_entities_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """
        Get all entities for a specific domain.

        Args:
            domain: Domain (e.g., "light", "switch", "sensor")

        Returns:
            List of entities in domain
        """
        all_states = self.get_all_states()
        return [s for s in all_states if s["entity_id"].startswith(f"{domain}.")]


if __name__ == "__main__":
    # Simple test
    ha = HomeAssistantAPI()
    print("Home Assistant API initialized")
    print(f"URL: {ha.url}")
