#!/bin/bash
# Capture API startup log with warnings
# Starts Milton API server, waits for health, captures warnings, then stops cleanly

set -euo pipefail

# Configuration
readonly LOG_FILE="${1:-/tmp/milton_api.log}"
readonly API_PORT="${API_PORT:-8001}"
readonly HEALTH_URL="http://localhost:${API_PORT}/health"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly API_SCRIPT="${SCRIPT_DIR}/start_api_server.py"
readonly MAX_HEALTH_ATTEMPTS=60  # 60 * 0.5s = 30 seconds max wait

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly NC='\033[0m'

# Global PID
API_PID=""

cleanup() {
    local exit_code=$?
    if [[ -n "${API_PID}" && "${API_PID}" -gt 0 ]]; then
        if ps -p "${API_PID}" > /dev/null 2>&1; then
            echo -e "${GREEN}Stopping API server (PID: ${API_PID})...${NC}" >&2
            # Try graceful shutdown first (SIGINT)
            kill -INT "${API_PID}" 2>/dev/null || true
            sleep 2
            # Force kill if still running
            if ps -p "${API_PID}" > /dev/null 2>&1; then
                kill -TERM "${API_PID}" 2>/dev/null || true
                sleep 1
            fi
            wait "${API_PID}" 2>/dev/null || true
        fi
    fi
    
    # Verify log file is not empty
    if [[ -f "${LOG_FILE}" ]]; then
        local line_count=$(wc -l < "${LOG_FILE}")
        if [[ $line_count -eq 0 ]]; then
            echo -e "${RED}Warning: Log file is empty!${NC}" >&2
            exit_code=1
        else
            echo -e "${GREEN}Log captured: ${line_count} lines in ${LOG_FILE}${NC}" >&2
        fi
    else
        echo -e "${RED}Error: Log file not created${NC}" >&2
        exit_code=1
    fi
    
    exit $exit_code
}

trap cleanup EXIT INT TERM

# Main
echo -e "${GREEN}Starting API server with warning capture...${NC}" >&2
echo -e "Log file: ${LOG_FILE}" >&2
echo ""

# Start API with unbuffered output and warnings enabled
# Use stdbuf to force line-buffered output
PYTHONUNBUFFERED=1 \
PYTHONTRACEMALLOC=50 \
PYTHONWARNINGS=default \
stdbuf -oL -eL python "${API_SCRIPT}" > "${LOG_FILE}" 2>&1 &

API_PID=$!

if ! ps -p "${API_PID}" > /dev/null 2>&1; then
    echo -e "${RED}Failed to start API server${NC}" >&2
    exit 1
fi

echo -e "${GREEN}API server started (PID: ${API_PID})${NC}" >&2

# Wait for health endpoint
echo -e "Waiting for health endpoint at ${HEALTH_URL}..." >&2

attempt=1
while [[ $attempt -le $MAX_HEALTH_ATTEMPTS ]]; do
    if curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API server is healthy (attempt ${attempt}/${MAX_HEALTH_ATTEMPTS})${NC}" >&2
        break
    fi
    
    if [[ $((attempt % 10)) -eq 0 ]]; then
        echo "   Still waiting... (attempt ${attempt}/${MAX_HEALTH_ATTEMPTS})" >&2
    fi
    
    # Check if process died
    if ! ps -p "${API_PID}" > /dev/null 2>&1; then
        echo -e "${RED}API server process died unexpectedly${NC}" >&2
        echo -e "${RED}Last 50 lines of log:${NC}" >&2
        tail -n 50 "${LOG_FILE}" >&2
        exit 1
    fi
    
    sleep 0.5
    ((attempt++))
done

if [[ $attempt -gt $MAX_HEALTH_ATTEMPTS ]]; then
    echo -e "${RED}Health check timeout after ${MAX_HEALTH_ATTEMPTS} attempts${NC}" >&2
    echo -e "${RED}Last 50 lines of log:${NC}" >&2
    tail -n 50 "${LOG_FILE}" >&2
    exit 1
fi

# Give it a moment to finish startup logging
sleep 2

echo -e "${GREEN}✅ Startup complete - stopping server...${NC}" >&2

# Cleanup will handle shutdown
exit 0
