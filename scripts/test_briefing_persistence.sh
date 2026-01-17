#!/bin/bash
# Test briefing persistence across API server restart
# Verifies that briefing items persist in SQLite after stop/restart cycle

set -euo pipefail

# Configuration
readonly API_BASE="http://localhost:8001"
readonly LOG_FILE="/tmp/milton_api.log"
readonly HEALTH_ENDPOINT="${API_BASE}/health"
readonly BRIEFING_ENDPOINT="${API_BASE}/api/briefing/items"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly API_SCRIPT="${SCRIPT_DIR}/start_api_server.py"
readonly MAX_HEALTH_ATTEMPTS=40  # 40 * 0.5s = 20 seconds max wait

# Color codes for output
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

# Global variables for cleanup
API_PID=""

# Cleanup function
cleanup() {
    local exit_code=$?
    if [[ -n "${API_PID}" && "${API_PID}" -gt 0 ]]; then
        echo -e "\n${YELLOW}🧹 Cleaning up API server (PID: ${API_PID})...${NC}"
        if kill "${API_PID}" 2>/dev/null; then
            wait "${API_PID}" 2>/dev/null || true
            echo -e "${GREEN}✅ Server stopped cleanly${NC}"
        fi
    fi
    if [[ $exit_code -ne 0 ]]; then
        echo -e "\n${RED}❌ Test failed - see logs above or check ${LOG_FILE}${NC}"
    fi
}

trap cleanup EXIT

# Function: wait for API health endpoint
wait_for_health() {
    local attempt=1
    echo -e "${YELLOW}⏳ Waiting for API health endpoint...${NC}"
    
    while [[ $attempt -le $MAX_HEALTH_ATTEMPTS ]]; do
        if curl -sf "${HEALTH_ENDPOINT}" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ API server is healthy (attempt ${attempt}/${MAX_HEALTH_ATTEMPTS})${NC}"
            return 0
        fi
        
        if [[ $((attempt % 5)) -eq 0 ]]; then
            echo "   Still waiting... (attempt ${attempt}/${MAX_HEALTH_ATTEMPTS})"
        fi
        
        sleep 0.5
        ((attempt++))
    done
    
    echo -e "${RED}❌ Health check failed after ${MAX_HEALTH_ATTEMPTS} attempts${NC}"
    echo -e "${RED}Last 50 lines of ${LOG_FILE}:${NC}"
    tail -n 50 "${LOG_FILE}" 2>/dev/null || echo "(log file not found)"
    return 1
}

# Function: start API server
start_api_server() {
    echo -e "${YELLOW}🚀 Starting API server...${NC}"
    python "${API_SCRIPT}" > "${LOG_FILE}" 2>&1 &
    API_PID=$!
    
    if ! ps -p "${API_PID}" > /dev/null 2>&1; then
        echo -e "${RED}❌ Failed to start API server${NC}"
        echo -e "${RED}Log contents:${NC}"
        cat "${LOG_FILE}"
        exit 1
    fi
    
    echo "   Server PID: ${API_PID}"
    wait_for_health
}

# Function: stop API server
stop_api_server() {
    if [[ -n "${API_PID}" && "${API_PID}" -gt 0 ]]; then
        echo -e "${YELLOW}🛑 Stopping API server (PID: ${API_PID})...${NC}"
        if kill "${API_PID}" 2>/dev/null; then
            wait "${API_PID}" 2>/dev/null || true
            echo -e "${GREEN}✅ Server stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  Server already stopped${NC}"
        fi
        API_PID=""
        # Give system time to release the port
        sleep 1
    fi
}

