#!/usr/bin/env python3
"""
FRONTIER Discovery Agent Demo

Demonstrates:
- Daily discovery routine
- Caching behavior (cache hits/misses)
- Graceful degradation (works without NEWS_API_KEY)
- DiscoveryResult output format
- Citation tracking
- Source timestamps

Usage:
    python scripts/demo_frontier.py

    # With custom research topic
    python scripts/demo_frontier.py --topic "machine learning"

    # Clear cache first
    python scripts/demo_frontier.py --clear-cache

    # Show cache stats
    python scripts/demo_frontier.py --cache-stats
"""

import sys
import os
from pathlib import Path
import argparse
import json
from datetime import datetime

# Add parent directory to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from agents.frontier import FRONTIER
from agents.frontier_cache import get_discovery_cache
from agents.contracts import DiscoveryResult


def print_separator(char="=", length=70):
    """Print separator line."""
    print(char * length)


def print_discovery_result(result: DiscoveryResult):
    """Pretty-print a DiscoveryResult."""
    print_separator()
    print(f"FRONTIER Discovery Report")
    print_separator()

    print(f"\n📋 Task ID: {result.task_id}")
    print(f"📅 Completed: {result.completed_at}")
    print(f"🔍 Query: {result.query}")
    print(f"📊 Confidence: {result.confidence.upper()}")

    print(f"\n📝 SUMMARY")
    print(f"{result.summary}")

    if result.findings:
        print(f"\n🔎 KEY FINDINGS ({len(result.findings)})")
        for i, finding in enumerate(result.findings, 1):
            print(f"  {i}. {finding}")

    print(f"\n📄 PAPERS ({len(result.papers)})")
    for i, paper in enumerate(result.papers[:3], 1):  # Show first 3
        title = paper.get("title", "Untitled")
        if "id" in paper:
            arxiv_id = paper.get("id", "unknown")
        else:
            arxiv_id = paper.get("arxiv_id", "unknown")
        print(f"  {i}. {title[:60]}...")
        print(f"     arXiv: {arxiv_id}")

    if len(result.papers) > 3:
        print(f"  ... and {len(result.papers) - 3} more papers")

    print(f"\n📰 NEWS ({len(result.news_items)})")
    if result.news_items:
        for i, article in enumerate(result.news_items[:3], 1):  # Show first 3
            title = article.get("title", "Untitled")
            url = article.get("url", "N/A")
            print(f"  {i}. {title[:60]}...")
            print(f"     URL: {url[:60]}...")
        if len(result.news_items) > 3:
            print(f"  ... and {len(result.news_items) - 3} more articles")
    else:
        news_api_configured = result.metadata.get("news_api_configured", False)
        if not news_api_configured:
            print("  ⚠️  No news (NEWS_API_KEY not configured - graceful degradation)")
        else:
            print("  No news articles found")

    print(f"\n📚 CITATIONS ({len(result.citations)})")
    for i, citation in enumerate(result.citations[:5], 1):  # Show first 5
        print(f"  {i}. {citation}")
    if len(result.citations) > 5:
        print(f"  ... and {len(result.citations) - 5} more citations")

    print(f"\n⏰ SOURCE TIMESTAMPS")
    for source, timestamp in result.source_timestamps.items():
        print(f"  {source}: {timestamp}")

    print(f"\n🔧 METADATA")
    print(f"  Research Interests: {', '.join(result.metadata.get('research_interests', [])[:3])}")
    print(f"  Total Sources: {result.metadata.get('total_sources', 0)}")
    print(f"  Cache Enabled: {result.metadata.get('cache_enabled', False)}")
    print(f"  News API Configured: {result.metadata.get('news_api_configured', False)}")

    print_separator()


