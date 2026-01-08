#!/usr/bin/env python3
"""
Export Training Data for LoRA Fine-Tuning

Exports conversations from Milton memory to SFT (Supervised Fine-Tuning) format.
Includes PII filtering, request/result pairing, and train/test splitting.

Usage:
    python scripts/export_training_data.py --days 30 [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from milton_orchestrator.state_paths import resolve_state_dir
from memory.backends import get_backend
from memory.retrieve import query_recent
from memory.schema import MemoryItem

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

# PII Detection Patterns
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b')
API_KEY_PATTERN = re.compile(r'\b(?:sk|pk|api|key)[-_]?[A-Za-z0-9]{20,}\b', re.IGNORECASE)
URL_WITH_TOKEN_PATTERN = re.compile(r'https?://[^\s]+[?&](?:token|key|api_key)=[^\s&]+')

# Milton system message
MILTON_SYSTEM_MESSAGE = """You are Milton, a personal AI assistant designed to help with daily tasks, memory management, research, and code execution.

You have access to the user's preferences, past conversations, and can perform various tasks including:
- Managing reminders and calendar events
- Researching topics using web search
- Executing code and system commands
- Tracking project status and goals
- Generating morning and evening briefings

You should be helpful, concise, and respectful of user privacy."""


def contains_pii(text: str) -> bool:
    """
    Check if text contains PII (Personal Identifiable Information).

    Args:
        text: Text to check

    Returns:
        True if PII detected, False otherwise
    """
    if EMAIL_PATTERN.search(text):
        return True
    if PHONE_PATTERN.search(text):
        return True
    if API_KEY_PATTERN.search(text):
        return True
    if URL_WITH_TOKEN_PATTERN.search(text):
        return True
    return False


def redact_pii(text: str) -> str:
    """
    Redact PII from text by replacing with placeholders.

    Args:
        text: Text to redact

    Returns:
        Text with PII replaced by placeholders
    """
    text = EMAIL_PATTERN.sub("[EMAIL]", text)
    text = PHONE_PATTERN.sub("[PHONE]", text)
    text = API_KEY_PATTERN.sub("[API_KEY]", text)
    text = URL_WITH_TOKEN_PATTERN.sub("[URL_WITH_TOKEN]", text)
    return text


def fetch_conversations(days: int, repo_root: Optional[Path] = None) -> List[MemoryItem]:
    """
    Fetch conversation memory items from backend.

    Args:
        days: Number of days to fetch
        repo_root: Repository root path

    Returns:
        List of MemoryItem objects
    """
    backend = get_backend(repo_root=repo_root)
    hours = days * 24

    logger.info(f"Fetching memory items from last {days} days ({hours} hours)...")
    items = query_recent(hours=hours, backend=backend, limit=10000)

    logger.info(f"Found {len(items)} memory items")
    return items


def pair_requests_results(items: List[MemoryItem]) -> List[Tuple[MemoryItem, MemoryItem]]:
    """
    Pair request memory items with their result counterparts via request_id.

    Args:
        items: List of all memory items

    Returns:
        List of (request, result) tuples
    """
    # Group items by request_id
    by_request_id = defaultdict(list)
    for item in items:
        if item.request_id:
            by_request_id[item.request_id].append(item)

    # Find request-result pairs
    pairs = []
    for request_id, group in by_request_id.items():
        requests = [item for item in group if item.type == "request"]
        results = [item for item in group if item.type == "result"]

        # Match each request with its corresponding result (chronologically)
        if requests and results:
            # Sort by timestamp
            requests.sort(key=lambda x: x.ts)
            results.sort(key=lambda x: x.ts)

            # Pair them up (1:1 matching)
            for req, res in zip(requests, results):
                # Verify result comes after request
                if res.ts >= req.ts:
                    pairs.append((req, res))

    logger.info(f"Paired {len(pairs)} request-result conversations")
    return pairs


def format_as_chat(pair: Tuple[MemoryItem, MemoryItem]) -> Dict[str, Any]:
    """
    Format a request-result pair as a chat conversation for SFT.

    Args:
        pair: Tuple of (request, result) MemoryItems

    Returns:
        Dict with "messages" key containing list of chat messages
    """
    request, result = pair

    return {
        "messages": [
            {"role": "system", "content": MILTON_SYSTEM_MESSAGE},
            {"role": "user", "content": request.content},
            {"role": "assistant", "content": result.content}
        ]
    }


def split_train_test(
    pairs: List[Dict[str, Any]],
    ratio: float = 0.2,
    seed: int = 42
) -> Tuple[List[Dict], List[Dict]]:
    """
    Split data into train and test sets deterministically.

    Args:
        pairs: List of formatted chat conversations
        ratio: Test set ratio (0.0-1.0)
        seed: Random seed for reproducibility

    Returns:
        Tuple of (train_data, test_data)
    """
    random.seed(seed)
    shuffled = pairs.copy()
    random.shuffle(shuffled)

    split_idx = int(len(shuffled) * (1 - ratio))
    train_data = shuffled[:split_idx]
    test_data = shuffled[split_idx:]

    logger.info(f"Split: {len(train_data)} train, {len(test_data)} test (ratio: {ratio:.2f})")
    return train_data, test_data


def compute_dataset_hash(data: List[Dict]) -> str:
    """
    Compute SHA256 hash of dataset for tracking.

    Args:
        data: List of examples

    Returns:
        Hex digest of SHA256 hash
    """
    content = json.dumps(data, sort_keys=True).encode()
    return hashlib.sha256(content).hexdigest()


def export_to_jsonl(
    train_data: List[Dict],
    test_data: List[Dict],
    output_dir: Path,
    days: int
):
    """
    Export train and test data to JSONL files with metadata.

    Args:
        train_data: Training examples
        test_data: Test examples
        output_dir: Output directory path
        days: Number of days exported
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write train.jsonl
    train_file = output_dir / "train.jsonl"
    with train_file.open("w") as f:
        for example in train_data:
            f.write(json.dumps(example) + "\n")

    # Write test.jsonl
    test_file = output_dir / "test.jsonl"
    with test_file.open("w") as f:
        for example in test_data:
            f.write(json.dumps(example) + "\n")

    # Compute dataset hash
    all_data = train_data + test_data
    dataset_hash = compute_dataset_hash(all_data)

    # Compute date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Write metadata.json
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "num_train": len(train_data),
        "num_test": len(test_data),
        "num_total": len(all_data),
        "test_ratio": len(test_data) / len(all_data) if all_data else 0.0,
        "dataset_hash": dataset_hash,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "files": {
            "train": str(train_file.relative_to(ROOT_DIR)),
            "test": str(test_file.relative_to(ROOT_DIR))
        }
    }

    metadata_file = output_dir / "metadata.json"
    with metadata_file.open("w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✅ Exported to {output_dir}/")
    logger.info(f"   Train: {train_file.name} ({len(train_data)} examples)")
    logger.info(f"   Test: {test_file.name} ({len(test_data)} examples)")
    logger.info(f"   Metadata: {metadata_file.name}")
    logger.info(f"   Dataset hash: {dataset_hash[:16]}...")


