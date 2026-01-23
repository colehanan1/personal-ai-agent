#!/usr/bin/env bash
set -euo pipefail

# Milton status script - shows systemd service status and health checks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
if [ -f "$SCRIPT_DIR/milton.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/milton.env"
fi

# Color output helpers
info() { echo "ℹ️  $*"; }
success() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; }
error() { echo "❌ $*" >&2; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                      MILTON SERVICE STATUS                            ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# Show systemd service status
info "Systemd Service Status:"
echo ""
systemctl --user status milton-api.service milton-gateway.service milton-reminders.service --no-pager || true
echo ""

# Show effective configuration
info "Effective Configuration:"
echo "  State Directory:  $MILTON_STATE_DIR"
echo "  API Server:       $MILTON_API_URL"
echo "  Gateway:          $GATEWAY_URL"
echo "  LLM Backend:      $LLM_API_URL"
echo "  Weaviate:         $WEAVIATE_URL"
echo "  Memory Retrieval: ${MILTON_GATEWAY_MEMORY_RETRIEVAL:-1}"
echo ""

# Check Open WebUI
info "Open WebUI Status:"
if docker ps --format '{{.Names}}' | grep -q "^open-webui$"; then
    success "Container running - http://localhost:3000"
else
    warn "Container not running - start with: $SCRIPT_DIR/open_webui_up.sh"
fi
echo ""

# Health checks
info "Health Checks:"
echo ""

# Check API /health
echo -n "  API /health:         "
if API_HEALTH=$(curl -fsS "$MILTON_API_URL/health" 2>&1); then
    success "OK"
else
    error "FAILED"
    echo "    Error: $API_HEALTH"
fi

# Check API /config
echo -n "  API /config:         "
if API_CONFIG=$(curl -fsS "$MILTON_API_URL/config" 2>&1); then
    STATE_DIR_FROM_API=$(echo "$API_CONFIG" | grep -oP '"state_dir"\s*:\s*"\K[^"]+' || echo "")
    if [ -n "$STATE_DIR_FROM_API" ]; then
        success "OK (state_dir: $STATE_DIR_FROM_API)"
    else
        warn "OK (no state_dir in response)"
    fi
else
    error "FAILED"
    echo "    Error: $API_CONFIG"
fi

# Check Gateway /health
echo -n "  Gateway /health:     "
if GW_HEALTH=$(curl -fsS "$GATEWAY_URL/health" 2>&1); then
    GW_STATUS=$(echo "$GW_HEALTH" | grep -oP '"status"\s*:\s*"\K[^"]+' || echo "unknown")
    LLM_STATUS=$(echo "$GW_HEALTH" | grep -oP '"llm"\s*:\s*"\K[^"]+' || echo "unknown")
    MEM_STATUS=$(echo "$GW_HEALTH" | grep -oP '"memory"\s*:\s*"\K[^"]+' || echo "unknown")

    if [ "$GW_STATUS" = "healthy" ] || [ "$GW_STATUS" = "degraded" ]; then
        success "OK (status: $GW_STATUS, llm: $LLM_STATUS, memory: $MEM_STATUS)"
    else
        warn "DEGRADED (status: $GW_STATUS, llm: $LLM_STATUS, memory: $MEM_STATUS)"
    fi
else
    error "FAILED"
    echo "    Error: $GW_HEALTH"
fi

# Check Gateway /memory/status
echo -n "  Gateway /memory/status: "
if MEM_STATUS_RESP=$(curl -fsS "$GATEWAY_URL/memory/status" 2>&1); then
    LAST_RETRIEVAL=$(echo "$MEM_STATUS_RESP" | grep -oP '"last_retrieval"\s*:\s*\K[^,}]+' || echo "null")
    RETRIEVAL_COUNT=$(echo "$MEM_STATUS_RESP" | grep -oP '"retrieval_count"\s*:\s*\K[0-9]+' || echo "0")

    if [ "$LAST_RETRIEVAL" != "null" ]; then
        success "OK (last: $LAST_RETRIEVAL, count: $RETRIEVAL_COUNT)"
    else
        if [ "${MILTON_GATEWAY_MEMORY_RETRIEVAL:-1}" = "1" ]; then
            warn "Memory retrieval enabled but no retrievals yet"
        else
            info "Memory retrieval disabled (count: $RETRIEVAL_COUNT)"
        fi
    fi
else
    error "FAILED"
    echo "    Error: $MEM_STATUS_RESP"
fi
echo ""

# Log file info
info "Log Files:"
echo "  API:       $MILTON_STATE_DIR/logs/milton-api.log"
echo "  Gateway:   $MILTON_STATE_DIR/logs/milton-gateway.log"
echo "  Reminders: journalctl --user -u milton-reminders -n 100 --no-pager"
echo ""
info "View logs:"
echo "  journalctl --user -u milton-api -f"
echo "  journalctl --user -u milton-gateway -f"
echo "  journalctl --user -u milton-reminders -f"
echo ""
