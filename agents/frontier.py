"""
FRONTIER - Discovery Agent
Monitors research feeds, discovers papers, and generates research briefs.
"""
import requests
from typing import Dict, Any, Optional, List
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging
import sys

# Add parent directory to path for imports


from integrations import ArxivAPI, NewsAPI
from agents.memory_hooks import (
    build_memory_context,
    record_memory,
    should_store_responses,
)

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
    ) -> str:
        """
        Generate research brief from papers.

        Args:
            papers: List of papers
            topic: Topic description
            include_analysis: Whether to include LLM analysis

        Returns:
            Formatted research brief
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
        output_path = os.path.expanduser(
            f"~/milton/outputs/research_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                f.write(brief)
            logger.info(f"Research brief saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save brief: {e}")

        return brief

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

    def daily_discovery(self) -> Dict[str, Any]:
        """
        Run daily discovery routine.

        Returns:
            Discovery results with papers and news
        """
        logger.info("Running daily discovery routine")

        # Get papers for interests
        papers_by_interest = self.get_recent_papers_by_interest(days=1, max_per_interest=3)

        # Flatten to single list
        all_papers = []
        for papers in papers_by_interest.values():
            all_papers.extend(papers)

        # Generate brief
        brief = self.generate_research_brief(all_papers, topic="Daily Discovery")

        # Get AI news
        news = self.monitor_ai_news(max_articles=5)

        return {
            "papers": all_papers,
            "news": news,
            "brief": brief,
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    # Simple test
    frontier = FRONTIER()
    print("FRONTIER agent initialized")
    print(f"Research interests: {', '.join(frontier.research_interests)}")
