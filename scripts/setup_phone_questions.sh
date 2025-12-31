#!/bin/bash
# Setup bidirectional communication with iPhone

echo "════════════════════════════════════════════════════════════════════"
echo "SETUP IPHONE QUESTIONS (ASK MILTON FROM YOUR PHONE)"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "This will set up a listener service that lets you ask Milton questions"
echo "from your iPhone and get AI responses sent back to you."
echo ""

# Get topic from .env
NTFY_TOPIC=$(grep "NTFY_TOPIC=" .env 2>/dev/null | cut -d'=' -f2)

if [ -z "$NTFY_TOPIC" ]; then
    echo "❌ Error: NTFY_TOPIC not set in .env"
    echo "   Run: ./scripts/setup_phone_delivery.sh first"
    exit 1
fi

QUESTIONS_TOPIC="${NTFY_TOPIC}-ask"

echo "Your topics:"
echo "  Briefings:  $NTFY_TOPIC"
echo "  Questions:  $QUESTIONS_TOPIC"
echo ""

# Create systemd service
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

echo "Creating systemd service..."
cat > "$SYSTEMD_DIR/milton-phone-listener.service" << EOF
[Unit]
Description=Milton Phone Question Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/cole-hanan/milton
Environment="PATH=/home/cole-hanan/miniconda3/envs/milton/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/cole-hanan/milton/scripts/ask_from_phone.py --listen
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable milton-phone-listener.service
systemctl --user start milton-phone-listener.service

echo "✅ Service created and started"
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "SETUP COMPLETE"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "📱 HOW TO USE FROM YOUR IPHONE:"
echo ""
echo "Method 1: Using ntfy App Actions (Easiest)"
echo "  1. Open ntfy app on iPhone"
echo "  2. Subscribe to: $QUESTIONS_TOPIC"
echo "  3. Tap the topic"
echo "  4. Use the 'Send' button or input field to send your question"
echo "  5. Wait a few seconds"
echo "  6. Your answer appears in: $NTFY_TOPIC"
echo ""
echo "Method 2: Using iOS Shortcuts"
echo "  - See guide below for setup"
echo ""
echo "Method 3: Using Terminal App (SSH)"
echo "  ssh cole-hanan@[your-ip]"
echo "  ~/bin/briefing              # Get briefing"
echo "  curl -d 'What is the weather?' ntfy.sh/$QUESTIONS_TOPIC  # Ask question"
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "SERVICE COMMANDS"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "  Check status:    systemctl --user status milton-phone-listener"
echo "  View logs:       journalctl --user -u milton-phone-listener -f"
echo "  Stop:            systemctl --user stop milton-phone-listener"
echo "  Start:           systemctl --user start milton-phone-listener"
echo "  Disable:         systemctl --user disable milton-phone-listener"
echo ""
echo "  Manual test:     ./scripts/ask_from_phone.py --listen"
echo ""
echo "════════════════════════════════════════════════════════════════════"
