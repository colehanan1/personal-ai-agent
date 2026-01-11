#!/usr/bin/env python3
"""
Create Minimal PEFT Adapter for Pipeline Testing

Creates a tiny LoRA adapter with minimal training (1 sample, 1 step)
purely to test the distillation and quantization pipeline end-to-end.

This is NOT for real training - just pipeline smoke testing.
"""
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

from training.adapter_manager import AdapterManager


def create_minimal_adapter(
    base_model_path: str,
    adapter_name: str,
    adapter_dir: Path,
):
    """
    Create a minimal PEFT adapter for pipeline testing.
    
    Args:
        base_model_path: Path to base model
        adapter_name: Name for the adapter
        adapter_dir: Directory to save adapter
    """
    print(f"Loading base model: {base_model_path}")
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(base_model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # Load model (small to fit in memory)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    
    print("Configuring LoRA...")
    
    # Minimal LoRA config
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,  # Minimal rank
        lora_alpha=16,
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"],  # Just 2 modules
        bias="none",
    )
    
    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    print("Creating minimal training dataset...")
    
    # Single training sample (just to initialize weights properly)
    train_data = Dataset.from_dict({
        "text": [
            "Hello, I am a test adapter for the Milton pipeline. This is a minimal training sample."
        ]
    })
    
    def tokenize_function(examples):
        outputs = tokenizer(
            examples["text"],
            truncation=True,
            max_length=128,
            padding="max_length",
        )
        outputs["labels"] = outputs["input_ids"].copy()
        return outputs
    
    train_data = train_data.map(tokenize_function, batched=True, remove_columns=["text"])
    
    print("Running minimal training (1 step)...")
    
    # Minimal training args - just 1 step to initialize properly
    training_args = TrainingArguments(
        output_dir=str(adapter_dir / "checkpoints"),
        max_steps=1,  # Just 1 step
        per_device_train_batch_size=1,
        save_strategy="no",  # Don't save checkpoints
        logging_steps=1,
        report_to="none",
        bf16=True,
        gradient_checkpointing=False,
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
    )
    
    trainer.train()
    
    print(f"Saving adapter to: {adapter_dir}")
    
    # Save adapter
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    
    # Verify saved files
    required_files = ["adapter_config.json", "adapter_model.safetensors"]
    for fname in required_files:
        fpath = adapter_dir / fname
        if not fpath.exists():
            raise RuntimeError(f"Expected file not created: {fpath}")
        print(f"  ✓ {fname} ({fpath.stat().st_size} bytes)")
    
    print("✓ Adapter created successfully")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create minimal PEFT adapter for testing")
    parser.add_argument(
        "--base-model",
        default="~/milton/models/Llama-3.1-8B-Instruct-HF",
        help="Path to base model",
    )
    parser.add_argument(
        "--name",
        default="minimal_test_adapter",
        help="Adapter name",
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    base_model_path = Path(args.base_model).expanduser().resolve()
    if not base_model_path.exists():
        print(f"ERROR: Base model not found: {base_model_path}")
        sys.exit(1)
    
    # Get adapter directory from AdapterManager
    am = AdapterManager()
    adapter_dir = Path(am.adapters_dir) / args.name
    
    print("=" * 60)
    print("Minimal Adapter Creation")
    print("=" * 60)
    print(f"Base model: {base_model_path}")
    print(f"Adapter name: {args.name}")
    print(f"Output directory: {adapter_dir}")
    print()
    
    # Create adapter
    create_minimal_adapter(
        str(base_model_path),
        args.name,
        adapter_dir,
    )
    
    print()
    print("Registering adapter...")
    
    # Register and activate
    am.register_adapter(
        args.name,
        str(adapter_dir),
        metadata={
            "type": "lora",
            "purpose": "pipeline_smoke_test",
            "base_model": str(base_model_path),
            "created_by": "create_minimal_adapter.py",
        }
    )
    am.activate(args.name)
    
    print(f"✓ Adapter registered and activated: {args.name}")
    print()
    print("You can now run:")
    print("  python scripts/distill_current_adapter.py")
    print("  python scripts/quantize_latest_model.py --bits 4")


if __name__ == "__main__":
    main()
