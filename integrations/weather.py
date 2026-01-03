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


def _parse_lat_lon(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _format_location_name(result: dict) -> str:
    parts = [result.get("name"), result.get("state"), result.get("country")]
    return ", ".join(part for part in parts if part)


class WeatherAPI:
    def __init__(self):
        self.api_key = _resolve_api_key()
        self.location = os.getenv("WEATHER_LOCATION")
        self.lat = os.getenv("WEATHER_LAT")
        self.lon = os.getenv("WEATHER_LON")
        self.base_url = "https://api.openweathermap.org/data/3.0/onecall"
        self.geo_url = "https://api.openweathermap.org/geo/1.0/direct"

    def _get_coordinates(self) -> tuple[float, float, str]:
        if self.lat and self.lon:
            try:
                lat = float(self.lat)
                lon = float(self.lon)
            except ValueError as exc:
                raise RuntimeError("WEATHER_LAT/WEATHER_LON must be valid numbers") from exc
            display = self.location or f"{lat},{lon}"
            return lat, lon, display

        location = self.location or "St. Louis,US"

        parsed = _parse_lat_lon(location)
        if parsed:
            lat, lon = parsed
            return lat, lon, location

        params = {
            "q": location,
            "limit": 1,
            "appid": self.api_key,
        }
        resp = requests.get(self.geo_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            raise RuntimeError(f"Location not found: {location}")
        result = data[0]
        lat = result["lat"]
        lon = result["lon"]
        display = _format_location_name(result) or location
        return lat, lon, display

    def current_weather(self):
        """Return dict with temp, condition, high, low, humidity, location."""
        if not self.api_key:
            raise RuntimeError(
                "OPENWEATHER_API_KEY not set in environment "
                "(WEATHER_API_KEY supported for backward compatibility)"
            )

        lat, lon, display_location = self._get_coordinates()
        params = {
            "lat": lat,
            "lon": lon,
            "exclude": "minutely,hourly,alerts",
            "appid": self.api_key,
            "units": "imperial",  # F for US
        }
        resp = requests.get(self.base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data["current"]
        daily = data.get("daily", [])
        temps = daily[0].get("temp", {}) if daily else {}
        high = temps.get("max", current["temp"])
        low = temps.get("min", current["temp"])

        return {
            "temp": current["temp"],
            "condition": current["weather"][0]["main"],
            "humidity": current["humidity"],
            "high": high,
            "low": low,
            "location": display_location,  # Added for tests
        }
