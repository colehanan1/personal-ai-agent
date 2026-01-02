#!/bin/bash
# Setup automatic phone delivery for morning briefing

echo "════════════════════════════════════════════════════════════════════"
echo "SETUP IPHONE BRIEFING DELIVERY"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "This will configure your morning briefing to automatically send to"
echo "your iPhone via push notification every morning at 8 AM."
echo ""

# Ask for ntfy topic
read -p "Enter your ntfy.sh topic name (e.g., milton-briefing-cole): " NTFY_TOPIC

if [ -z "$NTFY_TOPIC" ]; then
    echo "❌ Error: Topic name cannot be empty"
    exit 1
fi

# Add to .env if not already there
if ! grep -q "NTFY_TOPIC" .env 2>/dev/null; then
    echo "" >> .env
    echo "# Push notifications" >> .env
    echo "NTFY_TOPIC=$NTFY_TOPIC" >> .env
    echo "✅ Added NTFY_TOPIC to .env"
else
    # Update existing
    sed -i "s/^NTFY_TOPIC=.*/NTFY_TOPIC=$NTFY_TOPIC/" .env
    echo "✅ Updated NTFY_TOPIC in .env"
fi

# Update systemd service
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_DIR/milton-morning-briefing.service"

echo ""
echo "Updating systemd service to send notifications..."

cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=Milton PhD-Aware Morning Briefing
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/cole-hanan/milton
Environment="STATE_DIR=%h/.local/state/milton"
Environment="PATH=/home/cole-hanan/miniconda3/envs/milton/bin:/usr/local/bin:/usr/bin"
ExecStart=/bin/bash -c '/home/cole-hanan/milton/scripts/phd_aware_morning_briefing.py && /home/cole-hanan/milton/scripts/send_briefing_to_phone.py --method ntfy'
StandardOutput=journal
StandardError=journal
TimeoutStartSec=300
EOF

# Reload systemd
systemctl --user daemon-reload

echo "✅ Service updated"
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "NEXT STEPS"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "1. Install ntfy app on your iPhone from the App Store"
echo "2. Subscribe to topic: $NTFY_TOPIC"
echo "3. Test the delivery:"
echo ""
echo "   ./scripts/send_briefing_to_phone.py --method ntfy"
echo ""
echo "4. Your briefing will automatically be sent to your iPhone every"
echo "   morning at 8:00 AM!"
echo ""
echo "For full setup instructions, see:"
echo "   IPHONE_BRIEFING_SETUP.md"
echo ""
echo "════════════════════════════════════════════════════════════════════"
