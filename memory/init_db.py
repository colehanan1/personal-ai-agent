"""
Weaviate Database Initialization
Creates schema for short-term, working, and long-term memory.
"""
import weaviate
from weaviate.classes.config import Configure, Property, DataType
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")


def get_client() -> weaviate.WeaviateClient:
    """
    Get Weaviate client instance.

    Returns:
        Configured Weaviate client
    """
    client = weaviate.connect_to_local(host="localhost", port=8080)
    return client


def create_schema(client: Optional[weaviate.WeaviateClient] = None) -> None:
    """
    Create memory schema in Weaviate.

    Creates three collections:
    - ShortTermMemory: Recent interactions (24-48 hours)
    - WorkingMemory: Active context for ongoing tasks
    - LongTermMemory: Compressed, important historical data

    Args:
        client: Weaviate client instance (optional, creates new if not provided)
    """
    close_client = False
    if client is None:
        client = get_client()
        close_client = True

    try:
        # Short-term memory schema
        if not client.collections.exists("ShortTermMemory"):
            client.collections.create(
                name="ShortTermMemory",
                description="Recent interactions and events (24-48 hours)",
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="agent", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="context", data_type=DataType.TEXT),
                    Property(name="metadata", data_type=DataType.OBJECT),
                ],
            )
            print("Created ShortTermMemory schema")

        # Working memory schema
        if not client.collections.exists("WorkingMemory"):
            client.collections.create(
                name="WorkingMemory",
                description="Active context for ongoing tasks",
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="task_id", data_type=DataType.TEXT),
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="agent", data_type=DataType.TEXT),
                    Property(name="task_type", data_type=DataType.TEXT),
                    Property(name="status", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="dependencies", data_type=DataType.TEXT_ARRAY),
                    Property(name="metadata", data_type=DataType.OBJECT),
                ],
            )
            print("Created WorkingMemory schema")

        # Long-term memory schema
        if not client.collections.exists("LongTermMemory"):
            client.collections.create(
                name="LongTermMemory",
                description="Compressed historical data and learnings",
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="category", data_type=DataType.TEXT),
                    Property(name="summary", data_type=DataType.TEXT),
                    Property(name="importance", data_type=DataType.NUMBER),
                    Property(name="tags", data_type=DataType.TEXT_ARRAY),
                    Property(name="metadata", data_type=DataType.OBJECT),
                ],
            )
            print("Created LongTermMemory schema")

        print("\nWeaviate schema initialization complete")

    finally:
        if close_client:
            client.close()


def reset_schema(client: Optional[weaviate.WeaviateClient] = None) -> None:
    """
    Delete and recreate all memory collections.

    WARNING: This will delete all stored memories.

    Args:
        client: Weaviate client instance (optional)
    """
    close_client = False
    if client is None:
        client = get_client()
        close_client = True

    try:
        for collection in ["ShortTermMemory", "WorkingMemory", "LongTermMemory"]:
            if client.collections.exists(collection):
                client.collections.delete(collection)
                print(f"Deleted {collection}")

        create_schema(client)

    finally:
        if close_client:
            client.close()


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        print("WARNING: This will delete all memories!")
        response = input("Type 'yes' to confirm: ")
        if response.lower() == "yes":
            reset_schema()
        else:
            print("Aborted")
    else:
        create_schema()
