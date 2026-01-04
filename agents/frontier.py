"""
FRONTIER - Discovery Agent
Monitors research feeds, discovers papers, and generates research briefs.
"""
import requests
from typing import Dict, Any, Optional, List, Tuple
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging
import sys

from milton_orchestrator.state_paths import resolve_state_dir

# Add parent directory to path for imports


from integrations import ArxivAPI, NewsAPI
from agents.memory_hooks import (
    build_memory_context,
    record_memory,
    should_store_responses,
)
from agents.contracts import (
    DiscoveryResult,
    AgentReport,
    generate_task_id,
    generate_iso_timestamp,
)
from agents.frontier_cache import get_discovery_cache

load_dotenv()

logger = logging.getLogger(__name__)


class FRONTIER:
    """
    FRONTIER discovery agent.

    Responsibilities:
    - Monitor arXiv for relevant papers
    - Track AI/ML developments
    - Generate research briefs
    - Identify important publications
    - Curate content for Cole's research interests
    """

    def __init__(
        self,
        model_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize FRONTIER agent.

        Args:
            model_url: vLLM API URL (defaults to env var)
            model_name: Model name (defaults to env var)
        """
        self.model_url = (
            model_url
            or os.getenv("LLM_API_URL")
            or os.getenv("OLLAMA_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.model_name = (
            model_name
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        )
        self.system_prompt = self._load_system_prompt()

        # Initialize integrations
        self.arxiv = ArxivAPI()
        self.news = NewsAPI()

        # Research interests (customizable)
        self.research_interests = [
            "fMRI",
            "brain imaging",
            "neural networks",
            "biomedical engineering",
            "machine learning for neuroscience",
        ]

        logger.info("FRONTIER agent initialized")

    def _load_system_prompt(self) -> str:
        """Load FRONTIER system prompt from Prompts folder."""
        from agents import load_agent_context
        return load_agent_context("FRONTIER")

    def _call_llm(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000
    ) -> str:
        """Call vLLM API for inference."""
        url = f"{self.model_url}/v1/chat/completions"
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        memory_context = build_memory_context("FRONTIER", prompt)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        try:
            response = requests.post(url, json=payload, timeout=120, headers=headers)
            response.raise_for_status()
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            record_memory(
                "FRONTIER",
                prompt,
                memory_type="crumb",
                tags=["request"],
                importance=0.2,
                source="user",
            )
            if should_store_responses():
                record_memory(
                    "FRONTIER",
                    reply,
                    memory_type="crumb",
                    tags=["response"],
                    importance=0.1,
                    source="assistant",
                )
            return reply
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise

    def find_papers(
        self,
        research_topic: str,
        max_results: int = 10,
        categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find papers on arXiv for a research topic.

        Args:
            research_topic: Research topic or keywords
            max_results: Maximum number of papers
            categories: arXiv categories to search (optional)

        Returns:
            List of relevant papers

        Example:
            >>> frontier = FRONTIER()
            >>> papers = frontier.find_papers("fMRI brain connectivity", max_results=5)
        """
        logger.info(f"Searching papers: {research_topic}")

        if categories:
            # Search with category filter
            query = f"({' OR '.join([f'cat:{c}' for c in categories])}) AND all:{research_topic}"
        else:
            # General search
            query = f"all:{research_topic}"

        papers = self.arxiv.search_papers(query, max_results=max_results)

        return papers

    def get_recent_papers_by_interest(
        self, days: int = 7, max_per_interest: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get recent papers for all research interests.

        Args:
            days: Number of days back to search
            max_per_interest: Max papers per interest

        Returns:
            Dictionary mapping interests to papers
        """
        logger.info("Fetching papers for research interests")

        results = {}

        for interest in self.research_interests:
            papers = self.find_papers(interest, max_results=max_per_interest)
            results[interest] = papers

        return results

    def analyze_paper_relevance(
        self, paper: Dict[str, Any], context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze paper relevance to Cole's research.

        Args:
            paper: Paper dictionary from arXiv
            context: Additional context about research goals

        Returns:
            Analysis with relevance score and summary
        """
        context_str = context or "Biomedical engineering, fMRI, brain imaging"

        prompt = f"""
Analyze the relevance of this paper to research in {context_str}:

Title: {paper['title']}
Authors: {', '.join(paper['authors'][:5])}
Abstract: {paper['abstract'][:500]}...

Provide:
1. Relevance score (0-10)
2. Key contributions
3. Why it matters for this research area
4. Recommended action (read, skim, monitor)

Format as JSON.
"""

        response = self._call_llm(prompt, system_prompt=self.system_prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            analysis = json.loads(response[json_start:json_end])
            analysis["paper_id"] = paper.get("id") or paper.get("arxiv_id") or "unknown"
        except Exception as e:
            logger.error(f"Failed to parse analysis: {e}")
            analysis = {
                "relevance_score": 5,
                "error": str(e),
                "paper_id": paper.get("id") or paper.get("arxiv_id") or "unknown",
            }

        return analysis

    def generate_research_brief(
        self,
        papers: List[Dict[str, Any]],
        topic: Optional[str] = None,
        include_analysis: bool = False,
    ) -> Tuple[str, str]:
        """
        Generate research brief from papers.

        Args:
            papers: List of papers
            topic: Topic description
            include_analysis: Whether to include LLM analysis

        Returns:
            Tuple of (formatted research brief, saved file path if write succeeded)
        """
        logger.info(f"Generating research brief for {len(papers)} papers")

        sections = []

        # Header
        header = "FRONTIER Research Brief"
        if topic:
            header += f": {topic}"

        header += f"\n{datetime.now().strftime('%Y-%m-%d')}\n"
        header += "=" * 70 + "\n"

        sections.append(header)

        # Papers
        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "Untitled")
            authors = paper.get("authors") or []
            published = paper.get("published", "")
            paper_id = paper.get("id") or paper.get("arxiv_id") or "unknown"
            pdf_url = paper.get("pdf_url", "unknown")

            section = f"\n{i}. {title}\n"
            section += f"   Authors: {', '.join(authors[:3])}"

            if len(authors) > 3:
                section += f" et al. ({len(authors)} total)"

            published_date = published.split("T")[0] if published else "unknown"
            section += f"\n   Published: {published_date}\n"
            section += f"   arXiv: {paper_id}\n"
            section += f"   PDF: {pdf_url}\n"

            if include_analysis:
                analysis = self.analyze_paper_relevance(paper)
                section += f"   Relevance: {analysis.get('relevance_score', 'N/A')}/10\n"

            sections.append(section)

        # Summary
        if include_analysis:
            summary_prompt = f"""
Summarize the key themes and important findings from these {len(papers)} papers:

{json.dumps([{'title': p['title'], 'abstract': p['abstract'][:200]} for p in papers], indent=2)}

Provide a 2-3 sentence overview of the main trends and breakthroughs.
"""

            try:
                summary = self._call_llm(
                    summary_prompt, system_prompt=self.system_prompt, max_tokens=500
                )
                sections.append(f"\nKEY THEMES\n{summary}\n")
            except Exception as e:
                logger.error(f"Failed to generate summary: {e}")

        sections.append("=" * 70)

        brief = "\n".join(sections)

        # Save to outputs
        output_path = resolve_state_dir() / "outputs" / (
            f"research_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        saved_path: str = ""

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w") as f:
                f.write(brief)
            logger.info(f"Research brief saved to {output_path}")
            saved_path = str(output_path)
        except Exception as e:
            logger.error(f"Failed to save brief: {e}")

        return brief, saved_path

    def monitor_ai_news(self, max_articles: int = 10) -> List[Dict[str, Any]]:
        """
        Monitor AI/ML news and developments.

        Args:
            max_articles: Maximum number of articles

        Returns:
            List of relevant news articles
        """
        logger.info("Monitoring AI/ML news")

        keywords = ["artificial intelligence", "machine learning", "deep learning"]

        articles = []

        for keyword in keywords[:1]:  # Just use first keyword to avoid API limits
            try:
                results = self.news.get_recent_news(
                    keyword, days=3, max_results=max_articles // len(keywords)
                )
                articles.extend(results)
            except Exception as e:
                logger.error(f"News fetch failed for '{keyword}': {e}")

        return articles[:max_articles]

    def find_papers_cached(
        self,
        research_topic: str,
        max_results: int = 10,
        categories: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find papers on arXiv with caching support.

        This method uses a TTL-based cache to provide:
        - Deterministic results (same query returns cached results within TTL)
        - Reduced API calls (local-first principle)
        - Offline capability (works with cached data)

        Args:
            research_topic: Research topic or keywords
            max_results: Maximum number of papers
            categories: arXiv categories to search (optional)
            use_cache: Whether to use cache (default: True)

        Returns:
            List of papers with timestamps

        Example:
            >>> frontier = FRONTIER()
            >>> papers = frontier.find_papers_cached("fMRI", max_results=5)
        """
        cache = get_discovery_cache()

        # Check cache first
        if use_cache:
            params = {"max_results": max_results, "categories": categories or []}
            cached_papers = cache.get("arxiv", research_topic, params)

            if cached_papers is not None:
                logger.info(f"Using cached results for arXiv query: {research_topic}")
                return cached_papers

        # Cache miss or disabled - fetch from API
        logger.info(f"Fetching fresh results from arXiv: {research_topic}")
        papers = self.find_papers(research_topic, max_results, categories)

        # Add retrieval timestamp to each paper
        now = generate_iso_timestamp()
        for paper in papers:
            paper["retrieved_at"] = now

        # Cache results
        if use_cache and papers:
            params = {"max_results": max_results, "categories": categories or []}
            cache.set("arxiv", research_topic, papers, params)

        return papers

    def monitor_ai_news_cached(
        self,
        max_articles: int = 10,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Monitor AI/ML news with caching support.

        Note: This is optional and gracefully degrades if NEWS_API_KEY is not set.

        Args:
            max_articles: Maximum number of articles
            use_cache: Whether to use cache (default: True)

        Returns:
            List of news articles (empty if API key not configured)

        Example:
            >>> frontier = FRONTIER()
            >>> news = frontier.monitor_ai_news_cached(max_articles=5)
            >>> # Returns cached results if available, else fetches (if API key set)
        """
        cache = get_discovery_cache()

        # Check cache first
        if use_cache:
            params = {"max_articles": max_articles}
            cached_news = cache.get("news", "ai_ml_news", params)

            if cached_news is not None:
                logger.info("Using cached AI/ML news")
                return cached_news

        # Cache miss or disabled - check if API key is available
        if not self.news.api_key:
            logger.warning("NEWS_API_KEY not set - skipping news fetch (graceful degradation)")
            return []

        # Fetch from API
        try:
            logger.info("Fetching fresh AI/ML news")
            articles = self.monitor_ai_news(max_articles)

            # Add retrieval timestamp
            now = generate_iso_timestamp()
            for article in articles:
                article["retrieved_at"] = now

            # Cache results
            if use_cache and articles:
                params = {"max_articles": max_articles}
                cache.set("news", "ai_ml_news", articles, params)

            return articles

        except Exception as e:
            logger.error(f"News fetch failed: {e} - returning empty list")
            return []

    def daily_discovery(self) -> DiscoveryResult:
        """
        Run daily discovery routine with caching.

        Uses cached discovery methods to provide deterministic results
        and reduce external API calls. Returns structured DiscoveryResult
        with findings, citations, and source timestamps.

        Returns:
            DiscoveryResult object with papers, news, findings, and metadata

        Example:
            >>> frontier = FRONTIER()
            >>> result = frontier.daily_discovery()
            >>> print(f"Found {len(result.papers)} papers")
            >>> print(f"Confidence: {result.confidence}")
        """
        logger.info("Running daily discovery routine")

        task_id = generate_task_id("discovery")
        now = generate_iso_timestamp()

        # Use cached discovery methods
        all_papers = []
        source_timestamps = {}

        # Get papers for each research interest (with caching)
        for interest in self.research_interests:
            papers = self.find_papers_cached(interest, max_results=3, use_cache=True)
            all_papers.extend(papers)

            # Extract timestamp from first paper in this batch
            if papers and "retrieved_at" in papers[0]:
                source_timestamps[f"arxiv_{interest}"] = papers[0]["retrieved_at"]

        # Get AI news (with caching and graceful degradation)
        news = self.monitor_ai_news_cached(max_articles=5, use_cache=True)
        if news and "retrieved_at" in news[0]:
            source_timestamps["news"] = news[0]["retrieved_at"]

        # Extract citations from papers
        citations = []
        for paper in all_papers:
            arxiv_id = paper.get("id") or paper.get("arxiv_id")
            if arxiv_id:
                citations.append(f"arxiv:{arxiv_id}")
            pdf_url = paper.get("pdf_url")
            if pdf_url:
                citations.append(pdf_url)

        # Add news URLs to citations
        for article in news:
            url = article.get("url")
            if url:
                citations.append(url)

        # Generate findings (bullet points)
        findings = []

        # Group papers by interest for findings
        papers_by_interest = {}
        for interest in self.research_interests:
            interest_papers = [
                p for p in all_papers
                if interest.lower() in p.get("title", "").lower()
                or interest.lower() in p.get("abstract", "").lower()
            ]
            if interest_papers:
                papers_by_interest[interest] = interest_papers

        for interest, papers in papers_by_interest.items():
            if papers:
                findings.append(
                    f"{len(papers)} new paper(s) on {interest}: {papers[0].get('title', 'Untitled')[:60]}..."
                )

        if news:
            findings.append(f"{len(news)} AI/ML news article(s) retrieved")

        # Calculate confidence based on data quality
        confidence = "high"
        if len(all_papers) == 0 and len(news) == 0:
            confidence = "low"
        elif len(all_papers) < 3:
            confidence = "medium"

        # Build summary
        summary = (
            f"Discovered {len(all_papers)} papers and {len(news)} news items "
            f"for research interests: {', '.join(self.research_interests[:3])}"
        )

        # Generate brief (saves to file)
        brief, output_path = self.generate_research_brief(all_papers, topic="Daily Discovery")

        # Build metadata
        metadata = {
            "research_interests": self.research_interests,
            "total_sources": len(source_timestamps),
            "cache_enabled": True,
            "news_api_configured": bool(self.news.api_key),
        }

        # Create discovery result
        result = DiscoveryResult(
            task_id=task_id,
            completed_at=now,
            agent="frontier",
            query="Daily Discovery",
            summary=summary,
            findings=findings,
            citations=citations,
            source_timestamps=source_timestamps,
            confidence=confidence,
            papers=all_papers,
            news_items=news,
            output_path=output_path,
            metadata=metadata,
        )

        logger.info(f"Discovery complete: {len(all_papers)} papers, {len(news)} news, confidence={confidence}")
        return result


if __name__ == "__main__":
    # Simple test
    frontier = FRONTIER()
    print("FRONTIER agent initialized")
    print(f"Research interests: {', '.join(frontier.research_interests)}")
