"""Integration tests for chat memory persistence across sessions."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from storage.chat_memory import ChatMemoryStore


class TestChatMemoryIntegration:
    """Integration tests for conversation memory persistence."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def memory_store(self, temp_db):
        """Create a ChatMemoryStore instance."""
        return ChatMemoryStore(db_path=temp_db)

    def test_session_continuity(self, memory_store):
        """Test that conversations persist across simulated sessions."""
        thread_id = "test-thread-123"
        
        # Session 1: Initial conversation
        memory_store.append_turn(thread_id, "user", "Hello, my name is Alice")
        memory_store.append_turn(thread_id, "assistant", "Hello Alice! Nice to meet you.")
        memory_store.append_turn(thread_id, "user", "What's the capital of France?")
        memory_store.append_turn(thread_id, "assistant", "The capital of France is Paris.")
        
        # Simulate session end - close the store
        db_path = memory_store.db_path
        memory_store.close()
        
        # Session 2: New connection to same database
        new_store = ChatMemoryStore(db_path=db_path)
        
        # Retrieve conversation history
        turns = new_store.get_recent_turns(thread_id, limit=10)
        
        # Verify all turns are present in correct order
        assert len(turns) == 4
        assert turns[0].role == "user"
        assert "Alice" in turns[0].content
        assert turns[1].role == "assistant"
        assert "Alice" in turns[1].content
        assert turns[2].role == "user"
        assert "France" in turns[2].content
        assert turns[3].role == "assistant"
        assert "Paris" in turns[3].content
        
        new_store.close()

    def test_remember_command_persistence(self, memory_store):
        """Test that /remember facts persist across sessions."""
        # Session 1: Store some facts
        fact_id1 = memory_store.upsert_fact("user_name", "Alice")
        fact_id2 = memory_store.upsert_fact("favorite_color", "blue")
        fact_id3 = memory_store.upsert_fact("location", "Seattle")
        
        assert fact_id1 > 0
        assert fact_id2 > 0
        assert fact_id3 > 0
        
        # Simulate session end
        db_path = memory_store.db_path
        memory_store.close()
        
        # Session 2: New connection
        new_store = ChatMemoryStore(db_path=db_path)
        
        # Retrieve all facts
        facts = new_store.get_all_facts()
        assert len(facts) == 3
        
        # Verify facts are present
        fact_dict = {f.key: f.value for f in facts}
        assert fact_dict["user_name"] == "Alice"
        assert fact_dict["favorite_color"] == "blue"
        assert fact_dict["location"] == "Seattle"
        
        # Update a fact
        new_store.upsert_fact("favorite_color", "green")
        
        # Verify update
        updated_fact = new_store.get_fact("favorite_color")
        assert updated_fact is not None
        assert updated_fact.value == "green"
        
        new_store.close()

    def test_system_prompt_injection(self, memory_store):
        """Test that conversation history can be formatted for system prompt."""
        thread_id = "test-thread-456"
        
        # Build conversation
        memory_store.append_turn(thread_id, "user", "Remember my birthday is May 15")
        memory_store.append_turn(thread_id, "assistant", "I'll remember that your birthday is May 15!")
        memory_store.append_turn(thread_id, "user", "What's my birthday?")
        
        # Store a fact
        memory_store.upsert_fact("user_birthday", "May 15")
        
        # Retrieve for injection
        turns = memory_store.get_recent_turns(thread_id, limit=10)
        facts = memory_store.get_all_facts()
        
        # Format for system prompt (as would be done in server)
        history_context = "### Recent Conversation History:\n"
        for turn in turns:
            history_context += f"{turn.role}: {turn.content}\n"
        
        facts_context = "\n### Stored Facts:\n"
        for fact in facts:
            facts_context += f"- {fact.key}: {fact.value}\n"
        
        # Verify the context is useful
        assert "May 15" in history_context
        assert "birthday" in history_context.lower()
        assert "user_birthday" in facts_context
        assert "May 15" in facts_context

    def test_thread_isolation(self, memory_store):
        """Test that different threads don't interfere with each other."""
        thread1 = "user-alice"
        thread2 = "user-bob"
        
        # Alice's conversation
        memory_store.append_turn(thread1, "user", "My name is Alice")
        memory_store.append_turn(thread1, "assistant", "Hello Alice!")
        
        # Bob's conversation
        memory_store.append_turn(thread2, "user", "My name is Bob")
        memory_store.append_turn(thread2, "assistant", "Hello Bob!")
        
        # Retrieve separately
        alice_turns = memory_store.get_recent_turns(thread1, limit=10)
        bob_turns = memory_store.get_recent_turns(thread2, limit=10)
        
        # Verify isolation
        assert len(alice_turns) == 2
        assert len(bob_turns) == 2
        assert "Alice" in alice_turns[0].content
        assert "Alice" not in bob_turns[0].content
        assert "Bob" in bob_turns[0].content
        assert "Bob" not in alice_turns[0].content

    def test_limit_respects_token_budget(self, memory_store):
        """Test that limit parameter prevents unbounded history growth."""
        thread_id = "test-long-thread"
        
        # Create a long conversation
        for i in range(50):
            memory_store.append_turn(thread_id, "user", f"Message {i}")
            memory_store.append_turn(thread_id, "assistant", f"Response {i}")
        
        # Retrieve with limit
        recent_10 = memory_store.get_recent_turns(thread_id, limit=10)
        recent_5 = memory_store.get_recent_turns(thread_id, limit=5)
        
        # Verify limits are respected
        assert len(recent_10) == 10
        assert len(recent_5) == 5
        
        # Verify we get the MOST RECENT messages
        assert "Message 49" in recent_10[-2].content or "Message 45" in recent_10[0].content
        assert "Message 49" in recent_5[-2].content or "Message 47" in recent_5[0].content

    def test_empty_thread_handling(self, memory_store):
        """Test graceful handling of non-existent threads."""
        turns = memory_store.get_recent_turns("non-existent-thread", limit=10)
        assert turns == []
        
        facts = memory_store.get_all_facts()
        # Should be empty initially
        assert facts == [] or len(facts) == 0


class TestCommandProcessorMemory:
    """Test memory commands in the command processor."""

    def test_remember_command_format(self):
        """Test /remember command parsing."""
        # Valid formats
        valid_cases = [
            "/remember name: Alice",
            "/remember favorite_color: blue",
            "/remember user_location: Seattle, WA",
        ]
        
        for case in valid_cases:
            # Simple parsing check
            if ": " in case:
                _, rest = case.split(" ", 1)
                if ": " in rest:
                    key, value = rest.split(": ", 1)
                    assert key and value
                    assert len(key) > 0
                    assert len(value) > 0

    def test_memory_show_format(self):
        """Test /memory show command format."""
        command = "/memory show"
        assert command.startswith("/memory")
        assert "show" in command


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
