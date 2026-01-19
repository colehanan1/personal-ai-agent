#!/usr/bin/env bash
set -euo pipefail

# Milton smoke test - validates running services with comprehensive checks
# Tests API, Gateway, and memory retrieval functionality

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
if [ -f "$SCRIPT_DIR/milton.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/milton.env"
fi

# Color output helpers
info() { echo "ℹ️  $*"; }
success() { echo "✅ $*"; }
error() { echo "❌ $*" >&2; }
warn() { echo "⚠️  $*"; }

# Default to environment values or fallback
MILTON_API_URL="${MILTON_API_URL:-http://localhost:8001}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8081}"
MEMORY_RETRIEVAL_ENABLED="${MILTON_GATEWAY_MEMORY_RETRIEVAL:-1}"

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0

# Print test header
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                        MILTON SMOKE TESTS                             ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration:"
echo "  API URL:          $MILTON_API_URL"
echo "  Gateway URL:      $GATEWAY_URL"
echo "  Memory Retrieval: $MEMORY_RETRIEVAL_ENABLED"
echo "  State Directory:  ${MILTON_STATE_DIR:-$HOME/.local/state/milton}"
echo ""

# Helper function to run a test
run_test() {
    local test_name=$1
    shift
    local test_command=("$@")

    info "TEST: $test_name"

    if "${test_command[@]}"; then
        success "PASS: $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        error "FAIL: $test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Helper to show remediation on failure
show_remediation() {
    local service=$1
    echo ""
    error "Remediation for $service:"
    if [ "$service" = "API" ]; then
        echo "  systemctl --user restart milton-api"
        echo "  journalctl --user -u milton-api -n 50 --no-pager"
    elif [ "$service" = "Gateway" ]; then
        echo "  systemctl --user restart milton-gateway"
        echo "  journalctl --user -u milton-gateway -n 50 --no-pager"
    fi
    echo ""
}

# Helper to show logs on failure
show_logs_on_failure() {
    if [ $TESTS_FAILED -gt 0 ]; then
        echo ""
        error "Tests failed. Showing recent logs..."
        echo ""

        # Try journalctl first (systemd), fallback to log files
        if systemctl --user is-active milton-api.service >/dev/null 2>&1; then
            echo "=== API Server Logs (systemd, last 80 lines) ==="
            journalctl --user -u milton-api -n 80 --no-pager 2>/dev/null || echo "(no systemd logs)"
        else
            echo "=== API Server Logs (file, last 80 lines) ==="
            tail -80 "${MILTON_STATE_DIR:-$HOME/.local/state/milton}/logs/milton-api.log" 2>/dev/null || \
            tail -80 /tmp/milton_api.log 2>/dev/null || echo "(no API logs found)"
        fi
        echo ""

        if systemctl --user is-active milton-gateway.service >/dev/null 2>&1; then
            echo "=== Gateway Logs (systemd, last 80 lines) ==="
            journalctl --user -u milton-gateway -n 80 --no-pager 2>/dev/null || echo "(no systemd logs)"
        else
            echo "=== Gateway Logs (file, last 80 lines) ==="
            tail -80 "${MILTON_STATE_DIR:-$HOME/.local/state/milton}/logs/milton-gateway.log" 2>/dev/null || \
            tail -80 /tmp/milton_gateway.log 2>/dev/null || echo "(no Gateway logs found)"
        fi
        echo ""
    fi
}

# Trap to show logs on failure
trap show_logs_on_failure EXIT

# Test 1: API /config endpoint
test_api_config() {
    local response
    response=$(curl -fsS "$MILTON_API_URL/config" 2>&1)

    # Check if response contains state_dir
    if echo "$response" | grep -q '"state_dir"'; then
        local state_dir
        state_dir=$(echo "$response" | grep -oP '"state_dir"\s*:\s*"\K[^"]+' || echo "")
        if [ -n "$state_dir" ]; then
            info "API state_dir: $state_dir"
            return 0
        else
            error "state_dir field present but empty"
            return 1
        fi
    else
        error "Response missing 'state_dir' field"
        echo "Response: $response"
        return 1
    fi
}
run_test "API /config endpoint returns state_dir" test_api_config || show_remediation "API"

# Test 2: API /health endpoint
test_api_health() {
    curl -fsS "$MILTON_API_URL/health" >/dev/null 2>&1
}
run_test "API /health endpoint" test_api_health || show_remediation "API"

# Test 3: Gateway /health endpoint
test_gateway_health() {
    local response
    response=$(curl -fsS "$GATEWAY_URL/health" 2>&1)

    # Check health response structure
    if echo "$response" | grep -q '"status"'; then
        local status llm_status memory_status
        status=$(echo "$response" | grep -oP '"status"\s*:\s*"\K[^"]+' || echo "unknown")
        llm_status=$(echo "$response" | grep -oP '"llm"\s*:\s*"\K[^"]+' || echo "unknown")
        memory_status=$(echo "$response" | grep -oP '"memory"\s*:\s*"\K[^"]+' || echo "unknown")

        info "Gateway health: status=$status, llm=$llm_status, memory=$memory_status"

        if [ "$llm_status" = "down" ]; then
            warn "LLM backend is down - check $LLM_API_URL"
        fi

        return 0
    else
        error "Invalid health response"
        echo "Response: $response"
        return 1
    fi
}
run_test "Gateway /health endpoint" test_gateway_health || show_remediation "Gateway"

# Test 4: Gateway /memory/status (before chat)
test_memory_status_before() {
    local response
    response=$(curl -fsS "$GATEWAY_URL/memory/status" 2>&1)

    if echo "$response" | grep -q '"last_retrieval"'; then
        LAST_RETRIEVAL_BEFORE=$(echo "$response" | grep -oP '"last_retrieval"\s*:\s*\K[^,}]+' || echo "null")
        info "Memory status before chat: last_retrieval=$LAST_RETRIEVAL_BEFORE"
        return 0
    else
        error "Response missing 'last_retrieval' field"
        echo "Response: $response"
        return 1
    fi
}
run_test "Gateway /memory/status accessible" test_memory_status_before || show_remediation "Gateway"

# Test 5: Gateway /v1/chat/completions (with memory prompt)
test_chat_completions() {
    local response
    response=$(curl -fsS "$GATEWAY_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer sk-milton" \
        -d '{
            "model": "milton-local",
            "messages": [{"role": "user", "content": "Tell me about my goals from memory."}],
            "max_tokens": 100
        }' 2>&1)

    # Check if response contains expected fields
    if echo "$response" | grep -q '"choices"'; then
        # Verify choices array has content
        if echo "$response" | grep -q '"message"'; then
            # Extract content field to verify it's not empty
            local content
            content=$(echo "$response" | grep -oP '"content"\s*:\s*"\K[^"]+' | head -1 || echo "")
            if [ -n "$content" ]; then
                info "Chat response: ${content:0:80}..."
                return 0
            else
                error "Response content is empty"
                echo "Full response: $response"
                return 1
            fi
        else
            error "Response missing 'message' field"
            echo "Full response: $response"
            return 1
        fi
    else
        error "Response missing 'choices' field"
        echo "Full response: $response"
        return 1
    fi
}
run_test "Gateway /v1/chat/completions with memory query" test_chat_completions || show_remediation "Gateway"

# Test 6: Gateway /memory/status (after chat) - verify retrieval happened
test_memory_status_after() {
    # Wait briefly for memory retrieval to complete
    sleep 1

    local response
    response=$(curl -fsS "$GATEWAY_URL/memory/status" 2>&1)

    if echo "$response" | grep -q '"last_retrieval"'; then
        local last_retrieval_after
        last_retrieval_after=$(echo "$response" | grep -oP '"last_retrieval"\s*:\s*\K[^,}]+' || echo "null")

        info "Memory status after chat: last_retrieval=$last_retrieval_after"

        # If memory retrieval is enabled, verify it happened
        if [ "$MEMORY_RETRIEVAL_ENABLED" = "1" ]; then
            if [ "$last_retrieval_after" = "null" ]; then
                error "Memory retrieval enabled but last_retrieval is still null"
                warn "Gateway may not be configured correctly or memory system is down"
                return 1
            else
                success "Memory retrieval occurred (last: $last_retrieval_after)"
                return 0
            fi
        else
            # Memory retrieval disabled
            if [ "$last_retrieval_after" = "null" ]; then
                info "Memory retrieval disabled (as expected)"
                return 0
            else
                warn "Memory retrieval disabled but last_retrieval is not null: $last_retrieval_after"
                return 0
            fi
        fi
    else
        error "Response missing 'last_retrieval' field"
        echo "Response: $response"
        return 1
    fi
}
run_test "Gateway memory retrieval verification" test_memory_status_after || show_remediation "Gateway"

# Test 7: Check gateway logs for warnings (ResourceWarning, Con004)
test_gateway_log_warnings() {
    local log_path=""

    # Try multiple log locations
    if [ -f "${MILTON_STATE_DIR:-$HOME/.local/state/milton}/logs/milton-gateway.log" ]; then
        log_path="${MILTON_STATE_DIR:-$HOME/.local/state/milton}/logs/milton-gateway.log"
    elif [ -f "/tmp/milton_gateway.log" ]; then
        log_path="/tmp/milton_gateway.log"
    fi

    if [ -n "$log_path" ]; then
        info "Checking gateway log: $log_path"

        # Check for ResourceWarning
        if grep -q "ResourceWarning" "$log_path" 2>/dev/null; then
            error "Found ResourceWarning in gateway logs"
            grep -n "ResourceWarning" "$log_path" | tail -5
            return 1
        fi

        # Check for Con004 (connection errors)
        if grep -q "Con004" "$log_path" 2>/dev/null; then
            error "Found Con004 connection errors in gateway logs"
            grep -n "Con004" "$log_path" | tail -5
            return 1
        fi

        success "No ResourceWarning or Con004 errors found"
        return 0
    else
        warn "Gateway log file not found (skipping warning check)"
        return 0
    fi
}
run_test "Gateway log health check (no warnings)" test_gateway_log_warnings

# Print summary
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                           TEST SUMMARY                                ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Passed: $TESTS_PASSED"
echo "  Failed: $TESTS_FAILED"
echo ""

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    success "All smoke tests passed!"
    echo ""
    exit 0
else
    error "$TESTS_FAILED test(s) failed"
    echo ""
    echo "Diagnostics:"
    echo "  ./scripts/milton_status.sh - Check service status"
    echo "  journalctl --user -u milton-api -n 100 --no-pager"
    echo "  journalctl --user -u milton-gateway -n 100 --no-pager"
    echo ""
    exit 1
fi
