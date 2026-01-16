#!/bin/bash
# Quick test of chat memory after gateway restart

echo "🧪 Testing Chat Memory Implementation"
echo "======================================"
echo ""

# Wait for gateway to be ready
echo "⏳ Waiting for gateway to be ready..."
for i in {1..10}; do
    if curl -s http://localhost:8081/health > /dev/null 2>&1; then
        echo "✅ Gateway is responding"
        break
    fi
    echo "   Attempt $i/10..."
    sleep 1
done

echo ""
echo "📝 Test 1: Store a conversation turn"
echo "------------------------------------"

# Test conversation storage (this will happen automatically when you chat)
# For now, just verify the database can be created
python3 << 'PYTHON_TEST'
from pathlib import Path
from storage.chat_memory import ChatMemoryStore

db_path = Path.home() / ".local/state/milton/chat_memory.sqlite3"
store = ChatMemoryStore(db_path)

# Test turn storage
test_thread = "test-thread-startup"
store.append_turn(test_thread, "user", "Testing memory persistence")
store.append_turn(test_thread, "assistant", "Memory is working!")

# Test retrieval
turns = store.get_recent_turns(test_thread, limit=10)
print(f"✅ Stored and retrieved {len(turns)} turns")

# Test facts
store.upsert_fact("test_key", "test_value")
fact = store.get_fact("test_key")
print(f"✅ Stored and retrieved fact: {fact.key} = {fact.value}")

# Cleanup test data
store.delete_fact("test_key")
store.close()

print("✅ All basic operations working!")
PYTHON_TEST

echo ""
echo "🎉 Chat memory is ready!"
echo ""
echo "Try these commands in Open WebUI (http://100.117.64.117:3000/):"
echo ""
echo "  1. /remember name: Cole"
echo "  2. /memory show"
echo "  3. Chat normally - history will persist across sessions"
echo ""
echo "Database location: ~/.local/state/milton/chat_memory.sqlite3"
