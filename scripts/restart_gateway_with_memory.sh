#!/bin/bash
# Restart Milton Gateway to activate chat memory features

set -e

echo "🔄 Restarting Milton Gateway to activate chat memory persistence..."
echo ""

# Find the running gateway process
GATEWAY_PID=$(pgrep -f "start_chat_gateway.py" || echo "")

if [ -n "$GATEWAY_PID" ]; then
    echo "📍 Found gateway running (PID: $GATEWAY_PID)"
    echo "🛑 Stopping gateway..."
    kill $GATEWAY_PID
    
    # Wait for process to stop
    for i in {1..10}; do
        if ! ps -p $GATEWAY_PID > /dev/null 2>&1; then
            echo "✅ Gateway stopped"
            break
        fi
        echo "   Waiting for shutdown... ($i/10)"
        sleep 1
    done
    
    # Force kill if still running
    if ps -p $GATEWAY_PID > /dev/null 2>&1; then
        echo "⚠️  Force stopping..."
        kill -9 $GATEWAY_PID
        sleep 1
    fi
else
    echo "ℹ️  Gateway not currently running"
fi

echo ""
echo "🚀 Starting gateway with new memory features..."

# Start the gateway (assuming you want to run it in background)
cd /home/cole-hanan/milton
nohup python scripts/start_chat_gateway.py > logs/gateway.log 2>&1 &
NEW_PID=$!

sleep 2

# Check if it started successfully
if ps -p $NEW_PID > /dev/null 2>&1; then
    echo "✅ Gateway started successfully (PID: $NEW_PID)"
    echo ""
    echo "📋 Gateway is now running with:"
    echo "   - Persistent conversation memory"
    echo "   - /remember and /memory commands"
    echo "   - Thread-specific history (auto-loads last 10 turns)"
    echo ""
    echo "🌐 Access via: http://100.117.64.117:3000/"
    echo "📄 Logs: tail -f logs/gateway.log"
    echo ""
    echo "💡 Try it out:"
    echo "   1. Chat: 'My name is Cole'"
    echo "   2. Use: /remember favorite_language: Python"
    echo "   3. Close and reopen chat"
    echo "   4. Ask: 'What's my name?' or use: /memory show"
else
    echo "❌ Gateway failed to start. Check logs/gateway.log"
    exit 1
fi
