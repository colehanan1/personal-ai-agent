# agent_system/integrations/arxiv_api.py
import urllib.parse
import urllib.request
import feedparser

BASE_URL = "http://export.arxiv.org/api/query"

class ArxivAPI:
    def __init__(self, user_agent: str = "cole-local-agent/0.1"):
        self.user_agent = user_agent  # good practice per arXiv docs[web:93]

    def _call(self, query: str, start: int = 0, max_results: int = 5):
        params = {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        feed = feedparser.parse(data)  # standard pattern in arXiv examples[web:87][web:90]
        return feed

    def search_papers(self, query: str, max_results: int = 5):
        """Return list of dicts: title, authors, summary, published, arxiv_id, pdf_url."""
        feed = self._call(query, start=0, max_results=max_results)
        results = []
        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1]
            pdf_url = None
            for link in entry.links:
                if getattr(link, "type", "") == "application/pdf":
                    pdf_url = link.href
                    break

            results.append({
                "title": entry.title.strip(),
                "authors": [a.name for a in entry.authors],
                "summary": entry.summary.strip(),
                "published": entry.published,
                "arxiv_id": arxiv_id,
                "pdf_url": pdf_url,
            })
        return results

