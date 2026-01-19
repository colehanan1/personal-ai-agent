#!/usr/bin/env bash
set -euo pipefail

# Milton shutdown script - stops systemd user services
# Provides clean shutdown with optional force mode for port cleanup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration for port info
if [ -f "$SCRIPT_DIR/milton.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/milton.env"
fi

# Color output helpers
info() { echo "ℹ️  $*"; }
success() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; }
error() { echo "❌ $*" >&2; }

# Parse arguments
FORCE_MODE=false
if [ "${1:-}" = "--force" ]; then
    FORCE_MODE=true
    warn "Force mode enabled - will kill any processes on Milton ports"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    MILTON SERVICE SHUTDOWN                            ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# Stop services in reverse order (gateway first, then API)
info "Stopping Milton services via systemd..."
systemctl --user stop milton-gateway.service 2>/dev/null || true
systemctl --user stop milton-api.service 2>/dev/null || true
echo ""

# Wait a moment for processes to terminate
sleep 1

# Check if services actually stopped
API_RUNNING=$(systemctl --user is-active milton-api.service 2>/dev/null || echo "inactive")
GATEWAY_RUNNING=$(systemctl --user is-active milton-gateway.service 2>/dev/null || echo "inactive")

if [ "$API_RUNNING" = "inactive" ]; then
    success "API service stopped"
else
    warn "API service still running (state: $API_RUNNING)"
fi

if [ "$GATEWAY_RUNNING" = "inactive" ]; then
    success "Gateway service stopped"
else
    warn "Gateway service still running (state: $GATEWAY_RUNNING)"
fi
echo ""

# Check for processes still listening on Milton ports
info "Checking for processes on Milton ports..."
API_PORT="${MILTON_API_PORT:-8001}"
GATEWAY_PORT="${MILTON_CHAT_PORT:-8081}"

check_port_listeners() {
    local port=$1
    local service_name=$2

    if command -v lsof >/dev/null 2>&1; then
        local listeners
        listeners=$(lsof -iTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null || true)

        if [ -n "$listeners" ]; then
            warn "$service_name port $port still has listeners:"
            echo "$listeners" | grep -v "^COMMAND" || true

            if [ "$FORCE_MODE" = true ]; then
                warn "Force mode: killing processes on port $port"
                # Extract PIDs and kill them
                echo "$listeners" | grep -v "^COMMAND" | awk '{print $2}' | sort -u | while read -r pid; do
                    if [ -n "$pid" ]; then
                        kill -TERM "$pid" 2>/dev/null || true
                        sleep 0.5
                        if ps -p "$pid" >/dev/null 2>&1; then
                            kill -KILL "$pid" 2>/dev/null || true
                        fi
                    fi
                done
                success "Killed processes on port $port"
            else
                info "To force-kill these processes, run: $0 --force"
                info "Or manually: lsof -iTCP:$port -sTCP:LISTEN -t | xargs kill"
            fi
            return 1
        else
            success "$service_name port $port is free"
            return 0
        fi
    else
        warn "lsof not available, cannot check port $port"
        return 0
    fi
}

PORT_CLEAN=true
check_port_listeners "$API_PORT" "API" || PORT_CLEAN=false
check_port_listeners "$GATEWAY_PORT" "Gateway" || PORT_CLEAN=false
echo ""

# Show final status
if [ "$API_RUNNING" = "inactive" ] && [ "$GATEWAY_RUNNING" = "inactive" ] && [ "$PORT_CLEAN" = true ]; then
    success "All Milton services stopped cleanly"
else
    warn "Some services or ports may still be active"
    info "Check status: ./scripts/milton_status.sh"
fi
echo ""
