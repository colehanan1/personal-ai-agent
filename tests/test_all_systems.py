#!/usr/bin/env python3
"""
Comprehensive System Test Suite
Tests all components of Cole's agent system.
"""
import sys
import os
import time
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# Test results
test_results: List[Dict[str, Any]] = []


def print_header():
    """Print test header."""
    print("=" * 70)
    print("COLE'S AGENT SYSTEM - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print()


def print_test(name: str, status: str, details: str = ""):
    """Print test result."""
    symbol = "✓" if status == "pass" else "✗"
    status_text = "PASS" if status == "pass" else "FAIL"

    print(f"{symbol} {name:<50} [{status_text}]")
    if details:
        print(f"  {details}")

    test_results.append({"name": name, "status": status, "details": details})


def test_vllm_connectivity():
    """Test vLLM server connectivity."""
    try:
        import requests

        api_url = os.getenv("LLM_API_URL", "http://localhost:8000").rstrip("/")
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        url = f"{api_url}/v1/models"
        response = requests.get(url, timeout=5, headers=headers)

        if response.status_code == 200:
            print_test("vLLM Server Connectivity", "pass", "Server responding")
        else:
            print_test(
                "vLLM Server Connectivity",
                "fail",
                f"Server returned status {response.status_code}",
            )
            assert False, f"Server returned status {response.status_code}"

    except requests.exceptions.ConnectionError as e:
        print_test(
            "vLLM Server Connectivity",
            "fail",
            "Server not running (start with: python scripts/start_vllm.py)",
        )
        assert False, f"Server not running: {e}"
    except Exception as e:
        print_test("vLLM Server Connectivity", "fail", str(e))
        assert False, str(e)


def test_vllm_inference():
    """Test vLLM inference speed."""
    try:
        import requests

        api_url = os.getenv("LLM_API_URL", "http://localhost:8000").rstrip("/")
        model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        url = f"{api_url}/v1/chat/completions"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Say 'test' and nothing else."}],
            "max_tokens": 10,
        }

        start_time = time.time()
        response = requests.post(url, json=payload, timeout=30, headers=headers)
        elapsed = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            tokens = len(data["choices"][0]["message"]["content"].split())
            tokens_per_sec = tokens / elapsed if elapsed > 0 else 0

            print_test(
                "vLLM Inference",
                "pass",
                f"{tokens_per_sec:.1f} tokens/sec, {elapsed:.2f}s response time",
            )
        else:
            print_test("vLLM Inference", "fail", f"Status {response.status_code}")
            assert False, f"Status {response.status_code}"

    except Exception as e:
        print_test("vLLM Inference", "fail", str(e))
        assert False, str(e)


def test_weaviate_connectivity():
    """Test Weaviate connectivity."""
    try:
        import requests

        weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080").rstrip("/")
        response = requests.get(f"{weaviate_url}/v1/meta", timeout=5)

        if response.status_code == 200:
            print_test("Weaviate Connectivity", "pass", "Database ready")
        else:
            print_test("Weaviate Connectivity", "fail", "Database not ready")
            assert False, "Database not ready"

    except Exception as e:
        print_test(
            "Weaviate Connectivity",
            "fail",
            f"{str(e)} (start with: docker-compose up -d)",
        )
        assert False, str(e)


def test_weaviate_schema():
    """Test Weaviate schema initialization."""
    try:
        from memory.init_db import create_schema, get_client

        client = get_client()
        create_schema(client)

        # Check if collections exist
        collections = ["ShortTermMemory", "WorkingMemory", "LongTermMemory"]
        existing = [c for c in collections if client.collections.exists(c)]

        client.close()

        if len(existing) == 3:
            print_test(
                "Weaviate Schema", "pass", f"{len(existing)} collections initialized"
            )
        else:
            print_test("Weaviate Schema", "fail", f"Only {len(existing)}/3 collections")
            assert False, f"Only {len(existing)}/3 collections"

    except Exception as e:
        print_test("Weaviate Schema", "fail", str(e))
        assert False, str(e)


def test_memory_operations():
    """Test memory CRUD operations."""
    try:
        from memory.operations import MemoryOperations

        with MemoryOperations() as mem:
            # Test short-term memory
            mem_id = mem.add_short_term(
                agent="TEST",
                content="Test memory entry",
                context="System test",
            )

            # Retrieve
            recent = mem.get_recent_short_term(hours=1, agent="TEST")

            if len(recent) > 0:
                print_test(
                    "Memory Operations",
                    "pass",
                    f"Insert and retrieve successful ({len(recent)} entries)",
                )
            else:
                print_test("Memory Operations", "fail", "No entries retrieved")
                assert False, "No entries retrieved"

    except Exception as e:
        print_test("Memory Operations", "fail", str(e))
        assert False, str(e)


