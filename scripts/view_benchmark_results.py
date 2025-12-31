#!/home/cole-hanan/miniconda3/envs/milton/bin/python
"""
View Benchmark Results from Memory
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from memory.operations import MemoryOperations


def _parse_timestamp(value):
    """Parse RFC3339/ISO timestamps into aware datetimes."""
    if not value:
        return None

    # If already a datetime object, ensure it has timezone
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    # If string, parse it
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return None

    return None


def view_results():
    print("=" * 80)
    print("BENCHMARK RESULTS FROM MEMORY")
    print("=" * 80)

    with MemoryOperations() as mem:
        collection = mem.client.collections.get("ShortTermMemory")

        # Get all recent memories (last hour)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

        query = collection.query.fetch_objects(limit=50)

        # Filter benchmark-related memories
        benchmark_memories = []
        for obj in query.objects:
            context = obj.properties.get("context", "").lower()
            content = obj.properties.get("content", "")
            agent = obj.properties.get("agent", "")
            timestamp = obj.properties.get("timestamp")
            parsed_timestamp = _parse_timestamp(timestamp)

            # Keep only recent memories
            if not parsed_timestamp or parsed_timestamp < cutoff:
                continue

            # Look for benchmark-related queries
            if any(keyword in context for keyword in [
                "purpose", "strengths", "improve", "fibonacci",
                "bash script", "flask", "motivation", "benchmark"
            ]):
                benchmark_memories.append({
                    "timestamp": timestamp,
                    "parsed_timestamp": parsed_timestamp,
                    "agent": agent,
                    "context": obj.properties.get("context", ""),
                    "content": content,
                })

        # Sort by timestamp
        benchmark_memories.sort(
            key=lambda x: x["parsed_timestamp"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        print(f"\nFound {len(benchmark_memories)} benchmark-related memories\n")

        # Display results
        for i, mem in enumerate(benchmark_memories[:10], 1):
            print(f"\n{'='*80}")
            print(f"Result #{i}")
            print(f"{'='*80}")
            print(f"Timestamp: {mem['timestamp']}")
            print(f"Agent: {mem['agent']}")
            print(f"Question: {mem['context']}")
            content = mem['content']
            if len(content) > 500:
                print(f"\nAnswer:\n{content[:500]}...")
                print(f"\n[Truncated - {len(content)} total chars]")
            else:
                print(f"\nAnswer:\n{content}")

        # Show summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")

        agents_used = {}
        for mem in benchmark_memories:
            agent = mem['agent']
            agents_used[agent] = agents_used.get(agent, 0) + 1

        print(f"Total memories: {len(benchmark_memories)}")
        print(f"Agents used: {', '.join(f'{k}({v})' for k, v in agents_used.items())}")

        # Check for benchmark summary
        for obj in query.objects:
            agent = obj.properties.get("agent", "")
            context = obj.properties.get("context", "")
            if agent == "SYSTEM" and "benchmark" in context.lower():
                print(f"\nBenchmark Summary:")
                print(f"  {obj.properties.get('content', '')}")


if __name__ == "__main__":
    view_results()
