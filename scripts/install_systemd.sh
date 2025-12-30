#!/usr/bin/env bash
#
# Install Milton systemd timers and services
# Run as regular user (NOT root/sudo)
#

set -e

MILTON_ROOT="/home/cole-hanan/milton"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "==================================================================="
echo "Milton Phase 2: Installing systemd automation"
echo "==================================================================="

# Create systemd user directory
echo "[1/4] Creating systemd user directory..."
mkdir -p "$SYSTEMD_USER_DIR"

# Copy service and timer files
echo "[2/4] Copying systemd unit files..."
cp -v "${MILTON_ROOT}/systemd/"*.service "$SYSTEMD_USER_DIR/"
cp -v "${MILTON_ROOT}/systemd/"*.timer "$SYSTEMD_USER_DIR/"

# Reload systemd daemon
echo "[3/4] Reloading systemd daemon..."
systemctl --user daemon-reload

# Enable timers
echo "[4/4] Enabling timers..."
systemctl --user enable milton-nexus-morning.timer
systemctl --user enable milton-frontier-morning.timer
systemctl --user enable milton-job-processor.timer

echo ""
echo "==================================================================="
echo "✓ Installation complete!"
echo "==================================================================="
echo ""
echo "To start timers NOW:"
echo "  systemctl --user start milton-nexus-morning.timer"
echo "  systemctl --user start milton-frontier-morning.timer"
echo "  systemctl --user start milton-job-processor.timer"
echo ""
echo "To check timer status:"
echo "  systemctl --user list-timers --all | grep milton"
echo ""
echo "To view logs:"
echo "  journalctl --user -u milton-nexus-morning.service -f"
echo "  journalctl --user -u milton-frontier-morning.service -f"
echo "  journalctl --user -u milton-job-processor.service -f"
echo ""
echo "Timer schedules:"
echo "  - Morning briefing: Daily at 8:00 AM"
echo "  - Research discovery: Daily at 8:15 AM"
echo "  - Job processor: Every 30 min from 10 PM to 6 AM"
echo "==================================================================="
