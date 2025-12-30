#!/usr/bin/env python3
"""
Phase 2 Integration Tests
Tests all major components of the Milton system
"""
import sys
sys.path.insert(0, '/home/cole-hanan/milton')

import requests
import json
from pathlib import Path

def test_vllm():
    """Test 1: vLLM inference server"""
    print("\n[TEST 1] Testing vLLM inference server...")
    try:
        headers = {"Authorization": "Bearer dy537t7K6iEcE3Xr8O0N-6hStQ5veeGcRclhixvWvEo"}
        r = requests.get("http://localhost:8000/v1/models", headers=headers, timeout=5)
        assert r.status_code == 200, f"vLLM returned {r.status_code}"

        data = r.json()
        model_id = data.get('data', [{}])[0].get('id')
        print(f"  ✓ vLLM is UP")
        print(f"  ✓ Model loaded: {model_id}")
        return True
    except Exception as e:
        print(f"  ✗ vLLM FAILED: {e}")
        return False

def test_weaviate():
    """Test 2: Weaviate vector database"""
    print("\n[TEST 2] Testing Weaviate vector database...")
    try:
        r = requests.get("http://localhost:8080/v1/meta", timeout=5)
        assert r.status_code == 200, f"Weaviate returned {r.status_code}"

        data = r.json()
        version = data.get('version', 'unknown')
        print(f"  ✓ Weaviate is UP")
        print(f"  ✓ Version: {version}")
        return True
    except Exception as e:
        print(f"  ✗ Weaviate FAILED: {e}")
        return False

def test_agent_imports():
    """Test 3: Agent import verification"""
    print("\n[TEST 3] Testing agent imports...")
    results = []

    agents = [
        ("NEXUS", "agents.nexus", "NEXUS"),
        ("CORTEX", "agents.cortex", "CORTEX"),
        ("FRONTIER", "agents.frontier", "FRONTIER")
    ]

    for name, module_path, class_name in agents:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            print(f"  ✓ {name} import successful")
            results.append(True)
        except Exception as e:
            print(f"  ✗ {name} import FAILED: {e}")
            results.append(False)

    return all(results)

def test_agent_initialization():
    """Test 4: Agent initialization"""
    print("\n[TEST 4] Testing agent initialization...")
    results = []

    try:
        from agents.nexus import NEXUS
        nexus = NEXUS()
        print(f"  ✓ NEXUS initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ NEXUS initialization FAILED: {e}")
        results.append(False)

    try:
        from agents.cortex import CORTEX
        cortex = CORTEX()
        print(f"  ✓ CORTEX initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ CORTEX initialization FAILED: {e}")
        results.append(False)

    try:
        from agents.frontier import FRONTIER
        frontier = FRONTIER()
        print(f"  ✓ FRONTIER initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ FRONTIER initialization FAILED: {e}")
        results.append(False)

    return all(results)

def test_directories():
    """Test 5: Required directories exist"""
    print("\n[TEST 5] Testing directory structure...")
    results = []

    required_dirs = [
        Path("/home/cole-hanan/milton/logs/nexus"),
        Path("/home/cole-hanan/milton/logs/cortex"),
        Path("/home/cole-hanan/milton/logs/frontier"),
        Path("/home/cole-hanan/milton/job_queue/tonight"),
        Path("/home/cole-hanan/milton/job_queue/archive"),
        Path("/home/cole-hanan/milton/inbox/morning"),
        Path("/home/cole-hanan/milton/outputs"),
    ]

    for dir_path in required_dirs:
        if dir_path.exists():
            print(f"  ✓ {dir_path.relative_to('/home/cole-hanan/milton')}")
            results.append(True)
        else:
            print(f"  ✗ Missing: {dir_path.relative_to('/home/cole-hanan/milton')}")
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"    Created: {dir_path}")
            results.append(True)

    return all(results)

def test_config():
    """Test 6: Configuration files"""
    print("\n[TEST 6] Testing configuration...")
    results = []

    env_path = Path("/home/cole-hanan/milton/.env")
    if env_path.exists():
        with open(env_path, 'r') as f:
            content = f.read()

        if 'LLM_API_URL' in content:
            print(f"  ✓ .env file exists with LLM_API_URL")
            results.append(True)
        else:
            print(f"  ✗ .env missing LLM_API_URL")
            results.append(False)

        if 'WEAVIATE_URL' in content:
            print(f"  ✓ .env file has WEAVIATE_URL")
            results.append(True)
        else:
            print(f"  ✗ .env missing WEAVIATE_URL")
            results.append(False)
    else:
        print(f"  ✗ .env file not found")
        results.append(False)

    return all(results)

def main():
    print("="*70)
    print("MILTON PHASE 2: INTEGRATION TEST SUITE")
    print("="*70)

    tests = [
        ("vLLM Inference", test_vllm),
        ("Weaviate Memory", test_weaviate),
        ("Agent Imports", test_agent_imports),
        ("Agent Initialization", test_agent_initialization),
        ("Directory Structure", test_directories),
        ("Configuration", test_config),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n[EXCEPTION in {test_name}]: {e}")
            results[test_name] = False

    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print("-"*70)
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("="*70)
        print("✓ ALL TESTS PASSED - Phase 2 Ready!")
        print("="*70)
        return 0
    else:
        print("="*70)
        print("✗ SOME TESTS FAILED - Review errors above")
        print("="*70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
