#!/usr/bin/env bash
set -euo pipefail

# Milton startup script - installs and starts systemd user services
# Replaces manual process management with proper systemd services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MILTON_REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source environment configuration
if [ -f "$SCRIPT_DIR/milton.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/milton.env"
else
    echo "❌ Error: scripts/milton.env not found"
    exit 1
fi

# Color output helpers
info() { echo "ℹ️  $*"; }
success() { echo "✅ $*"; }
error() { echo "❌ $*" >&2; }
warn() { echo "⚠️  $*"; }

# Detect Python executable
detect_python() {
    local python_exe=""

    # Check for venv in common locations
    if [ -x "$MILTON_REPO_DIR/venv/bin/python" ]; then
        python_exe="$MILTON_REPO_DIR/venv/bin/python"
        info "Detected virtualenv at venv/bin/python" >&2
    elif [ -x "$MILTON_REPO_DIR/.venv/bin/python" ]; then
        python_exe="$MILTON_REPO_DIR/.venv/bin/python"
        info "Detected virtualenv at .venv/bin/python" >&2
    elif command -v python3 >/dev/null 2>&1; then
        python_exe="$(command -v python3)"
        warn "No virtualenv found, using system python3: $python_exe" >&2
    elif command -v python >/dev/null 2>&1; then
        python_exe="$(command -v python)"
        warn "No virtualenv found, using system python: $python_exe" >&2
    else
        error "No Python executable found" >&2
        error "Install Python or activate a virtualenv" >&2
        exit 1
    fi

    echo "$python_exe"
}

# Install systemd service unit
install_service() {
    local template_file=$1
    local service_name=$2
    local python_exe=$3

    local user_systemd_dir="$HOME/.config/systemd/user"
    mkdir -p "$user_systemd_dir"

    local service_file="$user_systemd_dir/${service_name}.service"

    info "Installing $service_name.service..."

    # Substitute placeholders
    sed -e "s|{{MILTON_REPO_DIR}}|$MILTON_REPO_DIR|g" \
        -e "s|{{MILTON_STATE_DIR}}|$MILTON_STATE_DIR|g" \
        -e "s|{{PYTHON_EXECUTABLE}}|$python_exe|g" \
        "$template_file" > "$service_file"

    success "Installed $service_file"
}

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                   MILTON SYSTEMD SERVICE SETUP                        ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# Detect Python
PYTHON_EXE=$(detect_python)
info "Using Python: $PYTHON_EXE"
echo ""

# Verify Python works
if ! "$PYTHON_EXE" --version >/dev/null 2>&1; then
    error "Python executable is not working: $PYTHON_EXE"
    exit 1
fi

# Ensure state and log directories exist
mkdir -p "$MILTON_STATE_DIR/logs"
success "State directory: $MILTON_STATE_DIR"
echo ""

# Install service files
info "Installing systemd service units..."
install_service "$SCRIPT_DIR/systemd/milton-api.service.template" "milton-api" "$PYTHON_EXE"
install_service "$SCRIPT_DIR/systemd/milton-gateway.service.template" "milton-gateway" "$PYTHON_EXE"
echo ""

# Reload systemd user daemon
info "Reloading systemd user daemon..."
systemctl --user daemon-reload
success "systemd daemon reloaded"
echo ""

# Stop any running services first (clean slate)
info "Stopping any existing Milton services..."
systemctl --user stop milton-gateway.service 2>/dev/null || true
systemctl --user stop milton-api.service 2>/dev/null || true
sleep 1
echo ""

# Enable and start services
info "Enabling and starting Milton services..."
systemctl --user enable milton-api.service
systemctl --user enable milton-gateway.service
systemctl --user start milton-api.service
echo ""

# Wait for API to be healthy before starting gateway
info "Waiting for API server to become healthy..."
for i in {1..15}; do
    if curl -fsS "$MILTON_API_URL/health" >/dev/null 2>&1; then
        success "API server is healthy"
        break
    fi
    if [ $i -eq 15 ]; then
        error "API server failed to become healthy after 15 seconds"
        error "Check logs: journalctl --user -u milton-api -n 100 --no-pager"
        exit 1
    fi
    sleep 1
done
echo ""

# Start gateway
systemctl --user start milton-gateway.service
echo ""

# Wait for Gateway to be healthy
info "Waiting for Gateway to become healthy..."
for i in {1..15}; do
    if curl -fsS "$GATEWAY_URL/health" >/dev/null 2>&1; then
        success "Gateway is healthy"
        break
    fi
    if [ $i -eq 15 ]; then
        error "Gateway failed to become healthy after 15 seconds"
        error "Check logs: journalctl --user -u milton-gateway -n 100 --no-pager"
        exit 1
    fi
    sleep 1
done
echo ""

success "All Milton services started successfully!"
echo ""
echo "Service Status:"
systemctl --user status milton-api.service milton-gateway.service --no-pager || true
echo ""
echo "Effective Configuration:"
echo "  State Directory:  $MILTON_STATE_DIR"
echo "  API Server:       $MILTON_API_URL"
echo "  Gateway:          $GATEWAY_URL"
echo "  LLM Backend:      $LLM_API_URL"
echo "  Weaviate:         $WEAVIATE_URL"
echo ""
echo "Logs:"
echo "  API:     journalctl --user -u milton-api -f"
echo "  Gateway: journalctl --user -u milton-gateway -f"
echo "  Or file: $MILTON_STATE_DIR/logs/milton-{api,gateway}.log"
echo ""
echo "Next Steps:"
echo "  1. Run smoke tests:    ./scripts/milton_smoke.sh"
echo "  2. Check status:       ./scripts/milton_status.sh"
echo "  3. Stop services:      ./scripts/milton_down.sh"
echo ""