def main():
    parser = argparse.ArgumentParser(description="Export training data from Milton memory")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to export (default: 30)"
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.2,
        help="Test set ratio (default: 0.2)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "training" / "data" / "exported",
        help="Output directory (default: training/data/exported/)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview export without writing files"
    )
    parser.add_argument(
        "--no-pii-check",
        action="store_true",
        help="Skip PII detection (not recommended)"
    )
    args = parser.parse_args()

    print("=== Milton Training Data Export ===\n")

    # Fetch conversations
    items = fetch_conversations(days=args.days, repo_root=ROOT_DIR)

    if not items:
        logger.error("No memory items found")
        sys.exit(1)

    # Pair requests and results
    pairs = pair_requests_results(items)

    if not pairs:
        logger.error("No request-result pairs found")
        logger.info("Make sure your memory contains both 'request' and 'result' type items with matching request_id")
        sys.exit(1)

    # Filter out conversations with PII
    if not args.no_pii_check:
        original_count = len(pairs)
        filtered_pairs = []
        pii_count = 0

        for req, res in pairs:
            if contains_pii(req.content) or contains_pii(res.content):
                pii_count += 1
                # Redact and keep
                req_content = redact_pii(req.content)
                res_content = redact_pii(res.content)
                # Create modified copies
                from dataclasses import replace
                req_redacted = replace(req, content=req_content)
                res_redacted = replace(res, content=res_content)
                filtered_pairs.append((req_redacted, res_redacted))
            else:
                filtered_pairs.append((req, res))

        logger.info(f"PII check: {pii_count}/{original_count} conversations redacted")
        pairs = filtered_pairs

    # Format as chat conversations
    formatted = [format_as_chat(pair) for pair in pairs]

    # Split train/test
    train_data, test_data = split_train_test(formatted, ratio=args.test_ratio)

    if len(train_data) < 10:
        logger.warning(f"⚠️  Small training set: {len(train_data)} examples (recommend ≥10)")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print(f"Found {len(items)} items → {len(pairs)} pairs → {len(formatted)} formatted")
        print(f"Train: {len(train_data)}, Test: {len(test_data)}")
        print(f"Would write to: {args.output_dir}/")
        print("\nExample conversation:")
        if formatted:
            print(json.dumps(formatted[0], indent=2))
    else:
        # Export to JSONL
        export_to_jsonl(train_data, test_data, args.output_dir, args.days)
        print(f"\n✅ Export complete! Training data ready at {args.output_dir}/")


if __name__ == "__main__":
    main()
