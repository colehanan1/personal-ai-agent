import json
from unittest.mock import MagicMock

from memory.backends import WeaviateBackend
from memory.schema import MemoryItem, UserProfile


def test_weaviate_backend_add_memory_calls_insert():
    short_collection = MagicMock()
    short_collection.data.insert.return_value = "uuid-123"

    client = MagicMock()
    client.collections.get.return_value = short_collection

    backend = WeaviateBackend(client)
    item = MemoryItem(
        id="mem-1",
        agent="NEXUS",
        type="fact",
        content="Test content",
        tags=["alpha"],
        importance=0.5,
        source="chat",
        evidence=["file.txt"],
    )

    memory_id = backend.append_short_term(item)
    assert memory_id == "uuid-123"
    client.collections.get.assert_called_with("ShortTermMemory")

    _args, kwargs = short_collection.data.insert.call_args
    props = kwargs["properties"]
    metadata = json.loads(props["metadata"])
    assert metadata["type"] == "fact"
    assert metadata["tags"] == ["alpha"]
    assert metadata["evidence"] == ["file.txt"]


def test_weaviate_backend_upsert_profile_calls_insert():
    long_collection = MagicMock()

    client = MagicMock()
    client.collections.get.return_value = long_collection

    backend = WeaviateBackend(client)
    profile = UserProfile(
        preferences=["dark mode"],
        stable_facts=["uses milton"],
        do_not_assume=[],
        evidence_ids=["mem-1"],
    )

    backend.upsert_user_profile(profile)
    client.collections.get.assert_called_with("LongTermMemory")
    assert long_collection.data.insert.called
