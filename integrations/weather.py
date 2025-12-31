# agent_system/integrations/weather.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root by default

class WeatherAPI:
    def __init__(self):
        self.api_key = os.getenv("WEATHER_API_KEY")
        self.location = os.getenv("WEATHER_LOCATION", "St. Louis,US")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def current_weather(self):
        """Return dict with temp, condition, high, low, humidity, location."""
        if not self.api_key:
            raise RuntimeError("WEATHER_API_KEY not set in environment")

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

