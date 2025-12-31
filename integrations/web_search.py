"""Lightweight web search integration with pluggable providers."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse
import logging
import os
import re
import html

import requests

logger = logging.getLogger(__name__)


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.results: List[Dict[str, str]] = []
        self._current: Optional[Dict[str, str]] = None
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "")

        if tag == "a" and "result__a" in class_attr:
            if self._current and len(self.results) < self.limit:
                self.results.append(self._current)
            self._current = {
                "title": "",
                "url": _clean_ddg_url(attrs_dict.get("href", "")),
                "snippet": "",
            }
            self._in_title = True
            return

        if "result__snippet" in class_attr:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_snippet and tag in {"a", "div", "span"}:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if not self._current:
            return
        if self._in_title:
            self._current["title"] += data
        elif self._in_snippet:
            self._current["snippet"] += data

    def finalize(self) -> None:
        if self._current and len(self.results) < self.limit:
            self.results.append(self._current)


def _clean_ddg_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
    return raw_url


class WebSearchAPI:
    def __init__(self, timeout: float = 12.0, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.serper_key = os.getenv("SERPER_API_KEY")
        self.brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
        self.tavily_key = os.getenv("TAVILY_API_KEY")

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not query:
            return []
        if self.serper_key:
            return self._search_serper(query, max_results)
        if self.brave_key:
            return self._search_brave(query, max_results)
        if self.tavily_key:
            return self._search_tavily(query, max_results)

        results = self._search_wikipedia(query, max_results)
        if results:
            return results

        try:
            return self._search_duckduckgo_html(query, max_results)
        except Exception as exc:
            logger.warning("Web search request failed: %s", exc)
            return []

    def _search_serper(self, query: str, max_results: int) -> List[Dict[str, str]]:
        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": self.serper_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": max_results},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Serper search failed: %s", exc)
            return []

        results = []
        for item in payload.get("organic", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def _search_brave(self, query: str, max_results: int) -> List[Dict[str, str]]:
        try:
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": self.brave_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Brave search failed: %s", exc)
            return []

        results = []
        for item in payload.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def _search_tavily(self, query: str, max_results: int) -> List[Dict[str, str]]:
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_key,
                    "query": query,
                    "max_results": max_results,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []

        results = []
        for item in payload.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def _search_wikipedia(self, query: str, max_results: int) -> List[Dict[str, str]]:
        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": max_results,
                },
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Wikipedia search failed: %s", exc)
            return []

        results = []
        for item in payload.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = re.sub("<.*?>", "", item.get("snippet", ""))
            results.append(
                {
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": html.unescape(snippet),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def _search_duckduckgo_html(
        self, query: str, max_results: int
    ) -> List[Dict[str, str]]:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        if response.status_code not in (200, 202):
            response.raise_for_status()

        parser = _DuckDuckGoHTMLParser(limit=max_results)
        parser.feed(response.text)
        parser.finalize()

        results: List[Dict[str, str]] = []
        for item in parser.results:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": item.get("snippet", "").strip(),
                }
            )
            if len(results) >= max_results:
                break
        return results
