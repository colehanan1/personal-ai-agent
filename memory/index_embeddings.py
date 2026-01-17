"""
Batch Indexing for Semantic Embeddings

Generates and indexes embeddings for existing memory items in Weaviate.
Supports incremental indexing, dry-run mode, and progress reporting.

Usage:
    python memory/index_embeddings.py [--dry-run] [--batch-size 32] [--force]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
import json
import sys

# Handle both direct execution and module import
if __name__ == "__main__" and __package__ is None:
    # Add parent directory to path for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from memory.backends import get_backend
    from memory.embeddings import embed_batch, is_available, EMBEDDING_DIM
    from memory.init_db import get_client
else:
    from .backends import get_backend
    from .embeddings import embed_batch, is_available, EMBEDDING_DIM
    from .init_db import get_client

logger = logging.getLogger(__name__)


def count_items_without_embeddings(client) -> int:
    """
    Count memory items that don't have embeddings yet.

    Args:
        client: Weaviate client

    Returns:
        Count of items without embeddings
    """
    try:
        collection = client.collections.get("ShortTermMemory")

        # Query all items
        result = collection.query.fetch_objects(limit=10000)

        total = len(result.objects)
        with_vectors = sum(1 for obj in result.objects if obj.vector is not None and len(obj.vector) > 0)
        without_vectors = total - with_vectors

        return without_vectors

    except Exception as e:
        logger.error(f"Failed to count items: {e}")
        return 0


def index_embeddings(
    *,
    batch_size: int = 32,
    dry_run: bool = False,
    force: bool = False,
    repo_root: Optional[Path] = None
) -> Tuple[int, int]:
    """
    Generate and index embeddings for memory items.

    Args:
        batch_size: Number of items to process per batch
        dry_run: If True, only show what would be done
        force: If True, regenerate embeddings even if they exist
        repo_root: Repository root path

    Returns:
        Tuple of (items_processed, items_updated)
    """
    # Check if embeddings are available
    if not is_available():
        logger.error("Embeddings not available. Install sentence-transformers first.")
        print("❌ Embeddings not available")
        print("   Install with: pip install sentence-transformers")
        return (0, 0)

    # Get backend and client
    backend = get_backend(repo_root=repo_root)
    client = get_client()

    try:
        collection = client.collections.get("ShortTermMemory")

        # Fetch all items
        print("Fetching memory items from Weaviate...")
        result = collection.query.fetch_objects(limit=10000)
        items = result.objects

        print(f"Found {len(items)} memory items")

        if dry_run:
            print("\n[DRY RUN MODE - No changes will be made]")

        # Filter items that need embedding
        items_to_process = []
        for item in items:
            has_vector = item.vector is not None and len(item.vector) > 0

            if force or not has_vector:
                items_to_process.append(item)

        print(f"Items to process: {len(items_to_process)}")

        if len(items_to_process) == 0:
            print("✅ All items already have embeddings")
            return (0, 0)

        if dry_run:
            print(f"\nWould generate embeddings for {len(items_to_process)} items")
            print(f"Batch size: {batch_size}")
            print(f"Estimated batches: {(len(items_to_process) + batch_size - 1) // batch_size}")
            return (len(items_to_process), 0)

        # Process in batches
        items_processed = 0
        items_updated = 0

        print(f"\nGenerating embeddings (batch_size={batch_size})...")

        for i in range(0, len(items_to_process), batch_size):
            batch = items_to_process[i:i+batch_size]

            # Extract content for embedding
            texts = []
            for item in batch:
                # Combine content and context for richer embeddings
                text = item.properties.get("content", "")
                context = item.properties.get("context", "")
                combined = f"{text} {context}".strip()
                texts.append(combined if combined else "empty")

            # Generate embeddings
            print(f"  Processing batch {i//batch_size + 1}/{(len(items_to_process) + batch_size - 1) // batch_size}...", end=" ")

            vectors = embed_batch(
                texts,
                batch_size=batch_size,
                show_progress=False
            )

            # Update items with vectors
            success_count = 0
            for item, vector in zip(batch, vectors):
                if vector is not None:
                    try:
                        # Update the item with the embedding vector
                        collection.data.update(
                            uuid=item.uuid,
                            vector=vector.tolist()
                        )
                        success_count += 1
                        items_updated += 1
                    except Exception as e:
                        logger.error(f"Failed to update item {item.uuid}: {e}")

            items_processed += len(batch)
            print(f"✓ {success_count}/{len(batch)} updated")

        print(f"\n✅ Indexing complete")
        print(f"   Processed: {items_processed} items")
        print(f"   Updated: {items_updated} items")

        return (items_processed, items_updated)

    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        print(f"❌ Indexing failed: {e}")
        return (0, 0)
    finally:
        client.close()


def show_stats(repo_root: Optional[Path] = None):
    """
    Show embedding indexing statistics.

    Args:
        repo_root: Repository root path
    """
    client = get_client()

    try:
        collection = client.collections.get("ShortTermMemory")
        result = collection.query.fetch_objects(limit=10000)

        total = len(result.objects)
        with_vectors = sum(1 for obj in result.objects if obj.vector is not None and len(obj.vector) > 0)
        without_vectors = total - with_vectors

        print("\n=== Embedding Index Statistics ===")
        print(f"Total items: {total}")
        print(f"With embeddings: {with_vectors} ({100*with_vectors//max(total,1)}%)")
        print(f"Without embeddings: {without_vectors}")
        print(f"Embedding dimension: {EMBEDDING_DIM}")

        if with_vectors > 0:
            print(f"\n✅ Semantic search enabled ({with_vectors} vectors indexed)")
        else:
            print(f"\n⚠️  No embeddings indexed yet")
            print(f"   Run: python memory/index_embeddings.py")

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        print(f"❌ Failed to get stats: {e}")

    finally:
        client.close()


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Generate and index embeddings for Milton memory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of items to process per batch (default: 32)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate embeddings even if they already exist"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show embedding statistics and exit"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    print("=== Milton Memory Embedding Indexer ===\n")

    if args.stats:
        show_stats()
    else:
        processed, updated = index_embeddings(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            force=args.force
        )

        if not args.dry_run and updated > 0:
            print("\nRun with --stats to see indexing statistics")


if __name__ == "__main__":
    main()
