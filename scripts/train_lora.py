#!/usr/bin/env python3
"""
LoRA Fine-Tuning Training Script

Trains a LoRA adapter on exported conversation data using PEFT + transformers.
Produces versioned adapters with full metadata and training logs.

Usage:
    python scripts/train_lora.py --config training/configs/lora_default.yaml [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

# Training dependencies (imported lazily to avoid slow startup)
def _import_training_deps():
    """Lazy import of training dependencies."""
    global torch, transformers, peft, datasets
    try:
        import torch
        import transformers
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from datasets import load_dataset
        import datasets
    except ImportError as e:
        logger.error(f"Missing training dependencies: {e}")
        logger.error("Install with: pip install transformers peft datasets accelerate bitsandbytes")
        sys.exit(1)


@dataclass
class TrainingConfig:
    """Training configuration loaded from YAML."""

    # Model paths
    base_model_path: str
    run_name_prefix: str = "lora"

    # LoRA hyperparameters
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ])

    # Training hyperparameters
    learning_rate: float = 3e-4
    num_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    bf16: bool = True
    lr_scheduler_type: str = "cosine"
    warmup_steps: int = 10
    max_grad_norm: float = 1.0
    logging_steps: int = 10
    save_steps: int = 100

    # Data paths
    train_file: str = "training/data/exported/train.jsonl"
    test_file: str = "training/data/exported/test.jsonl"

    # Output paths
    adapters_dir: str = "adapters"
    runs_dir: str = "runs"

    # Advanced options
    max_seq_length: int = 2048
    use_gradient_checkpointing: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> "TrainingConfig":
        """
        Load configuration from YAML file.

        Args:
            path: Path to YAML config file

        Returns:
            TrainingConfig instance
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with path.open("r") as f:
            config_dict = yaml.safe_load(f)

        # Validate required fields
        required = ["base_model_path"]
        for field_name in required:
            if field_name not in config_dict:
                raise ValueError(f"Missing required field in config: {field_name}")

        return cls(**config_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "base_model_path": self.base_model_path,
            "run_name_prefix": self.run_name_prefix,
            "lora": {
                "r": self.lora_r,
                "alpha": self.lora_alpha,
                "dropout": self.lora_dropout,
                "target_modules": self.target_modules
            },
            "training": {
                "learning_rate": self.learning_rate,
                "num_epochs": self.num_epochs,
                "per_device_train_batch_size": self.per_device_train_batch_size,
                "gradient_accumulation_steps": self.gradient_accumulation_steps,
                "bf16": self.bf16,
                "lr_scheduler_type": self.lr_scheduler_type,
                "warmup_steps": self.warmup_steps,
                "max_grad_norm": self.max_grad_norm
            },
            "data": {
                "train_file": self.train_file,
                "test_file": self.test_file,
                "max_seq_length": self.max_seq_length
            }
        }


def get_git_info() -> Dict[str, Any]:
    """
    Capture git repository state for provenance.

    Returns:
        Dictionary with commit hash, branch, dirty state
    """
    try:
        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()[:7]  # Short hash

        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()

        # Check if working directory is dirty
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        is_dirty = len(result.stdout.strip()) > 0

        return {
            "hash": commit_hash,
            "branch": branch,
            "dirty": is_dirty
        }
    except subprocess.CalledProcessError:
        logger.warning("Failed to get git info (not a git repo?)")
        return {
            "hash": "unknown",
            "branch": "unknown",
            "dirty": False
        }


def validate_safety(config: TrainingConfig) -> List[str]:
    """
    Pre-training safety checks.

    Args:
        config: Training configuration

    Returns:
        List of validation errors (empty if all checks pass)
    """
    errors = []

    # Check base model exists
    base_model_path = Path(config.base_model_path)
    if not base_model_path.exists():
        errors.append(f"Base model not found: {base_model_path}")

    # Check training data exists
    train_file = ROOT_DIR / config.train_file
    test_file = ROOT_DIR / config.test_file

    if not train_file.exists():
        errors.append(f"Training file not found: {train_file}")
    if not test_file.exists():
        errors.append(f"Test file not found: {test_file}")

    # Check dataset not empty
    if train_file.exists():
        with train_file.open("r") as f:
            train_lines = sum(1 for _ in f)
        if train_lines < 10:
            errors.append(f"Training set too small: {train_lines} examples (need ≥10)")

    # Check disk space (need ≥10GB free)
    stat = os.statvfs(ROOT_DIR)
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
    if free_gb < 10:
        errors.append(f"Insufficient disk space: {free_gb:.1f}GB free (need ≥10GB)")

    # Warn if git dirty (not fatal)
    git_info = get_git_info()
    if git_info["dirty"]:
        logger.warning("⚠️  Git working directory is dirty (uncommitted changes)")

    return errors


