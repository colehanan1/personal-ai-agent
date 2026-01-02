#!/bin/bash
# Fix known issues and run tests

echo "=== FIXING KNOWN ISSUES ==="

# Default state directory (override with STATE_DIR)
STATE_DIR="${STATE_DIR:-$HOME/.local/state/milton}"

# 1. Create log directory
echo "Creating log directory..."
mkdir -p "${STATE_DIR}/logs"
echo "✓ Log directory created"

# 2. Check .env file has required keys
echo ""
echo "Checking .env configuration..."
if ! grep -q "OPENWEATHER_API_KEY" .env 2>/dev/null && ! grep -q "WEATHER_API_KEY" .env 2>/dev/null; then
    echo "⚠ Use OPENWEATHER_API_KEY; WEATHER_API_KEY is supported for backward compatibility."
elif ! grep -q "OPENWEATHER_API_KEY" .env 2>/dev/null && grep -q "WEATHER_API_KEY" .env 2>/dev/null; then
    echo "ℹ Use OPENWEATHER_API_KEY; WEATHER_API_KEY is supported for backward compatibility."
fi
if ! grep -q "NEWS_API_KEY" .env 2>/dev/null || grep -q "NEWS_API_KEY=YOUR_KEY_HERE" .env; then
    echo "⚠ NEWS_API_KEY not configured in .env"
fi
if ! grep -q "HOME_ASSISTANT" .env 2>/dev/null; then
    echo "ℹ Home Assistant not configured (optional)"
fi

echo ""
echo "=== RUNNING TESTS ==="
/home/cole-hanan/miniconda3/envs/milton/bin/python tests/test_all_systems.py

echo ""
echo "=== SYSTEM STATUS ==="
curl -s http://localhost:8001/api/system-state | jq

echo ""
echo "=== BENCHMARK RESULTS IN MEMORY ==="
/home/cole-hanan/miniconda3/envs/milton/bin/python scripts/view_benchmark_results.py | head -50
