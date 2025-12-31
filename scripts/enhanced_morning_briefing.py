#!/home/cole-hanan/miniconda3/envs/milton/bin/python3
"""
Enhanced Morning Briefing with Benchmark Results
Combines weather, papers, and AI benchmark performance data
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from integrations.weather import WeatherAPI
from memory.operations import MemoryOperations


def get_benchmark_summary():
    """Extract benchmark results from memory."""
    try:
        with MemoryOperations() as mem:
            collection = mem.client.collections.get("ShortTermMemory")
            query = collection.query.fetch_objects(limit=50)

            # Find benchmark summaries and recent responses
            summaries = []
            recent_queries = []

            for obj in query.objects:
                agent = obj.properties.get("agent", "")
                context = obj.properties.get("context", "")
                content = obj.properties.get("content", "")
                timestamp = obj.properties.get("timestamp")

                # System benchmark summaries
                if agent == "SYSTEM" and "benchmark" in context.lower():
                    summaries.append({
                        "summary": content,
                        "timestamp": str(timestamp) if timestamp else None
                    })

                # Recent benchmark queries
                elif any(k in context.lower() for k in ["purpose", "strengths", "improve", "fibonacci", "flask"]):
                    recent_queries.append({
                        "agent": agent,
                        "query": context[:60] + "..." if len(context) > 60 else context,
                        "response_preview": content[:100] + "..." if len(content) > 100 else content
                    })

            return {
                "summaries": summaries[:3],
                "recent_queries": recent_queries[:5],
                "total_queries": len(recent_queries)
            }
    except Exception as e:
        return {
            "error": str(e),
            "summaries": [],
            "recent_queries": [],
            "total_queries": 0
        }


def generate_enhanced_briefing():
    """Generate morning briefing with weather, benchmarks, and system status."""
    print("=" * 70)
    print("MILTON MORNING BRIEFING")
    print(f"{datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}")
    print("=" * 70)

    # Weather
    print("\n📍 WEATHER")
    try:
        weather = WeatherAPI().current_weather()
        print(f"  Location: {weather['location']}")
        print(f"  Current:  {weather['temp']:.1f}°F, {weather['condition']}")
        print(f"  Range:    {weather['low']:.1f}°F - {weather['high']:.1f}°F")
        print(f"  Humidity: {weather['humidity']}%")
        weather_data = weather
    except Exception as e:
        print(f"  ⚠ Weather unavailable: {e}")
        weather_data = None

    # Benchmark Results
    print("\n🧪 AI BENCHMARK PERFORMANCE")
    benchmarks = get_benchmark_summary()

    if benchmarks.get("error"):
        print(f"  ⚠ Error accessing benchmarks: {benchmarks['error']}")
    elif benchmarks["summaries"]:
        print(f"  Latest Summary:")
        for summary in benchmarks["summaries"][:1]:
            print(f"    {summary['summary']}")

        if benchmarks["recent_queries"]:
            print(f"\n  Recent Test Queries ({benchmarks['total_queries']} total):")
            for i, query in enumerate(benchmarks["recent_queries"][:3], 1):
                print(f"    {i}. [{query['agent']}] {query['query']}")
    else:
        print("  No benchmark data available")

    # System Status
    print("\n🖥️  SYSTEM STATUS")
    try:
        with MemoryOperations() as mem:
            collection = mem.client.collections.get("ShortTermMemory")
            result = collection.aggregate.over_all(total_count=True)
            vector_count = result.total_count or 0
            print(f"  Memory vectors: {vector_count}")
            print(f"  Status: ✓ Online")
    except Exception as e:
        print(f"  ⚠ Memory check failed: {e}")

    # Save to file
    print("\n💾 SAVING BRIEFING")
    output_dir = Path("inbox/morning")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "enhanced_brief_latest.json"

    briefing_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "weather": weather_data,
        "benchmarks": benchmarks,
        "system_status": {
            "memory_vectors": vector_count if 'vector_count' in locals() else 0,
            "status": "online"
        }
    }

    with output_file.open("w") as f:
        json.dump(briefing_data, f, indent=2)

    print(f"  ✓ Saved to: {output_file}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if weather_data:
        print(f"  Weather:    {weather_data['temp']:.0f}°F, {weather_data['condition']}")
    if benchmarks["summaries"]:
        print(f"  Benchmarks: {benchmarks['total_queries']} queries stored in memory")
    print(f"  Full data:  {output_file}")
    print("=" * 70)

    return output_file


if __name__ == "__main__":
    try:
        generate_enhanced_briefing()
    except Exception as e:
        print(f"\n❌ Error generating briefing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