def compute_dataset_hash(train_file: Path, test_file: Path) -> str:
    """
    Compute SHA256 hash of training data for provenance.

    Args:
        train_file: Path to train.jsonl
        test_file: Path to test.jsonl

    Returns:
        Hex digest of combined dataset hash
    """
    hasher = hashlib.sha256()

    for file_path in [train_file, test_file]:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)

    return hasher.hexdigest()


def load_and_prepare_data(config: TrainingConfig, tokenizer) -> datasets.DatasetDict:
    """
    Load JSONL files and prepare datasets.

    Args:
        config: Training configuration
        tokenizer: HuggingFace tokenizer

    Returns:
        DatasetDict with train and test splits
    """
    from datasets import load_dataset

    train_file = str(ROOT_DIR / config.train_file)
    test_file = str(ROOT_DIR / config.test_file)

    # Load JSONL files
    logger.info(f"Loading training data from {config.train_file}...")
    dataset = load_dataset(
        "json",
        data_files={"train": train_file, "test": test_file}
    )

    logger.info(f"  Train examples: {len(dataset['train'])}")
    logger.info(f"  Test examples: {len(dataset['test'])}")

    # Tokenization function
    def tokenize_function(examples):
        """Apply chat template and tokenize."""
        texts = []
        for messages in examples["messages"]:
            # Apply chat template
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False
            )
            texts.append(text)

        # Tokenize
        result = tokenizer(
            texts,
            truncation=True,
            max_length=config.max_seq_length,
            padding=False
        )

        # Copy input_ids to labels for causal LM
        result["labels"] = result["input_ids"].copy()

        return result

    # Tokenize datasets
    logger.info("Tokenizing datasets...")
    tokenized = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing"
    )

    return tokenized


