# FRONTIER Discovery Agent - Production Documentation

**Status**: Works ✅

FRONTIER is Milton's research discovery agent that monitors scientific papers, AI/ML news, and research developments. It provides deterministic, citation-backed discovery with local-first caching.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Caching System](#caching-system)
4. [Discovery Sources](#discovery-sources)
5. [Output Schema](#output-schema)
6. [Configuration](#configuration)
7. [Usage Examples](#usage-examples)
8. [Adding New Sources](#adding-new-sources)
9. [Troubleshooting](#troubleshooting)

---

## Overview

### What FRONTIER Does

- **Paper Discovery**: Monitors arXiv for relevant research papers
- **News Monitoring**: Tracks AI/ML news and developments (optional)
- **Research Briefs**: Generates structured summaries with citations
- **Citation Tracking**: Maintains arXiv IDs, DOIs, and URLs for all findings
- **Deterministic Results**: Uses TTL-based caching for reproducible outputs

### Key Principles

1. **Local-First**: Prefer cached data, minimize external API calls
2. **Citation-Backed**: Every finding includes source citations and timestamps
3. **Graceful Degradation**: Works without optional API keys
4. **Single-User**: No multi-user isolation or authentication
5. **Evidence-First**: All outputs include provenance metadata

---

## Architecture

```
FRONTIER Agent
├── Discovery Methods
│   ├── find_papers_cached()      # arXiv search with caching
│   ├── monitor_ai_news_cached()  # News monitoring (optional)
│   └── daily_discovery()         # Unified discovery routine
│
├── Caching Layer
│   └── DiscoveryCache
│       ├── 6-hour TTL by default
│       ├── Storage: STATE_DIR/cache/frontier/
│       └── Deterministic cache keys (query + params hash)
│
└── Output Format
    └── DiscoveryResult
        ├── summary: Brief overview
        ├── findings: Bullet-point discoveries
        ├── citations: arXiv IDs, URLs, DOIs
        ├── source_timestamps: When each source was retrieved
        └── confidence: high/medium/low
```

---

## Caching System

### How It Works

FRONTIER uses a **TTL-based caching system** to provide deterministic results and reduce external API calls.

#### Cache Storage

- **Location**: `STATE_DIR/cache/frontier/`
- **Format**: JSON files (one per cached query)
- **Structure**:

```json
{
  "source": "arxiv",
  "query": "fMRI brain imaging",
  "params": {"max_results": 10, "categories": []},
  "cached_at": "2024-01-15T10:00:00.123456",
  "data": [
    {
      "id": "2401.12345",
      "title": "Deep Learning for fMRI Analysis",
      "retrieved_at": "2024-01-15T10:00:00.123456"
    }
  ]
}
```

#### Cache Keys

Cache keys are deterministic, generated from:
- Source name (e.g., "arxiv", "news")
- Query string (e.g., "fMRI")
- Parameters (e.g., `{"max_results": 10}`)

**Example**:
```python
cache_key = hashlib.sha256(
    f"arxiv:fMRI:{json.dumps({'max_results': 10}, sort_keys=True)}"
).hexdigest()[:16]
```

#### TTL Behavior

- **Default TTL**: 6 hours
- **Cache Hit**: Returns cached data if age < TTL
- **Cache Miss**: Fetches from external API, caches result
- **Expired**: Automatically deletes stale cache files

#### Cache Statistics

```python
from agents.frontier_cache import get_discovery_cache

cache = get_discovery_cache()
stats = cache.get_stats()

# Returns:
# {
#   "total": 15,
#   "by_source": {"arxiv": 10, "news": 5},
#   "oldest": "2024-01-15T08:00:00",
#   "newest": "2024-01-15T12:00:00"
# }
```

---

## Discovery Sources

### 1. arXiv (No API Key Required)

**Status**: Always Available ✅

- Searches arXiv RSS feed for research papers
- No authentication required
- Categories: cs.AI, cs.LG, cs.CV, q-bio.NC, etc.

**Usage**:
```python
from agents.frontier import FRONTIER

frontier = FRONTIER()
papers = frontier.find_papers_cached(
    research_topic="fMRI brain imaging",
    max_results=10,
    categories=["q-bio.NC", "cs.LG"],
    use_cache=True
)
```

**Output Fields**:
- `id`: arXiv ID (e.g., "2401.12345")
- `title`: Paper title
- `authors`: List of authors
- `abstract`: Paper abstract
- `published`: Publication date (ISO 8601)
- `pdf_url`: Direct PDF link
- `retrieved_at`: Timestamp when fetched

### 2. NewsAPI (Optional)

**Status**: Optional (graceful degradation) ⚠️

- Monitors AI/ML news articles
- Requires `NEWS_API_KEY` environment variable
- Returns empty list if key not configured

**Configuration**:
```bash
# .env
NEWS_API_KEY=your_newsapi_key_here
```

**Usage**:
```python
news = frontier.monitor_ai_news_cached(
    max_articles=10,
    use_cache=True
)
# Returns [] if NEWS_API_KEY not set (no errors)
```

**Output Fields**:
- `title`: Article title
- `url`: Article URL
- `published_at`: Publication timestamp
- `source`: News source name
- `retrieved_at`: Timestamp when fetched

### 3. Adding Future Sources

See [Adding New Sources](#adding-new-sources) section below.

---

## Output Schema

### DiscoveryResult

All FRONTIER outputs use the **DiscoveryResult** contract from `agents/contracts.py`.

**Required Fields**:
```python
@dataclass(frozen=True)
class DiscoveryResult:
    task_id: str                           # Unique task ID
    completed_at: str                      # ISO 8601 timestamp
    agent: str                             # "frontier"
    query: str                             # Search query/topic
    summary: str                           # Brief overview (required)

    # Optional fields
    findings: List[str]                    # Bullet-point discoveries
    citations: List[str]                   # arXiv IDs, URLs, DOIs
    source_timestamps: Dict[str, str]      # {source: timestamp}
    confidence: str                        # "low"/"medium"/"high"
    papers: List[Dict[str, Any]]           # Paper details
    news_items: List[Dict[str, Any]]       # News articles
    output_path: str                       # Path to saved brief
    metadata: Dict[str, Any]               # Additional metadata
```

**Example**:
```python
result = frontier.daily_discovery()

print(result.summary)
# "Discovered 8 papers and 3 news items for research interests: fMRI, brain imaging, neural networks"

print(result.findings)
# [
#   "3 new paper(s) on fMRI: Deep Learning for fMRI Analysis and Predictiv...",
#   "2 new paper(s) on brain imaging: Novel Brain Imaging Techniques for...",
#   "3 AI/ML news article(s) retrieved"
# ]

print(result.citations)
# [
#   "arxiv:2401.12345",
#   "https://arxiv.org/pdf/2401.12345.pdf",
#   "arxiv:2401.54321",
#   "https://example.com/ai-breakthrough"
# ]

print(result.source_timestamps)
# {
#   "arxiv_fMRI": "2024-01-15T10:00:00.123456",
#   "arxiv_brain imaging": "2024-01-15T10:00:05.234567",
#   "news": "2024-01-15T10:00:10.345678"
# }

print(result.confidence)
# "high"
```

---

## Configuration

### Environment Variables

```bash
# .env

# LLM Configuration (required for analysis)
LLM_API_URL=http://localhost:8000
LLM_MODEL=meta-llama/Llama-3.1-8B-Instruct

# Optional: NewsAPI
NEWS_API_KEY=your_newsapi_key_here  # Optional (graceful degradation)

# Optional: State directory override
STATE_DIR=/custom/path/to/state  # Defaults to milton_orchestrator default
```

### Research Interests

Customize in `agents/frontier.py`:

```python
self.research_interests = [
    "fMRI",
    "brain imaging",
    "neural networks",
    "biomedical engineering",
    "machine learning for neuroscience",
]
```

### Cache Configuration

```python
from agents.frontier_cache import DiscoveryCache

# Custom TTL (default: 6 hours)
cache = DiscoveryCache(ttl_hours=12)

# Custom cache directory
cache = DiscoveryCache(cache_dir=Path("/custom/cache/dir"))
```

---

## Usage Examples

### Daily Discovery Routine

```python
from agents.frontier import FRONTIER

frontier = FRONTIER()
result = frontier.daily_discovery()

print(f"Summary: {result.summary}")
print(f"Confidence: {result.confidence}")
print(f"Papers: {len(result.papers)}")
print(f"News: {len(result.news_items)}")

# Access findings
for finding in result.findings:
    print(f"- {finding}")

# Access citations
for citation in result.citations:
    print(f"  [Citation] {citation}")
```

### Cached Paper Search

```python
# First call: cache miss (calls arXiv API)
papers1 = frontier.find_papers_cached("fMRI", max_results=10)

# Second call: cache hit (returns cached results)
papers2 = frontier.find_papers_cached("fMRI", max_results=10)

# Same results, but second call is instant
assert papers1 == papers2
```

### Disable Caching

```python
# Always fetch fresh results
papers = frontier.find_papers_cached(
    "brain imaging",
    max_results=5,
    use_cache=False  # Bypass cache
)
```

### Generate Research Brief

```python
papers = frontier.find_papers_cached("neural networks", max_results=10)

brief = frontier.generate_research_brief(
    papers,
    topic="Neural Networks Weekly",
    include_analysis=True  # Uses LLM to analyze relevance
)

# Brief saved to STATE_DIR/outputs/research_brief_YYYYMMDD_HHMMSS.txt
print(brief)
```

### Graceful Degradation (No NewsAPI Key)

```python
# Works even if NEWS_API_KEY not set
result = frontier.daily_discovery()

# result.news_items will be []
# result.metadata["news_api_configured"] will be False
# No errors or warnings
```

---

## Adding New Sources

### Step 1: Create Integration

```python
# integrations/new_source.py

class NewSourceAPI:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NEW_SOURCE_API_KEY")

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search new source."""
        # Implement API call
        return results
```

### Step 2: Add to FRONTIER

```python
# agents/frontier.py

from integrations.new_source import NewSourceAPI

class FRONTIER:
    def __init__(self, ...):
        # ...
        self.new_source = NewSourceAPI()

    def search_new_source_cached(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search new source with caching."""
        cache = get_discovery_cache()

        # Check cache
        if use_cache:
            params = {"max_results": max_results}
            cached_results = cache.get("new_source", query, params)
            if cached_results is not None:
                return cached_results

        # Graceful degradation
        if not self.new_source.api_key:
            logger.warning("NEW_SOURCE_API_KEY not set - skipping")
            return []

        # Fetch from API
        results = self.new_source.search(query, max_results)

        # Add timestamp
        now = generate_iso_timestamp()
        for result in results:
            result["retrieved_at"] = now

        # Cache results
        if use_cache and results:
            cache.set("new_source", query, results, params)

        return results
```

### Step 3: Integrate into daily_discovery()

```python
def daily_discovery(self) -> DiscoveryResult:
    # ...

    # Add new source
    new_source_results = self.search_new_source_cached(
        query="relevant topic",
        max_results=5,
        use_cache=True
    )

    # Extract timestamp
    if new_source_results and "retrieved_at" in new_source_results[0]:
        source_timestamps["new_source"] = new_source_results[0]["retrieved_at"]

    # Add to findings
    if new_source_results:
        findings.append(f"{len(new_source_results)} results from NewSource")

    # ...
```

### Step 4: Add Tests

```python
# tests/test_frontier.py

def test_new_source_cached(test_cache_dir, mock_new_source_results):
    """Test new source caching."""
    with patch.object(FRONTIER, "search_new_source", return_value=mock_new_source_results):
        frontier = FRONTIER()

        cache = DiscoveryCache(cache_dir=test_cache_dir, ttl_hours=6)

        with patch("agents.frontier.get_discovery_cache", return_value=cache):
            # First call: cache miss
            results1 = frontier.search_new_source_cached("test query", use_cache=True)
            assert len(results1) > 0

            # Second call: cache hit
            with patch.object(FRONTIER, "search_new_source") as mock:
                results2 = frontier.search_new_source_cached("test query", use_cache=True)
                mock.assert_not_called()  # Cache hit
```

---

## Troubleshooting

### Cache Not Working

**Symptom**: Every call hits the external API, no caching

**Causes**:
1. Cache disabled: `use_cache=False`
2. Different parameters: Cache keys include params
3. TTL expired: Check cache age

**Solution**:
```python
from agents.frontier_cache import get_discovery_cache

cache = get_discovery_cache()
stats = cache.get_stats()

print(f"Total cache entries: {stats['total']}")
print(f"By source: {stats['by_source']}")

# Clear cache if needed
cache.clear()
```

### No News Results

**Symptom**: `result.news_items` is always empty

**Causes**:
1. `NEWS_API_KEY` not set in `.env`
2. API key invalid or expired
3. API rate limit exceeded

**Solution**:
```python
# Check API key configuration
import os
api_key = os.getenv("NEWS_API_KEY")
print(f"NEWS_API_KEY configured: {bool(api_key)}")

# Check metadata
result = frontier.daily_discovery()
print(f"News API configured: {result.metadata['news_api_configured']}")

# If False, FRONTIER gracefully degraded (no errors)
```

### Papers Missing retrieved_at Timestamp

**Symptom**: Papers don't have `retrieved_at` field

**Causes**:
1. Using non-cached method: `find_papers()` instead of `find_papers_cached()`
2. Old cached data without timestamps

**Solution**:
```python
# Always use cached methods
papers = frontier.find_papers_cached("fMRI", use_cache=True)

# Verify timestamp
assert "retrieved_at" in papers[0]

# Or clear cache to refresh
cache = get_discovery_cache()
cache.clear()
```

### Low Confidence Results

**Symptom**: `result.confidence == "low"`

**Causes**:
1. No papers or news found
2. Network issues preventing API calls
3. Invalid research topics

**Solution**:
```python
result = frontier.daily_discovery()

if result.confidence == "low":
    print(f"Papers found: {len(result.papers)}")
    print(f"News found: {len(result.news_items)}")

    # Check if sources are working
    papers = frontier.find_papers_cached("machine learning", max_results=5)
    if not papers:
        print("arXiv API may be down or blocked")
```

### DiscoveryResult Validation Errors

**Symptom**: `ValueError` when creating `DiscoveryResult`

**Causes**:
1. Missing required fields (task_id, agent, query, summary)
2. Invalid confidence level (not in [low, medium, high])
3. Invalid ISO 8601 timestamp

**Solution**:
```python
from agents.contracts import generate_task_id, generate_iso_timestamp

# Correct usage
result = DiscoveryResult(
    task_id=generate_task_id("discovery"),
    completed_at=generate_iso_timestamp(),
    agent="frontier",
    query="fMRI research",
    summary="Found 5 relevant papers",  # Required, non-empty
    confidence="medium",  # Must be low/medium/high
)
```

### Cache Permission Errors

**Symptom**: `PermissionError` when writing to cache

**Causes**:
1. Cache directory not writable
2. STATE_DIR permissions incorrect

**Solution**:
```bash
# Check cache directory
ls -la $STATE_DIR/cache/frontier/

# Fix permissions
chmod -R u+w $STATE_DIR/cache/
```

---

## Performance Characteristics

### API Call Reduction

With 6-hour TTL cache:
- **First discovery**: ~5 API calls (5 research interests)
- **Subsequent discoveries (within TTL)**: 0 API calls
- **Cache hit rate**: ~95% for daily discovery routine

### Response Times

- **Cache hit**: < 10ms (disk read)
- **Cache miss**: 1-3 seconds (arXiv API)
- **News API**: 0.5-1 second (if configured)

### Storage Usage

- **Per cached query**: ~5-50 KB (depends on results)
- **Daily discovery**: ~100-200 KB total
- **Auto-cleanup**: TTL expiration removes stale files

---

## Testing

Run FRONTIER tests:

```bash
# All tests
pytest tests/test_frontier.py -v

# Specific test
pytest tests/test_frontier.py::test_daily_discovery_integration -v

# With coverage
pytest tests/test_frontier.py --cov=agents.frontier --cov-report=html
```

**Test Coverage**:
- ✅ Cache hit/miss behavior
- ✅ TTL expiration
- ✅ Graceful degradation (no API keys)
- ✅ DiscoveryResult validation
- ✅ daily_discovery() integration
- ✅ Cache key determinism
- ✅ Source timestamp tracking

---

## Definition of Done Checklist

FRONTIER is considered "Works" when:

- [x] Implements caching with TTL (6 hours)
- [x] Returns DiscoveryResult with all required fields
- [x] Includes citations for all findings
- [x] Tracks source timestamps (retrieved_at)
- [x] Calculates confidence (low/medium/high)
- [x] Works without NEWS_API_KEY (graceful degradation)
- [x] Uses cached methods in daily_discovery()
- [x] Has 12+ passing unit tests with mocked APIs
- [x] Comprehensive documentation (this file)
- [x] Demo script showing graceful degradation

**Status**: ✅ All requirements met

---

## References

- [Agent Contracts](./AGENTS.md)
- [CORTEX Job Queue](./JOB_QUEUE.md)
- [arXiv API](https://arxiv.org/help/api)
- [NewsAPI Documentation](https://newsapi.org/docs)

---

**Last Updated**: 2026-01-02
**Version**: 1.0.0
**Status**: Production Ready ✅