def demo_daily_discovery():
    """Run daily discovery demo."""
    print("\n🚀 Running FRONTIER Daily Discovery Demo")
    print_separator()

    print("\n1️⃣  Initializing FRONTIER agent...")
    frontier = FRONTIER()
    print(f"   Research interests: {', '.join(frontier.research_interests[:3])}")

    # Check if NEWS_API_KEY is set
    news_api_key = os.getenv("NEWS_API_KEY")
    if news_api_key:
        print("   ✅ NEWS_API_KEY configured")
    else:
        print("   ⚠️  NEWS_API_KEY not set (will gracefully degrade)")

    print("\n2️⃣  Running daily_discovery() (may take 1-3 seconds on first run)...")
    start_time = datetime.now()
    result = frontier.daily_discovery()
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"   ✅ Discovery completed in {elapsed:.2f} seconds")

    print("\n3️⃣  Discovery Results:")
    print_discovery_result(result)

    print("\n4️⃣  Running daily_discovery() again (should use cache)...")
    start_time = datetime.now()
    result2 = frontier.daily_discovery()
    elapsed2 = (datetime.now() - start_time).total_seconds()
    print(f"   ✅ Discovery completed in {elapsed2:.2f} seconds")

    if elapsed2 < elapsed / 2:
        print(f"   🎉 Cache hit! Second run {elapsed / elapsed2:.1f}x faster")
    else:
        print("   ⚠️  Cache may have missed (check TTL)")

    # Verify results are identical
    if result.papers == result2.papers:
        print("   ✅ Results are identical (deterministic)")
    else:
        print("   ⚠️  Results differ (cache may have different data)")


def demo_custom_search(topic: str):
    """Demo custom paper search with caching."""
    print(f"\n🔍 Searching for papers on: {topic}")
    print_separator()

    frontier = FRONTIER()

    print("\n1️⃣  First search (cache miss)...")
    start_time = datetime.now()
    papers1 = frontier.find_papers_cached(topic, max_results=5, use_cache=True)
    elapsed1 = (datetime.now() - start_time).total_seconds()
    print(f"   Found {len(papers1)} papers in {elapsed1:.2f} seconds")

    if papers1:
        print(f"\n   Top result:")
        print(f"   - {papers1[0].get('title', 'Untitled')[:70]}...")
        print(f"   - arXiv: {papers1[0].get('id', 'unknown')}")
        print(f"   - Retrieved: {papers1[0].get('retrieved_at', 'N/A')}")

    print("\n2️⃣  Second search (cache hit)...")
    start_time = datetime.now()
    papers2 = frontier.find_papers_cached(topic, max_results=5, use_cache=True)
    elapsed2 = (datetime.now() - start_time).total_seconds()
    print(f"   Found {len(papers2)} papers in {elapsed2:.2f} seconds")

    if elapsed2 < elapsed1 / 5:
        print(f"   🎉 Cache hit! {elapsed1 / elapsed2:.1f}x faster")
    else:
        print("   ⚠️  Cache may have missed")

    # Verify determinism
    if papers1 == papers2:
        print("   ✅ Results are identical (deterministic)")


def show_cache_stats():
    """Show cache statistics."""
    print("\n📊 FRONTIER Cache Statistics")
    print_separator()

    cache = get_discovery_cache()
    stats = cache.get_stats()

    print(f"\nTotal cache entries: {stats['total']}")
    print(f"\nBy source:")
    for source, count in stats.get("by_source", {}).items():
        print(f"  {source}: {count}")

    if stats.get("oldest"):
        print(f"\nOldest entry: {stats['oldest']}")
    if stats.get("newest"):
        print(f"Newest entry: {stats['newest']}")

    print_separator()


def clear_cache():
    """Clear FRONTIER cache."""
    print("\n🗑️  Clearing FRONTIER cache...")
    cache = get_discovery_cache()
    cache.clear()
    print("   ✅ Cache cleared")


def main():
    """Main demo entry point."""
    parser = argparse.ArgumentParser(description="FRONTIER Discovery Agent Demo")
    parser.add_argument(
        "--topic",
        type=str,
        help="Custom research topic to search"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cache before running"
    )
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Show cache statistics"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("FRONTIER Discovery Agent Demo")
    print("Demonstrates caching, graceful degradation, and citations")
    print("=" * 70)

    # Clear cache if requested
    if args.clear_cache:
        clear_cache()

    # Show cache stats if requested
    if args.cache_stats:
        show_cache_stats()
        return

    # Custom topic search or daily discovery
    if args.topic:
        demo_custom_search(args.topic)
    else:
        demo_daily_discovery()

    print("\n✨ Demo complete!")
    print("\nNext steps:")
    print("  - Run again to see cache hits")
    print("  - Try: python scripts/demo_frontier.py --topic 'neural networks'")
    print("  - Check cache: python scripts/demo_frontier.py --cache-stats")
    print("  - Clear cache: python scripts/demo_frontier.py --clear-cache")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
