"""Integration modules package."""
from .weather import WeatherAPI
from .arxiv_api import ArxivAPI
from .home_assistant import HomeAssistantAPI
from .news_api import NewsAPI
from .calendar import CalendarAPI

__all__ = [
    "WeatherAPI",
    "ArxivAPI",
    "HomeAssistantAPI",
    "NewsAPI",
    "CalendarAPI",
]
