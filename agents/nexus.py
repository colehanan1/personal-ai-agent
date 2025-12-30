"""
NEXUS - Orchestration Hub
Coordinates between agents, generates briefings, and routes requests.
"""
import requests
from typing import Dict, Any, Optional, List
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging
import sys

from integrations import HomeAssistantAPI, WeatherAPI, ArxivAPI, NewsAPI, CalendarAPI

load_dotenv()

logger = logging.getLogger(__name__)


class NEXUS:
    """
    NEXUS orchestration agent.

    Responsibilities:
    - Route user requests to appropriate agents
    - Generate morning and evening briefings
    - Coordinate between CORTEX and FRONTIER
    - Maintain conversational context
    - Handle bedtime routine
    """

    def __init__(
        self,
        model_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize NEXUS agent.

        Args:
            model_url: vLLM API URL (defaults to env var)
            model_name: Model name (defaults to env var)
        """
        self.model_url = (
            model_url or os.getenv("OLLAMA_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.model_name = os.getenv(
            "OLLAMA_MODEL", "meta-llama/Llama-3.1-405B-Instruct"
        )
        self.system_prompt = self._load_system_prompt()

        # Initialize integrations
        self.home_assistant = HomeAssistantAPI()
        self.weather = WeatherAPI()
        self.arxiv = ArxivAPI()  # Note: Milton uses ArxivAPI not ArXivAPI
        self.news = NewsAPI()
        self.calendar = CalendarAPI()

        logger.info("NEXUS agent initialized")

    def _load_system_prompt(self) -> str:
        """Load NEXUS system prompt from Prompts folder."""
        from agents import load_agent_context
        return load_agent_context("NEXUS")

    def _call_llm(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000
    ) -> str:
        """Call vLLM API for inference."""
        url = f"{self.model_url}/v1/chat/completions"

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise

    def route_request(self, user_input: str) -> Dict[str, Any]:
        """
        Route user request to appropriate agent or integration.

        Args:
            user_input: User's input

        Returns:
            Routing decision with target agent and context
        """
        prompt = f"""
Analyze the following user request and determine how to route it:

User request: {user_input}

Available options:
1. CORTEX - For execution tasks (data analysis, code generation, overnight jobs)
2. FRONTIER - For research and discovery (papers, news, monitoring)
3. Direct integration - For simple queries (weather, home control, calendar)
4. NEXUS (self) - For conversation and general assistance

Respond with JSON:
{{
    "target": "CORTEX|FRONTIER|integration_name|NEXUS",
    "reasoning": "explanation",
    "context": {{"any": "relevant context"}}
}}
"""

        response = self._call_llm(prompt, system_prompt=self.system_prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            routing = json.loads(response[json_start:json_end])
        except Exception as e:
            logger.error(f"Failed to parse routing decision: {e}")
            routing = {"target": "NEXUS", "reasoning": "Unable to parse routing"}

        return routing

    def generate_morning_briefing(self) -> str:
        """
        Generate morning briefing with weather, news, calendar, and home status.

        Returns:
            Formatted morning briefing
        """
        logger.info("Generating morning briefing")

        sections = []

        # Header
        now = datetime.now()
        sections.append(f"Good morning, Cole! {now.strftime('%A, %B %d, %Y')}\n")
        sections.append("=" * 70 + "\n")

        # Weather
        try:
            weather_info = self.weather.format_current_weather()
            sections.append(f"\nWEATHER\n{weather_info}\n")
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            sections.append("\nWEATHER\nUnavailable\n")

        # Calendar (stub)
        sections.append("\nTODAY'S SCHEDULE\n")
        try:
            events = self.calendar.get_today_events()
            if events:
                sections.append(self.calendar.format_events(events))
            else:
                sections.append("No scheduled events\n")
        except Exception as e:
            sections.append("Calendar unavailable (stub implementation)\n")

        # News highlights
        sections.append("\nNEWS HIGHLIGHTS\n")
        try:
            headlines = self.news.get_top_headlines(category="technology", max_results=3)
            for i, article in enumerate(headlines, 1):
                sections.append(f"{i}. {article['title']} ({article['source']})\n")
        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            sections.append("News unavailable\n")

        # Home status (if configured)
        sections.append("\nHOME STATUS\n")
        try:
            # Example: Check a temperature sensor
            # Replace with actual entity IDs
            sections.append("Home Assistant integration ready\n")
        except Exception:
            sections.append("Home Assistant unavailable\n")

        sections.append("\n" + "=" * 70)

        return "\n".join(sections)

    def generate_evening_briefing(self) -> str:
        """
        Generate evening briefing with day summary and overnight tasks.

        Returns:
            Formatted evening briefing
        """
        logger.info("Generating evening briefing")

        sections = []

        # Header
        sections.append(f"Evening briefing - {datetime.now().strftime('%A, %B %d')}\n")
        sections.append("=" * 70 + "\n")

        # Summary of day
        sections.append("\nDAY SUMMARY\n")
        sections.append("Tasks completed today: [To be implemented with memory system]\n")

        # Overnight queue status
        sections.append("\nOVERNIGHT QUEUE\n")
        sections.append("Scheduled jobs: [To be implemented with job queue]\n")

        # Tomorrow preview
        sections.append("\nTOMORROW\n")
        try:
            weather = self.weather.forecast(days=1)
            if weather and weather.get("days"):
                day = weather["days"][0]
                sections.append(
                    f"Weather: High {day['high']}°F, Low {day['low']}°F, {day['condition']}\n"
                )
        except Exception:
            sections.append("Weather forecast unavailable\n")

        sections.append("\n" + "=" * 70)

        return "\n".join(sections)

    def handle_bedtime(self, tasks: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Handle bedtime routine: queue overnight tasks, generate briefing.

        Args:
            tasks: List of tasks to queue for overnight processing

        Returns:
            Bedtime summary
        """
        logger.info("Handling bedtime routine")

        # Generate evening briefing
        briefing = self.generate_evening_briefing()

        # Queue tasks (placeholder)
        queued_tasks = tasks or []

        # Save briefing to inbox
        briefing_path = os.path.expanduser(
            f"~/agent-system/inbox/evening/briefing_{datetime.now().strftime('%Y%m%d')}.txt"
        )

        try:
            os.makedirs(os.path.dirname(briefing_path), exist_ok=True)
            with open(briefing_path, "w") as f:
                f.write(briefing)
        except Exception as e:
            logger.error(f"Failed to save briefing: {e}")

        return {
            "briefing": briefing,
            "queued_tasks": queued_tasks,
            "briefing_saved": briefing_path,
        }

    def process_message(self, message: str) -> str:
        """
        Process a message from Cole.

        Args:
            message: User message

        Returns:
            Response
        """
        # Route to determine handling
        routing = self.route_request(message)

        if routing["target"] == "NEXUS":
            # Handle directly
            response = self._call_llm(message, system_prompt=self.system_prompt)
            return response
        else:
            # Delegate to other agent/integration
            return f"Routing to {routing['target']}: {routing['reasoning']}"


if __name__ == "__main__":
    # Simple test
    nexus = NEXUS()
    print("NEXUS agent initialized")
    print("\nGenerating morning briefing...\n")
    print(nexus.generate_morning_briefing())
