"""Tests for chat memory store functionality."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from storage.chat_memory import ChatMemoryStore, ConversationTurn, MemoryFact


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def store(temp_db):
    """Create a ChatMemoryStore instance for testing."""
    return ChatMemoryStore(temp_db)


class TestConversationTurns:
    """Tests for conversation turn storage and retrieval."""

    def test_append_turn(self, store):
        """Test storing a conversation turn."""
        turn_id = store.append_turn(
            thread_id="test-123",
            role="user",
            content="Hello Milton"
        )
        assert turn_id > 0

    def test_append_turn_validates_role(self, store):
        """Test that invalid roles are rejected."""
        with pytest.raises(ValueError, match="Invalid role"):
            store.append_turn(
                thread_id="test-123",
                role="invalid",
                content="Test"
            )

    def test_append_turn_validates_content(self, store):
        """Test that empty content is rejected."""
        with pytest.raises(ValueError, match="Content cannot be empty"):
            store.append_turn(
                thread_id="test-123",
                role="user",
                content=""
            )

    def test_get_recent_turns_empty(self, store):
        """Test retrieving turns from empty thread."""
        turns = store.get_recent_turns("nonexistent-thread")
        assert len(turns) == 0

    def test_get_recent_turns_chronological(self, store):
        """Test that turns are returned in chronological order."""
        thread_id = "test-order"
        
        # Add turns in sequence
        store.append_turn(thread_id, "user", "First message")
        store.append_turn(thread_id, "assistant", "First response")
        store.append_turn(thread_id, "user", "Second message")
        store.append_turn(thread_id, "assistant", "Second response")
        
        turns = store.get_recent_turns(thread_id)
        
        assert len(turns) == 4
        assert turns[0].content == "First message"
        assert turns[1].content == "First response"
        assert turns[2].content == "Second message"
        assert turns[3].content == "Second response"

    def test_get_recent_turns_respects_limit(self, store):
        """Test that limit parameter works correctly."""
        thread_id = "test-limit"
        
        # Add 5 turns
        for i in range(5):
            store.append_turn(thread_id, "user", f"Message {i}")
        
        # Request only 3 most recent
        turns = store.get_recent_turns(thread_id, limit=3)
        
        assert len(turns) == 3
        # Should get the 3 most recent (2, 3, 4)
        assert turns[0].content == "Message 2"
        assert turns[1].content == "Message 3"
        assert turns[2].content == "Message 4"

    def test_get_recent_turns_isolates_threads(self, store):
        """Test that turns are isolated by thread_id."""
        store.append_turn("thread-a", "user", "Thread A message")
        store.append_turn("thread-b", "user", "Thread B message")
        
        turns_a = store.get_recent_turns("thread-a")
        turns_b = store.get_recent_turns("thread-b")
        
        assert len(turns_a) == 1
        assert len(turns_b) == 1
        assert turns_a[0].content == "Thread A message"
        assert turns_b[0].content == "Thread B message"


class TestMemoryFacts:
    """Tests for memory fact storage and retrieval."""

    def test_upsert_fact_insert(self, store):
        """Test inserting a new fact."""
        fact_id = store.upsert_fact("name", "Cole")
        assert fact_id > 0
        
        fact = store.get_fact("name")
        assert fact is not None
        assert fact.key == "name"
        assert fact.value == "Cole"

    def test_upsert_fact_update(self, store):
        """Test updating an existing fact."""
        store.upsert_fact("favorite_color", "blue")
        store.upsert_fact("favorite_color", "green")
        
        fact = store.get_fact("favorite_color")
        assert fact.value == "green"  # Updated value

    def test_upsert_fact_case_insensitive(self, store):
        """Test that fact keys are case-insensitive."""
        store.upsert_fact("NAME", "Cole")
        
        # Retrieve with different case
        fact = store.get_fact("name")
        assert fact is not None
        assert fact.value == "Cole"
        
        # Update with different case
        store.upsert_fact("Name", "Cole Hanan")
        fact = store.get_fact("NAME")
        assert fact.value == "Cole Hanan"

    def test_upsert_fact_validates_key(self, store):
        """Test that empty keys are rejected."""
        with pytest.raises(ValueError, match="Key cannot be empty"):
            store.upsert_fact("", "value")

    def test_upsert_fact_validates_value(self, store):
        """Test that empty values are rejected."""
        with pytest.raises(ValueError, match="Value cannot be empty"):
            store.upsert_fact("key", "")

    def test_get_fact_not_found(self, store):
        """Test retrieving a non-existent fact."""
        fact = store.get_fact("nonexistent")
        assert fact is None

    def test_get_all_facts_empty(self, store):
        """Test retrieving facts from empty store."""
        facts = store.get_all_facts()
        assert len(facts) == 0

    def test_get_all_facts_multiple(self, store):
        """Test retrieving multiple facts."""
        store.upsert_fact("name", "Cole")
        store.upsert_fact("favorite_editor", "Neovim")
        store.upsert_fact("favorite_language", "Python")
        
        facts = store.get_all_facts()
        assert len(facts) == 3
        
        # Should be ordered by key
        keys = [f.key for f in facts]
        assert keys == sorted(keys)

    def test_delete_fact_exists(self, store):
        """Test deleting an existing fact."""
        store.upsert_fact("temp", "value")
        
        deleted = store.delete_fact("temp")
        assert deleted is True
        
        # Verify it's gone
        fact = store.get_fact("temp")
        assert fact is None

    def test_delete_fact_not_found(self, store):
        """Test deleting a non-existent fact."""
        deleted = store.delete_fact("nonexistent")
        assert deleted is False

    def test_delete_fact_case_insensitive(self, store):
        """Test that deletion is case-insensitive."""
        store.upsert_fact("TEST", "value")
        
        deleted = store.delete_fact("test")
        assert deleted is True
        
        fact = store.get_fact("TEST")
        assert fact is None


class TestIntegration:
    """Integration tests for combined functionality."""

    def test_mixed_operations(self, store):
        """Test a realistic sequence of operations."""
        thread_id = "session-123"
        
        # Initial conversation
        store.append_turn(thread_id, "user", "What's my name?")
        store.append_turn(thread_id, "assistant", "I don't know your name yet.")
        
        # User teaches the assistant
        store.append_turn(thread_id, "user", "/remember name: Cole")
        store.upsert_fact("name", "Cole")
        store.append_turn(thread_id, "assistant", "✅ Remembered: **name** = Cole")
        
        # Later in conversation
        store.append_turn(thread_id, "user", "What's my name?")
        
        # Load context
        turns = store.get_recent_turns(thread_id)
        facts = store.get_all_facts()
        
        assert len(turns) == 5
        assert len(facts) == 1
        assert facts[0].key == "name"
        assert facts[0].value == "Cole"
        
        # Assistant can now answer
        store.append_turn(thread_id, "assistant", "Your name is Cole.")

    def test_thread_isolation_with_facts(self, store):
        """Test that conversation threads are isolated but facts are shared."""
        # Thread 1
        store.append_turn("thread-1", "user", "/remember city: Boston")
        store.upsert_fact("city", "Boston")
        
        # Thread 2 can access the same fact
        facts = store.get_all_facts()
        assert len(facts) == 1
        assert facts[0].value == "Boston"
        
        # But threads have separate conversation history
        store.append_turn("thread-2", "user", "What city am I in?")
        
        turns_1 = store.get_recent_turns("thread-1")
        turns_2 = store.get_recent_turns("thread-2")
        
        assert len(turns_1) == 1
        assert len(turns_2) == 1
        assert turns_1[0].thread_id == "thread-1"
        assert turns_2[0].thread_id == "thread-2"


class TestDataclasses:
    """Tests for dataclass functionality."""

    def test_conversation_turn_to_dict(self, store):
        """Test ConversationTurn serialization."""
        turn_id = store.append_turn("test", "user", "Hello")
        turns = store.get_recent_turns("test")
        
        turn_dict = turns[0].to_dict()
        
        assert turn_dict["id"] == turn_id
        assert turn_dict["thread_id"] == "test"
        assert turn_dict["role"] == "user"
        assert turn_dict["content"] == "Hello"
        assert "created_at" in turn_dict

    def test_memory_fact_to_dict(self, store):
        """Test MemoryFact serialization."""
        store.upsert_fact("key", "value")
        facts = store.get_all_facts()
        
        fact_dict = facts[0].to_dict()
        
        assert fact_dict["key"] == "key"
        assert fact_dict["value"] == "value"
        assert "created_at" in fact_dict
        assert "updated_at" in fact_dict


class TestConcurrency:
    """Tests for thread safety (basic checks)."""

    def test_concurrent_append(self, store):
        """Test that concurrent appends don't cause issues."""
        # This is a basic check - full concurrency testing would require threading
        thread_id = "concurrent-test"
        
        for i in range(10):
            store.append_turn(thread_id, "user", f"Message {i}")
        
        turns = store.get_recent_turns(thread_id)
        assert len(turns) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
