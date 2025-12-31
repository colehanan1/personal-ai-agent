#!/bin/bash
# Quick summary of benchmark results

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║              MILTON BENCHMARK SUMMARY                              ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# System status
echo "📊 SYSTEM STATUS"
curl -s http://localhost:8001/api/system-state 2>/dev/null | jq -r '
  "  NEXUS:    \(.nexus.status)",
  "  CORTEX:   \(.cortex.status)",
  "  FRONTIER: \(.frontier.status)",
  "  Memory:   \(.memory.status) - \(.memory.vector_count) vectors (\(.memory.memory_mb) MB)"
' || echo "  ⚠ API server not responding"

echo ""
echo "🧪 BENCHMARK RESULTS"
echo ""

# Get benchmark summary from memory
/home/cole-hanan/miniconda3/envs/milton/bin/python3 << 'PYEOF'
from memory.operations import MemoryOperations
from datetime import datetime

with MemoryOperations() as mem:
    collection = mem.client.collections.get("ShortTermMemory")
    query = collection.query.fetch_objects(limit=50)

    # Find benchmark summaries
    summaries = []
    benchmark_queries = []

    for obj in query.objects:
        agent = obj.properties.get("agent", "")
        context = obj.properties.get("context", "")
        content = obj.properties.get("content", "")

        if agent == "SYSTEM" and "benchmark" in context.lower():
            summaries.append(content)
        elif any(k in context.lower() for k in ["purpose", "strengths", "improve", "fibonacci", "flask"]):
            benchmark_queries.append({
                "context": context,
                "agent": agent,
                "preview": content[:80]
            })

    if summaries:
        print(f"  Latest run: {summaries[0]}")
        print()

    if benchmark_queries:
        print(f"  Found {len(benchmark_queries)} benchmark responses:")
        for i, q in enumerate(benchmark_queries[:6], 1):
            print(f"    {i}. [{q['agent']}] {q['context'][:50]}...")
PYEOF

echo ""
echo "📁 FILES CREATED"
echo "  ✓ Git repo:        entrepreneur_project/"
echo "  ✓ Benchmark script: tests/quick_benchmark.py"
echo "  ✓ View results:     scripts/view_benchmark_results.py"
echo "  ✓ Error summary:    ERROR_SUMMARY.md"
echo ""
echo "🔍 QUICK COMMANDS"
echo "  View all results:   ./scripts/view_benchmark_results.py"
echo "  Run again:          ./tests/quick_benchmark.py"
echo "  Check system:       ./scripts/fix_and_test.sh"
echo ""
echo "════════════════════════════════════════════════════════════════════"
