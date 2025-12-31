#!/bin/bash
set -e

echo "========================================"
echo "Milton Orchestrator Service Installation"
echo "========================================"
echo ""

# Detect installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$INSTALL_DIR/venv"

# Check that venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please run install.sh first"
    exit 1
fi

# Check that .env exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Warning: .env file not found at $INSTALL_DIR/.env"
    echo "The service will not start without proper configuration."
    echo ""
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create systemd user directory
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

# Generate service file
SERVICE_FILE="$SYSTEMD_USER_DIR/milton-orchestrator.service"

echo "Creating systemd service file: $SERVICE_FILE"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Milton Orchestrator - Voice-to-Code System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_DIR/bin/milton-orchestrator
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

echo "Service file created successfully"
echo ""

# Reload systemd
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo ""
echo "========================================"
echo "Service installation complete!"
echo "========================================"
echo ""
echo "Service management commands:"
echo "  Start:   systemctl --user start milton-orchestrator"
echo "  Stop:    systemctl --user stop milton-orchestrator"
echo "  Status:  systemctl --user status milton-orchestrator"
echo "  Logs:    journalctl --user -u milton-orchestrator -f"
echo "  Enable:  systemctl --user enable milton-orchestrator"
echo "  Disable: systemctl --user disable milton-orchestrator"
echo ""
echo "To enable the service at login:"
echo "  systemctl --user enable milton-orchestrator"
echo ""
echo "To start the service now:"
echo "  systemctl --user start milton-orchestrator"
echo ""