# Function: create briefing item
create_briefing_item() {
    local unique_marker="$1"
    local response
    
    echo -e "${YELLOW}📝 Creating briefing item with marker: ${unique_marker}${NC}" >&2
    
    response=$(curl -sf -X POST "${BRIEFING_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"Test persistence: ${unique_marker}\", \"priority\": 5, \"source\": \"test_script\"}" \
        2>&1) || {
        echo -e "${RED}❌ Failed to create briefing item${NC}" >&2
        echo "Response: ${response}" >&2
        return 1
    }
    
    echo "   Response: ${response}" >&2
    
    # Parse item_id - handle both jq and fallback
    local item_id
    if command -v jq >/dev/null 2>&1; then
        item_id=$(echo "${response}" | jq -r '.id')
    else
        # Fallback: parse JSON with grep/sed
        item_id=$(echo "${response}" | grep -oP '"id":\s*\K\d+' || echo "")
    fi
    
    if [[ -z "${item_id}" || "${item_id}" == "null" ]]; then
        echo -e "${RED}❌ Failed to parse item ID from response${NC}" >&2
        return 1
    fi
    
    echo -e "${GREEN}✅ Created item with ID: ${item_id}${NC}" >&2
    echo "${item_id}"
}

# Function: verify briefing item exists
verify_briefing_item() {
    local expected_id="$1"
    local unique_marker="$2"
    local response
    
    echo -e "${YELLOW}🔍 Verifying briefing item exists...${NC}"
    echo "   Looking for ID: ${expected_id}"
    echo "   Looking for marker: ${unique_marker}"
    
    response=$(curl -sf "${BRIEFING_ENDPOINT}?status=active" 2>&1) || {
        echo -e "${RED}❌ Failed to fetch briefing items${NC}"
        echo "Response: ${response}"
        return 1
    }
    
    # Check if response contains our ID and marker
    local found_id=false
    local found_marker=false
    
    if echo "${response}" | grep -q "\"id\": ${expected_id}"; then
        found_id=true
        echo -e "${GREEN}   ✓ Found item ID: ${expected_id}${NC}"
    fi
    
    if echo "${response}" | grep -qF "${unique_marker}"; then
        found_marker=true
        echo -e "${GREEN}   ✓ Found unique marker: ${unique_marker}${NC}"
    fi
    
    if [[ "${found_id}" == true && "${found_marker}" == true ]]; then
        echo -e "${GREEN}✅ Briefing item persisted correctly!${NC}"
        return 0
    else
        echo -e "${RED}❌ Briefing item not found in active items${NC}"
        echo "Full response:"
        echo "${response}" | head -100
        return 1
    fi
}

# Main test flow
main() {
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Briefing Persistence Test (API Restart)      ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Generate unique marker for this test run
    local unique_marker="persist_test_$(date +%s)_$$"
    local item_id
    
    # Step 1: Start API server
    echo -e "\n${YELLOW}═══ Step 1: Start API Server ═══${NC}"
    start_api_server
    
    # Step 2: Create briefing item
    echo -e "\n${YELLOW}═══ Step 2: Create Briefing Item ═══${NC}"
    item_id=$(create_briefing_item "${unique_marker}")
    
    if [[ -z "${item_id}" ]]; then
        echo -e "${RED}❌ Failed to create briefing item${NC}"
        exit 1
    fi
    
    # Step 3: Stop API server
    echo -e "\n${YELLOW}═══ Step 3: Stop API Server ═══${NC}"
    stop_api_server
    
    # Step 4: Restart API server
    echo -e "\n${YELLOW}═══ Step 4: Restart API Server ═══${NC}"
    start_api_server
    
    # Step 5: Verify persistence
    echo -e "\n${YELLOW}═══ Step 5: Verify Persistence ═══${NC}"
    if verify_briefing_item "${item_id}" "${unique_marker}"; then
        echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              ✅ TEST PASSED ✅                  ║${NC}"
        echo -e "${GREEN}║                                                ║${NC}"
        echo -e "${GREEN}║  Briefing item persisted across restart!      ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
        exit 0
    else
        echo -e "\n${RED}╔════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║              ❌ TEST FAILED ❌                  ║${NC}"
        echo -e "${RED}║                                                ║${NC}"
        echo -e "${RED}║  Briefing item did NOT persist after restart  ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════╝${NC}"
        exit 1
    fi
}

# Run main
main