def create_lora_model(config: TrainingConfig):
    """
    Load base model and apply LoRA configuration.

    Args:
        config: Training configuration

    Returns:
        Tuple of (model, tokenizer)
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    import torch

    logger.info(f"Loading base model from {config.base_model_path}...")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.base_model_path)

    # Set pad token if not present
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model with bfloat16
    model = AutoModelForCausalLM.from_pretrained(
        config.base_model_path,
        torch_dtype=torch.bfloat16 if config.bf16 else torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

    # Enable gradient checkpointing
    if config.use_gradient_checkpointing:
        model.gradient_checkpointing_enable()

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # LoRA configuration
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.target_modules,
        bias="none",
        task_type="CAUSAL_LM"
    )

    logger.info(f"Applying LoRA configuration (r={config.lora_r}, alpha={config.lora_alpha})...")
    model = get_peft_model(model, lora_config)

    # Print trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_pct = 100 * trainable_params / total_params

    logger.info(f"  Trainable params: {trainable_params:,} ({trainable_pct:.2f}%)")
    logger.info(f"  Total params: {total_params:,}")

    return model, tokenizer


def train(config: TrainingConfig, run_id: str, dry_run: bool = False) -> Path:
    """
    Execute LoRA training and save adapter.

    Args:
        config: Training configuration
        run_id: Unique run identifier (e.g., lora_20260105_142301)
        dry_run: If True, skip actual training

    Returns:
        Path to saved adapter directory
    """
    from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling

    # Create output directories
    adapter_dir = ROOT_DIR / config.adapters_dir / run_id
    run_dir = ROOT_DIR / config.runs_dir / run_id

    adapter_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Adapter output: {adapter_dir}")
    logger.info(f"Run artifacts: {run_dir}")

    if dry_run:
        logger.info("DRY RUN MODE - Skipping training")
        return adapter_dir

    # Load model and tokenizer
    model, tokenizer = create_lora_model(config)

    # Load and prepare data
    tokenized_dataset = load_and_prepare_data(config, tokenizer)

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False  # Causal LM, not masked LM
    )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(run_dir),
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        per_device_eval_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        bf16=config.bf16,
        lr_scheduler_type=config.lr_scheduler_type,
        warmup_steps=config.warmup_steps,
        max_grad_norm=config.max_grad_norm,
        logging_dir=str(run_dir / "logs"),
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        save_total_limit=2,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="tensorboard",
        remove_unused_columns=False
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["test"],
        data_collator=data_collator
    )

    # Train
    logger.info("Starting training...")
    start_time = datetime.now(timezone.utc)

    train_result = trainer.train()

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    logger.info(f"✅ Training complete ({duration:.0f}s)")
    logger.info(f"   Final loss: {train_result.training_loss:.4f}")

    # Save adapter
    logger.info(f"Saving adapter to {adapter_dir}...")
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    # Save metadata
    git_info = get_git_info()
    train_file = ROOT_DIR / config.train_file
    test_file = ROOT_DIR / config.test_file
    dataset_hash = compute_dataset_hash(train_file, test_file)

    # Load dataset metadata if available
    metadata_file = train_file.parent / "metadata.json"
    dataset_info = {}
    if metadata_file.exists():
        with metadata_file.open("r") as f:
            dataset_metadata = json.load(f)
            dataset_info = {
                "num_examples": dataset_metadata.get("num_total", 0),
                "date_range": dataset_metadata.get("date_range", {})
            }

    metadata = {
        "run_id": run_id,
        "status": "training",  # Will be updated by eval script
        "created_at": start_time.isoformat(),
        "git_hash": git_info["hash"],
        "git_branch": git_info["branch"],
        "git_dirty": git_info["dirty"],
        "dataset": {
            "hash": dataset_hash,
            **dataset_info
        },
        "training": {
            "config": config.to_dict(),
            "duration_seconds": int(duration),
            "final_loss": float(train_result.training_loss)
        },
        "paths": {
            "adapter_dir": str(adapter_dir),
            "run_dir": str(run_dir)
        }
    }

    metadata_path = adapter_dir / "metadata.json"
    with metadata_path.open("w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✅ Metadata saved to {metadata_path}")

    return adapter_dir


def main():
    parser = argparse.ArgumentParser(description="Train LoRA adapter on Milton conversations")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to training config YAML"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and show training plan without executing"
    )
    args = parser.parse_args()

    print("=== Milton LoRA Training ===\n")

    try:
        # Load configuration
        logger.info(f"Loading config from {args.config}...")
        config = TrainingConfig.from_yaml(args.config)

        # Generate run ID
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"{config.run_name_prefix}_{timestamp}"

        logger.info(f"Run ID: {run_id}")

        # Safety checks
        logger.info("Running safety checks...")
        errors = validate_safety(config)

        if errors:
            logger.error("❌ Safety checks failed:")
            for error in errors:
                logger.error(f"   • {error}")
            sys.exit(1)

        logger.info("✅ Safety checks passed")

        if args.dry_run:
            print("\n=== DRY RUN MODE ===")
            print(f"Would train adapter: {run_id}")
            print(f"Base model: {config.base_model_path}")
            print(f"LoRA config: r={config.lora_r}, alpha={config.lora_alpha}")
            print(f"Training data: {config.train_file}")
            print(f"Output: {config.adapters_dir}/{run_id}/")
            return

        # Import training dependencies (slow, so only when needed)
        logger.info("Loading training libraries (this may take a moment)...")
        _import_training_deps()

        # Train
        adapter_dir = train(config, run_id, dry_run=args.dry_run)

        print(f"\n✅ Training complete!")
        print(f"   Adapter: {adapter_dir}")
        print(f"\nNext steps:")
        print(f"   1. Evaluate: python scripts/eval_lora.py --run-id {run_id}")
        print(f"   2. Monitor: tensorboard --logdir {config.runs_dir}/{run_id}/logs")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
