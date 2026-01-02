# milton/integrations/weather.py
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root by default

logger = logging.getLogger(__name__)
_LEGACY_KEY_WARNING_EMITTED = False


def _resolve_api_key() -> str | None:
    global _LEGACY_KEY_WARNING_EMITTED
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if api_key:
        return api_key

    legacy_key = os.getenv("WEATHER_API_KEY")
    if legacy_key and not _LEGACY_KEY_WARNING_EMITTED:
        logger.warning(
            "WEATHER_API_KEY is deprecated; use OPENWEATHER_API_KEY. "
            "Falling back to WEATHER_API_KEY for backward compatibility."
        )
        _LEGACY_KEY_WARNING_EMITTED = True
    return legacy_key


class WeatherAPI:
    def __init__(self):
        self.api_key = _resolve_api_key()
        self.location = os.getenv("WEATHER_LOCATION", "St. Louis,US")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def current_weather(self):
        """Return dict with temp, condition, high, low, humidity, location."""
        if not self.api_key:
            raise RuntimeError(
                "OPENWEATHER_API_KEY not set in environment "
                "(WEATHER_API_KEY supported for backward compatibility)"
            )

        params = {
            "q": self.location,
            "appid": self.api_key,
            "units": "imperial",  # F for US
        }
        resp = requests.get(self.base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        return {
            "temp": data["main"]["temp"],
            "condition": data["weather"][0]["main"],
            "humidity": data["main"]["humidity"],
            "high": data["main"]["temp_max"],
            "low": data["main"]["temp_min"],
            "location": self.location,  # Added for tests
        }
