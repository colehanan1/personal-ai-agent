"""
News API Integration
Fetch news articles from NewsAPI.org
"""
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)


class NewsAPI:
    """Interface to NewsAPI.org."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize News API client.

        Args:
            api_key: NewsAPI key (defaults to env var)
        """
        self.api_key = api_key or os.getenv("NEWS_API_KEY", "")

        if not self.api_key:
            logger.warning(
                "News API key not configured. " "Set NEWS_API_KEY environment variable."
            )

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make HTTP request to News API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response data

        Raises:
            requests.RequestException: On API error
        """
        params["apiKey"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"News API error: {e}")
            raise

    def get_top_headlines(
        self,
        country: str = "us",
        category: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get top headlines.

        Args:
            country: Country code (us, gb, etc.)
            category: Category (business, technology, science, health, etc.)
            max_results: Maximum number of articles

        Returns:
            List of news articles

        Example:
            >>> news = NewsAPI()
            >>> headlines = news.get_top_headlines(category="technology", max_results=5)
        """
        params = {"country": country, "pageSize": max_results}

        if category:
            params["category"] = category

        data = self._request("top-headlines", params)

        return [self._format_article(article) for article in data.get("articles", [])]

    def search_news(
        self,
        query: str,
        from_date: Optional[str] = None,
        max_results: int = 10,
        sort_by: str = "publishedAt",
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles.

        Args:
            query: Search query
            from_date: Start date (YYYY-MM-DD format)
            max_results: Maximum results
            sort_by: Sort by (publishedAt, relevancy, popularity)

        Returns:
            List of news articles

        Example:
            >>> news = NewsAPI()
            >>> articles = news.search_news("artificial intelligence", max_results=5)
        """
        params = {
            "q": query,
            "pageSize": max_results,
            "sortBy": sort_by,
            "language": "en",
        }

        if from_date:
            params["from"] = from_date

        data = self._request("everything", params)

        return [self._format_article(article) for article in data.get("articles", [])]

    def get_recent_news(
        self, query: str, days: int = 7, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent news for a query.

        Args:
            query: Search query
            days: Number of days back to search
            max_results: Maximum results

        Returns:
            List of recent news articles
        """
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        return self.search_news(query, from_date=from_date, max_results=max_results)

    def _format_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format article data.

        Args:
            article: Raw article data

        Returns:
            Formatted article
        """
        return {
            "title": article.get("title", ""),
            "description": article.get("description", ""),
            "url": article.get("url", ""),
            "source": article.get("source", {}).get("name", ""),
            "author": article.get("author", ""),
            "published_at": article.get("publishedAt", ""),
            "image_url": article.get("urlToImage", ""),
        }

    def format_article_text(self, article: Dict[str, Any]) -> str:
        """
        Format article as readable text.

        Args:
            article: Article dictionary

        Returns:
            Formatted string
        """
        published = article["published_at"].split("T")[0] if article["published_at"] else "Unknown"

        return (
            f"{article['title']}\n"
            f"Source: {article['source']} | Published: {published}\n"
            f"{article['description']}\n"
            f"URL: {article['url']}\n"
        )

    def generate_brief(
        self, articles: List[Dict[str, Any]], topic: Optional[str] = None
    ) -> str:
        """
        Generate a brief summary of news articles.

        Args:
            articles: List of articles
            topic: Optional topic description

        Returns:
            Formatted brief
        """
        header = f"News"
        if topic:
            header += f": {topic}"

        header += f" ({len(articles)} articles)\n"
        header += "=" * 70 + "\n\n"

        summaries = []
        for i, article in enumerate(articles, 1):
            published = (
                article["published_at"].split("T")[0]
                if article["published_at"]
                else "Unknown"
            )

            summary = (
                f"{i}. {article['title']}\n"
                f"   Source: {article['source']} | {published}\n"
                f"   {article['description'][:150]}...\n"
            )
            summaries.append(summary)

        return header + "\n".join(summaries)


if __name__ == "__main__":
    # Simple test
    news = NewsAPI()
    print("News API initialized")
