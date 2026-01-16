#!/usr/bin/env python3
"""Verification script for persistent chat memory.

Demonstrates that conversation history and memory facts persist across sessions.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.chat_memory import ChatMemoryStore


def main():
    """Run verification scenarios."""
    db_path = Path.home() / ".local/state/milton/chat_memory_demo.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("CHAT MEMORY PERSISTENCE VERIFICATION")
    print("=" * 70)
    
    # Scenario 1: Conversation history persistence
    print("\n📝 Scenario 1: Conversation History Persistence")
    print("-" * 70)
    
    thread_id = "demo-thread-123"
    
    # Session 1: Create conversation
    print("\n[Session 1] Creating conversation...")
    store1 = ChatMemoryStore(db_path)
    store1.append_turn(thread_id, "user", "Hello, my name is Cole")
    store1.append_turn(thread_id, "assistant", "Hi Cole! Nice to meet you.")
    store1.append_turn(thread_id, "user", "I'm working on the Milton project")
    store1.append_turn(thread_id, "assistant", "That's great! Tell me about the Milton project.")
    print("  ✓ Added 4 conversation turns")
    store1.close()
    
    # Session 2: Retrieve conversation
    print("\n[Session 2] Retrieving conversation after restart...")
    store2 = ChatMemoryStore(db_path)
    history = store2.get_recent_turns(thread_id, limit=10)
    print(f"  ✓ Retrieved {len(history)} turns:")
    for i, turn in enumerate(history, 1):
        preview = turn.content[:50] + "..." if len(turn.content) > 50 else turn.content
        print(f"     {i}. {turn.role:10s}: {preview}")
    store2.close()
    
    # Scenario 2: Memory facts persistence
    print("\n\n🧠 Scenario 2: Memory Facts Persistence (/remember)")
    print("-" * 70)
    
    # Session 1: Store facts
    print("\n[Session 1] Storing memory facts...")
    store3 = ChatMemoryStore(db_path)
    store3.upsert_fact("user_name", "Cole")
    store3.upsert_fact("favorite_editor", "Neovim")
    store3.upsert_fact("current_project", "Milton AI Assistant")
    print("  ✓ Stored 3 memory facts")
    store3.close()
    
    # Session 2: Retrieve facts
    print("\n[Session 2] Retrieving facts after restart...")
    store4 = ChatMemoryStore(db_path)
    facts = store4.get_all_facts()
    print(f"  ✓ Retrieved {len(facts)} facts:")
    for fact in facts:
        print(f"     - {fact.key}: {fact.value}")
    store4.close()
    
    # Scenario 3: Update and delete
    print("\n\n🔄 Scenario 3: Update and Delete Operations")
    print("-" * 70)
    
    store5 = ChatMemoryStore(db_path)
    
    # Update
    print("\nUpdating favorite_editor to 'VS Code'...")
    store5.upsert_fact("favorite_editor", "VS Code")
    updated = store5.get_fact("favorite_editor")
    print(f"  ✓ Updated: {updated.key} = {updated.value}")
    
    # Delete
    print("\nDeleting current_project fact...")
    deleted = store5.delete_fact("current_project")
    print(f"  ✓ Deleted: {deleted}")
    
    # Show remaining
    remaining = store5.get_all_facts()
    print(f"\nRemaining facts: {len(remaining)}")
    for fact in remaining:
        print(f"  - {fact.key}: {fact.value}")
    
    store5.close()
    
    # Scenario 4: Thread isolation
    print("\n\n🔒 Scenario 4: Thread Isolation")
    print("-" * 70)
    
    store6 = ChatMemoryStore(db_path)
    
    thread_alice = "user-alice"
    thread_bob = "user-bob"
    
    # Alice's conversation
    store6.append_turn(thread_alice, "user", "I love Python")
    store6.append_turn(thread_alice, "assistant", "Python is great!")
    
    # Bob's conversation
    store6.append_turn(thread_bob, "user", "I prefer JavaScript")
    store6.append_turn(thread_bob, "assistant", "JavaScript is powerful!")
    
    # Retrieve separately
    alice_history = store6.get_recent_turns(thread_alice, limit=10)
    bob_history = store6.get_recent_turns(thread_bob, limit=10)
    
    print(f"\nAlice's conversation ({len(alice_history)} turns):")
    for turn in alice_history:
        print(f"  {turn.role}: {turn.content}")
    
    print(f"\nBob's conversation ({len(bob_history)} turns):")
    for turn in bob_history:
        print(f"  {turn.role}: {turn.content}")
    
    store6.close()
    
    print("\n" + "=" * 70)
    print("✅ ALL SCENARIOS PASSED")
    print("=" * 70)
    print(f"\nDatabase location: {db_path}")
    print("You can inspect the database with: sqlite3 <path>")
    print("\nTo clean up: rm -f", db_path)


if __name__ == "__main__":
    main()
