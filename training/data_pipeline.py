"""
Data Pipeline for LoRA Training

Converts conversation logs from memory system into training examples.
Integrates with memory/compression_pipeline.py and importance_scorer.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from random import Random

from memory.backends import get_backend
from memory.schema import MemoryItem
from memory.importance_scorer import score as compute_importance
from milton_orchestrator.state_paths import resolve_state_dir

logger = logging.getLogger(__name__)


@dataclass
class TrainingExample:
    """A single training example for LoRA fine-tuning."""
    input: str
    output: str
    importance: float
    timestamp: str
    source_ids: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_chat_format(self) -> Dict[str, Any]:
        """
        Convert to chat format for training.
        
        Returns:
            {"messages": [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]}
        """
        return {
            "messages": [
                {"role": "user", "content": self.input},
                {"role": "assistant", "content": self.output}
            ],
            "metadata": {
                "importance": self.importance,
                "timestamp": self.timestamp,
                "source_ids": self.source_ids,
            }
        }


class DataPipeline:
    """
    Manages conversion of conversation logs to training data.
    
    Attributes:
        min_importance: Minimum importance threshold for inclusion
        max_age_days: Maximum age of conversations to include
        random_seed: Random seed for reproducible splits
    """
    
    def __init__(
        self,
        min_importance: float = 0.3,
        max_age_days: int = 60,
        random_seed: int = 42,
    ):
        """
        Initialize DataPipeline.
        
        Args:
            min_importance: Minimum importance score (0.0-1.0)
            max_age_days: Maximum age in days
            random_seed: Random seed for splits
        """
        self.min_importance = min_importance
        self.max_age_days = max_age_days
        self.random_seed = random_seed
        self.rng = Random(random_seed)
        
    def collect_conversations(
        self,
        repo_root: Optional[Path] = None,
    ) -> List[MemoryItem]:
        """
        Collect conversation data from memory system.
        
        Args:
            repo_root: Repository root path
            
        Returns:
            List of MemoryItem objects meeting criteria
        """
        backend = get_backend(repo_root=repo_root)
        items = backend.list_short_term()
        
        # Filter by age
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        items = [item for item in items if item.ts >= cutoff_time]
        
        # Compute importance scores
        for item in items:
            if item.importance == 0.0 or item.importance is None:
                item.importance = compute_importance(item)
        
        # Filter by importance
        items = [item for item in items if item.importance >= self.min_importance]
        
        logger.info(
            f"Collected {len(items)} conversations "
            f"(min_importance={self.min_importance}, max_age_days={self.max_age_days})"
        )
        
        return items
    
    def build_training_examples(
        self,
        items: List[MemoryItem],
    ) -> List[TrainingExample]:
        """
        Build training examples from memory items.
        
        Pairs consecutive user/assistant exchanges into training examples.
        
        Args:
            items: List of MemoryItem objects
            
        Returns:
            List of TrainingExample objects
        """
        examples = []
        
        # Sort by timestamp
        items_sorted = sorted(items, key=lambda x: x.ts)
        
        # Look for user request -> assistant response pairs
        i = 0
        while i < len(items_sorted) - 1:
            current = items_sorted[i]
            next_item = items_sorted[i + 1]
            
            # Check if this is a request-response pair
            if (current.source == "user" and next_item.source == "assistant"):
                # Build training example
                example = TrainingExample(
                    input=current.content,
                    output=next_item.content,
                    importance=max(current.importance, next_item.importance),
                    timestamp=current.ts.isoformat(),
                    source_ids=[current.id, next_item.id],
                    metadata={
                        "agent": current.agent,
                        "tags": list(set(current.tags + next_item.tags)),
                    }
                )
                examples.append(example)
                i += 2  # Skip both items
            else:
                i += 1
        
        logger.info(f"Built {len(examples)} training examples from {len(items)} items")
        return examples
    
    def split_dataset(
        self,
        examples: List[TrainingExample],
        train_ratio: float = 0.8,
    ) -> tuple[List[TrainingExample], List[TrainingExample]]:
        """
        Split examples into train/eval sets.
        
        Args:
            examples: List of training examples
            train_ratio: Ratio for training set (default: 0.8)
            
        Returns:
            Tuple of (train_examples, eval_examples)
        """
        # Shuffle with deterministic seed
        shuffled = examples.copy()
        self.rng.shuffle(shuffled)
        
        # Split
        split_idx = int(len(shuffled) * train_ratio)
        train_examples = shuffled[:split_idx]
        eval_examples = shuffled[split_idx:]
        
        logger.info(
            f"Split dataset: {len(train_examples)} train, {len(eval_examples)} eval"
        )
        
        return train_examples, eval_examples
    
    def export_to_jsonl(
        self,
        examples: List[TrainingExample],
        output_path: Path,
        chat_format: bool = True,
    ) -> None:
        """
        Export examples to JSONL file.
        
        Args:
            examples: List of training examples
            output_path: Output file path
            chat_format: Use chat format (default: True)
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            for example in examples:
                if chat_format:
                    data = example.to_chat_format()
                else:
                    data = example.to_dict()
                f.write(json.dumps(data) + '\n')
        
        logger.info(f"Exported {len(examples)} examples to {output_path}")
    
    def prepare_dataset(
        self,
        output_dir: Optional[Path] = None,
        train_ratio: float = 0.8,
        chat_format: bool = True,
    ) -> Dict[str, Any]:
        """
        Full pipeline: collect, build, split, and export dataset.
        
        Args:
            output_dir: Output directory (defaults to training/data/exported)
            train_ratio: Train/eval split ratio
            chat_format: Use chat format for export
            
        Returns:
            Dictionary with dataset statistics
        """
        if output_dir is None:
            output_dir = Path("training/data/exported")
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Collect conversations
        items = self.collect_conversations()
        
        if not items:
            logger.warning("No conversations found meeting criteria")
            return {
                "status": "empty",
                "train_count": 0,
                "eval_count": 0,
                "min_importance": self.min_importance,
            }
        
        # Build examples
        examples = self.build_training_examples(items)
        
        if not examples:
            logger.warning("No training examples could be built")
            return {
                "status": "no_examples",
                "items_collected": len(items),
                "train_count": 0,
                "eval_count": 0,
            }
        
        # Split
        train_examples, eval_examples = self.split_dataset(examples, train_ratio)
        
        # Export
        self.export_to_jsonl(
            train_examples,
            output_dir / "train.jsonl",
            chat_format=chat_format,
        )
        self.export_to_jsonl(
            eval_examples,
            output_dir / "test.jsonl",
            chat_format=chat_format,
        )
        
        # Statistics
        stats = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_collected": len(items),
            "examples_built": len(examples),
            "train_count": len(train_examples),
            "eval_count": len(eval_examples),
            "min_importance": self.min_importance,
            "max_age_days": self.max_age_days,
            "train_ratio": train_ratio,
            "avg_importance": sum(ex.importance for ex in examples) / len(examples),
            "output_dir": str(output_dir),
        }
        
        # Save stats
        with open(output_dir / "dataset_stats.json", 'w') as f:
            json.dumps(stats, indent=2, f=f)
        
        logger.info(f"Dataset prepared: {stats}")
        return stats


if __name__ == "__main__":
    # Test the data pipeline
    logging.basicConfig(level=logging.INFO)
    
    print("Testing DataPipeline...")
    pipeline = DataPipeline(min_importance=0.2, max_age_days=30)
    
    print("\nCollecting conversations...")
    items = pipeline.collect_conversations()
    print(f"  Collected {len(items)} items")
    
    if items:
        print("\nBuilding training examples...")
        examples = pipeline.build_training_examples(items)
        print(f"  Built {len(examples)} examples")
        
        if examples:
            print("\nSplitting dataset...")
            train, eval_set = pipeline.split_dataset(examples)
            print(f"  Train: {len(train)}, Eval: {len(eval_set)}")
            
            print("\nSample example:")
            if train:
                sample = train[0]
                print(f"  Input: {sample.input[:80]}...")
                print(f"  Output: {sample.output[:80]}...")
                print(f"  Importance: {sample.importance:.2f}")
    
    print("\n✅ DataPipeline test complete")
