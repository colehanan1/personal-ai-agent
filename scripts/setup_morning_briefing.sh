#!/bin/bash
# Setup automatic morning briefing with systemd timer

echo "════════════════════════════════════════════════════════════════════"
echo "MILTON MORNING BRIEFING SETUP"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Create systemd user directory
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

# Create service file
echo "Creating systemd service..."
cat > "$SYSTEMD_DIR/milton-morning-briefing.service" << 'EOF'
[Unit]
Description=Milton PhD-Aware Morning Briefing
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/cole-hanan/milton
Environment="PATH=/home/cole-hanan/miniconda3/envs/milton/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/cole-hanan/milton/scripts/phd_aware_morning_briefing.py
StandardOutput=journal
StandardError=journal
TimeoutStartSec=300
EOF

# Create timer file
echo "Creating systemd timer (runs at 8:00 AM daily)..."
cat > "$SYSTEMD_DIR/milton-morning-briefing.timer" << 'EOF'
[Unit]
Description=Milton Morning Briefing Timer
Requires=milton-morning-briefing.service

[Timer]
OnCalendar=*-*-* 08:00:00
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Reload systemd
echo "Reloading systemd..."
systemctl --user daemon-reload

# Enable and start timer
echo "Enabling timer..."
systemctl --user enable milton-morning-briefing.timer
systemctl --user start milton-morning-briefing.timer

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "✓ SETUP COMPLETE"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "Morning briefing will run automatically at 8:00 AM daily"
echo ""
echo "USEFUL COMMANDS:"
echo "  Check timer status:  systemctl --user list-timers milton*"
echo "  Run now:             systemctl --user start milton-morning-briefing.service"
echo "  View logs:           journalctl --user -u milton-morning-briefing.service"
echo "  Disable:             systemctl --user disable milton-morning-briefing.timer"
echo "  Manual run:          ./scripts/phd_aware_morning_briefing.py"
echo ""
echo "BRIEFING LOCATION:"
echo "  inbox/morning/enhanced_brief_latest.json"
echo ""
echo "════════════════════════════════════════════════════════════════════"
