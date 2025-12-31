#!/usr/bin/env python3
"""
Milton Benchmark Suite
Tests model capabilities across multiple dimensions and stores results.
"""
import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from memory.operations import MemoryOperations

API_URL = "http://localhost:8001"


class BenchmarkRunner:
    """Runs comprehensive benchmarks on Milton system."""

    def __init__(self):
        self.results = []
        self.start_time = time.time()

    def log(self, message: str):
        """Print timestamped log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def run_query(self, query: str, agent: str = None, category: str = "general") -> Dict[str, Any]:
        """Send query to Milton and wait for response."""
        self.log(f"Query ({category}): {query[:60]}...")

        # Submit query
        payload = {"query": query}
        if agent:
            payload["agent"] = agent

        response = requests.post(f"{API_URL}/api/ask", json=payload)
        response.raise_for_status()
        data = response.json()
        request_id = data["request_id"]

        # Wait for completion
        max_wait = 60
        start = time.time()
        while time.time() - start < max_wait:
            requests_data = requests.get(f"{API_URL}/api/recent-requests").json()
            req = next((r for r in requests_data if r["id"] == request_id), None)

            if req and req["status"] in ["COMPLETE", "FAILED"]:
                duration_ms = req.get("duration_ms")
                duration = (duration_ms / 1000) if duration_ms else 0
                self.log(f"  → {req['status']} in {duration:.1f}s")

                result = {
                    "query": query,
                    "category": category,
                    "agent": req.get("agent", "UNKNOWN"),
                    "status": req["status"],
                    "duration_s": duration,
                    "timestamp": datetime.now().isoformat(),
                }
                self.results.append(result)
                return result

            time.sleep(1)

        self.log("  → TIMEOUT")
        return {"query": query, "category": category, "status": "TIMEOUT"}

    def test_self_reflection(self):
        """Test model's ability to reflect on itself."""
        self.log("\n=== SELF-REFLECTION TESTS ===")

        queries = [
            "Who are you and what is your purpose?",
            "What are your key strengths as an AI assistant?",
            "What are your current limitations and how could you improve?",
            "How do you think you can best help make my life easier?",
            "Describe your ideal interaction with a human user.",
        ]

        for query in queries:
            self.run_query(query, agent="NEXUS", category="self_reflection")
            time.sleep(2)

    def test_task_execution(self):
        """Test CORTEX's task execution abilities."""
        self.log("\n=== TASK EXECUTION TESTS ===")

        queries = [
            "Write a Python function to calculate Fibonacci numbers recursively",
            "Create a simple TODO list data structure with add, remove, and list operations",
            "Generate a bash script to backup a directory",
        ]

        for query in queries:
            self.run_query(query, agent="CORTEX", category="task_execution")
            time.sleep(2)

    def test_research(self):
        """Test FRONTIER's research capabilities."""
        self.log("\n=== RESEARCH TESTS ===")

        queries = [
            "What are the latest trends in AI safety research?",
            "Summarize recent developments in quantum computing",
            "What papers discuss neural network interpretability?",
        ]

        for query in queries:
            self.run_query(query, agent="FRONTIER", category="research")
            time.sleep(2)

    def test_entrepreneurial_idea(self):
        """Generate code for an entrepreneurial idea."""
        self.log("\n=== ENTREPRENEURIAL PROJECT ===")

        query = """Create a simple API service idea for a 'Daily Motivation Quotes' app.
Include:
1. A Python Flask API with endpoints for getting random quotes
2. A simple data structure for storing quotes
3. Basic error handling
4. Instructions for running it

Keep it simple and production-ready."""

        self.run_query(query, agent="CORTEX", category="entrepreneurial")
        time.sleep(3)

    def test_problem_solving(self):
        """Test problem-solving abilities."""
        self.log("\n=== PROBLEM SOLVING TESTS ===")

        queries = [
            "How would you design a system to automatically organize my emails?",
            "What's the best approach to learn a new programming language efficiently?",
            "How can I automate my morning routine using technology?",
        ]

        for query in queries:
            self.run_query(query, agent="NEXUS", category="problem_solving")
            time.sleep(2)

    def test_memory_storage(self):
        """Verify memory storage is working."""
        self.log("\n=== MEMORY VERIFICATION ===")

        with MemoryOperations() as mem:
            collection = mem.client.collections.get("ShortTermMemory")
            result = collection.aggregate.over_all(total_count=True)
            count = result.total_count or 0

            self.log(f"Memory vectors stored: {count}")

            # Get recent memories
            query = collection.query.fetch_objects(limit=5)
            self.log(f"Recent memories: {len(query.objects)}")

            for obj in query.objects[:3]:
                agent = obj.properties.get("agent", "UNKNOWN")
                content = obj.properties.get("content", "")[:50]
                self.log(f"  - {agent}: {content}...")

    def create_git_repo(self):
        """Create a new git repo for entrepreneurial project."""
        self.log("\n=== CREATING GIT REPOSITORY ===")

        repo_path = ROOT_DIR / "entrepreneur_project"

        try:
            if repo_path.exists():
                self.log(f"Repo already exists at {repo_path}")
                return

            repo_path.mkdir(parents=True)

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            self.log(f"✓ Initialized git repo at {repo_path}")

            # Create README
            readme = repo_path / "README.md"
            readme.write_text("""# Daily Motivation Quotes API

A simple Flask API service for serving daily motivational quotes.

## Generated by Milton AI System
Created during benchmark testing.

## Setup
1. Install dependencies: `pip install flask`
2. Run: `python app.py`
3. Access: http://localhost:5000/quote

## Endpoints
- GET /quote - Get a random motivational quote
- GET /quotes - Get all quotes
""")

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit: Project setup by Milton"],
                cwd=repo_path,
                check=True,
            )

            self.log(f"✓ Created repository with initial commit")

        except Exception as e:
            self.log(f"✗ Error creating repo: {e}")

    def generate_report(self):
        """Generate benchmark report."""
        self.log("\n=== BENCHMARK REPORT ===")

        total_time = time.time() - self.start_time
        total_queries = len(self.results)
        successful = len([r for r in self.results if r["status"] == "COMPLETE"])
        failed = len([r for r in self.results if r["status"] == "FAILED"])

        self.log(f"Total time: {total_time:.1f}s")
        self.log(f"Total queries: {total_queries}")
        self.log(f"Successful: {successful}")
        self.log(f"Failed: {failed}")
        if total_queries > 0:
            self.log(f"Success rate: {(successful/total_queries*100):.1f}%")
        else:
            self.log("Success rate: N/A (no queries completed)")

        # Category breakdown
        categories = {}
        for result in self.results:
            cat = result["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "success": 0}
            categories[cat]["total"] += 1
            if result["status"] == "COMPLETE":
                categories[cat]["success"] += 1

        self.log("\nCategory Performance:")
        for cat, stats in categories.items():
            success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            self.log(f"  {cat}: {stats['success']}/{stats['total']} ({success_rate:.0f}%)")

        # Save report
        report_path = ROOT_DIR / "benchmark_results.json"
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "total_time_s": total_time,
            "total_queries": total_queries,
            "successful": successful,
            "failed": failed,
            "categories": categories,
            "results": self.results,
        }

        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2)

        self.log(f"\n✓ Report saved to {report_path}")

        # Store summary in memory
        try:
            with MemoryOperations() as mem:
                summary = f"Benchmark completed: {successful}/{total_queries} queries successful ({(successful/total_queries*100):.0f}%). Categories tested: {', '.join(categories.keys())}. Total time: {total_time:.1f}s"
                mem.add_short_term(
                    agent="SYSTEM",
                    content=summary,
                    context="Benchmark Suite",
                    metadata={"type": "benchmark_report", "timestamp": datetime.now().isoformat()},
                )
                self.log("✓ Summary stored in memory for morning briefing")
        except Exception as e:
            self.log(f"✗ Could not store in memory: {e}")

    def run_all(self):
        """Run complete benchmark suite."""
        self.log("=" * 60)
        self.log("MILTON BENCHMARK SUITE")
        self.log("=" * 60)

        try:
            self.test_self_reflection()
            self.test_task_execution()
            self.test_research()
            self.test_problem_solving()
            self.test_entrepreneurial_idea()
            self.create_git_repo()
            self.test_memory_storage()
            self.generate_report()

            self.log("\n" + "=" * 60)
            self.log("BENCHMARK COMPLETE")
            self.log("=" * 60)

        except KeyboardInterrupt:
            self.log("\n\nBenchmark interrupted by user")
            self.generate_report()
        except Exception as e:
            self.log(f"\n\nBenchmark error: {e}")
            import traceback
            traceback.print_exc()
            self.generate_report()


if __name__ == "__main__":
    runner = BenchmarkRunner()
    runner.run_all()