def test_home_assistant():
    """Test Home Assistant integration."""
    try:
        from integrations import HomeAssistantAPI

        ha = HomeAssistantAPI()

        if not ha.url or not ha.token:
            print_test(
                "Home Assistant",
                "fail",
                "Not configured (set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN)",
            )
            assert False, "Not configured (set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN)"

        # Try to get states
        states = ha.get_all_states()

        if isinstance(states, list):
            print_test("Home Assistant", "pass", f"Connected ({len(states)} entities)")
        else:
            print_test("Home Assistant", "fail", "Invalid response")
            assert False, "Invalid response"

    except Exception as e:
        print_test("Home Assistant", "fail", str(e))
        assert False, str(e)


def test_weather_api():
    """Test Weather API integration."""
    try:
        from integrations import WeatherAPI

        weather = WeatherAPI()

        if not weather.api_key:
            print_test(
                "Weather API",
                "fail",
                "Not configured (Use OPENWEATHER_API_KEY; WEATHER_API_KEY is supported for backward compatibility.)",
            )
            assert False, "Not configured (Use OPENWEATHER_API_KEY; WEATHER_API_KEY is supported for backward compatibility.)"

        # Get current weather
        current = weather.current_weather()

        if "temp" in current:
            print_test(
                "Weather API",
                "pass",
                f"{current['temp']}°F {current['location']}, {current['condition']}",
            )
        else:
            print_test("Weather API", "fail", "Invalid response")
            assert False, "Invalid response"

    except Exception as e:
        print_test("Weather API", "fail", str(e))
        assert False, str(e)


def test_arxiv_api():
    """Test arXiv API integration."""
    try:
        from integrations import ArxivAPI

        arxiv = ArxivAPI()

        # Search for a common topic
        papers = arxiv.search_papers("cat:cs.AI AND ti:transformer", max_results=5)

        if len(papers) > 0:
            print_test("arXiv API", "pass", f"{len(papers)} papers found")
        else:
            print_test("arXiv API", "fail", "No papers found")
            assert False, "No papers found"

    except Exception as e:
        print_test("arXiv API", "fail", str(e))
        assert False, str(e)


def test_news_api():
    """Test News API integration."""
    try:
        from integrations import NewsAPI

        news = NewsAPI()

        if not news.api_key:
            print_test("News API", "fail", "Not configured (set NEWS_API_KEY)")
            assert False, "Not configured (set NEWS_API_KEY)"

        # Get top headlines
        headlines = news.get_top_headlines(category="technology", max_results=5)

        if len(headlines) > 0:
            print_test("News API", "pass", f"{len(headlines)} articles retrieved")
        else:
            print_test("News API", "fail", "No articles found")
            assert False, "No articles found"

    except Exception as e:
        print_test("News API", "fail", str(e))
        assert False, str(e)


def test_job_queue():
    """Test job queue system."""
    try:
        from job_queue import JobManager
        from datetime import datetime, timedelta

        manager = JobManager()
        manager.start()

        # Add a test job
        def test_task():
            pass

        run_time = datetime.now() + timedelta(seconds=5)
        manager.add_job("test_job", test_task, run_time)

        # List jobs
        jobs = manager.list_jobs()

        manager.shutdown()

        if len(jobs) > 0:
            print_test("Job Queue", "pass", f"{len(jobs)} job(s) scheduled")
        else:
            print_test("Job Queue", "fail", "No jobs in queue")
            assert False, "No jobs in queue"

    except Exception as e:
        print_test("Job Queue", "fail", str(e))
        assert False, str(e)


def test_logging():
    """Test logging system."""
    try:
        from agent_logging import setup_logging
        import os
        from milton_orchestrator.state_paths import resolve_state_dir

        logger = setup_logging("TEST_AGENT", console_output=False)

        logger.info("Test log entry")

        log_dir = str(resolve_state_dir() / "logs" / "test_agent")

        if os.path.exists(log_dir):
            print_test("Logging System", "pass", f"Log directory: {log_dir}")
        else:
            print_test("Logging System", "fail", "Log directory not created")
            assert False, "Log directory not created"

    except Exception as e:
        print_test("Logging System", "fail", str(e))
        assert False, str(e)


def print_summary():
    """Print test summary."""
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in test_results if r["status"] == "pass")
    failed = sum(1 for r in test_results if r["status"] == "fail")
    total = len(test_results)

    print(f"\nTotal tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("\n✓ ALL SYSTEMS OPERATIONAL")
    else:
        print(f"\n✗ {failed} SYSTEM(S) NEED ATTENTION")

        print("\nFailed tests:")
        for result in test_results:
            if result["status"] == "fail":
                print(f"  - {result['name']}: {result['details']}")

    print()


def main():
    """Run all tests."""
    print_header()

    # Run tests in order
    print("CORE SERVICES")
    print("-" * 70)
    test_vllm_connectivity()
    test_vllm_inference()
    test_weaviate_connectivity()
    test_weaviate_schema()

    print()
    print("MEMORY SYSTEM")
    print("-" * 70)
    test_memory_operations()

    print()
    print("INTEGRATIONS")
    print("-" * 70)
    test_home_assistant()
    test_weather_api()
    test_arxiv_api()
    test_news_api()

    print()
    print("INFRASTRUCTURE")
    print("-" * 70)
    test_job_queue()
    test_logging()

    print_summary()


if __name__ == "__main__":
    main()
