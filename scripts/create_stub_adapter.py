#!/usr/bin/env python3
"""
Create Stub PEFT Adapter for Pipeline Testing

Creates a valid PEFT adapter structure without actual training.
Uses random initialization to create minimal-size weights.
"""
import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
from safetensors.torch import save_file

from training.adapter_manager import AdapterManager


def create_stub_adapter(adapter_name: str, adapter_dir: Path):
    """
    Create a stub PEFT adapter with valid structure.
    
    Args:
        adapter_name: Name for the adapter
        adapter_dir: Directory to save adapter
    """
    adapter_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating stub adapter at: {adapter_dir}")
    
    # Create adapter_config.json
    config = {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "inference_mode": False,
        "r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.1,
        "target_modules": ["q_proj", "v_proj"],
        "bias": "none",
        "modules_to_save": None,
        "init_lora_weights": True,
        "layers_to_transform": None,
        "layers_pattern": None,
    }
    
    config_path = adapter_dir / "adapter_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  ✓ adapter_config.json ({config_path.stat().st_size} bytes)")
    
    # Create minimal weight tensors (stub - just random small tensors)
    # These are placeholders to make the adapter structurally valid
    weights = {}
    
    # Create a few small weight matrices for 2 layers
    # Format: base_model.model.layers.{layer}.{module}.lora_{A/B}.weight
    for layer in [0, 1]:  # Just 2 layers
        for module in ["q_proj", "v_proj"]:
            # LoRA uses A and B matrices
            # A: (r, in_features), B: (out_features, r)
            # Using small dims to keep file tiny
            r = 8
            in_features = 128  # Much smaller than real model
            out_features = 128
            
            key_a = f"base_model.model.layers.{layer}.self_attn.{module}.lora_A.weight"
            key_b = f"base_model.model.layers.{layer}.self_attn.{module}.lora_B.weight"
            
            weights[key_a] = torch.randn(r, in_features, dtype=torch.float16) * 0.01
            weights[key_b] = torch.randn(out_features, r, dtype=torch.float16) * 0.01
    
    # Save as safetensors
    weights_path = adapter_dir / "adapter_model.safetensors"
    save_file(weights, str(weights_path))
    print(f"  ✓ adapter_model.safetensors ({weights_path.stat().st_size} bytes)")
    
    # Create README
    readme_path = adapter_dir / "README.md"
    with open(readme_path, 'w') as f:
        f.write(f"""# {adapter_name}

This is a stub PEFT adapter created for pipeline smoke testing.
It contains valid structure but random weights (not trained).

**Purpose:** Test distillation and quantization pipeline end-to-end.
**Created by:** create_stub_adapter.py
""")
    print(f"  ✓ README.md ({readme_path.stat().st_size} bytes)")
    
    print("✓ Stub adapter created successfully")
    
    # Return total size
    total_size = sum(f.stat().st_size for f in adapter_dir.iterdir() if f.is_file())
    print(f"  Total size: {total_size / 1024:.1f} KB")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create stub PEFT adapter for testing")
    parser.add_argument(
        "--name",
        default="smoke_test_adapter",
        help="Adapter name",
    )
    
    args = parser.parse_args()
    
    # Get adapter directory from AdapterManager
    am = AdapterManager()
    adapter_dir = Path(am.adapters_dir) / args.name
    
    print("=" * 60)
    print("Stub Adapter Creation")
    print("=" * 60)
    print(f"Adapter name: {args.name}")
    print(f"Output directory: {adapter_dir}")
    print()
    
    # Create adapter
    create_stub_adapter(args.name, adapter_dir)
    
    print()
    print("Registering adapter...")
    
    # Register and activate
    am.register_adapter(
        args.name,
        adapter_dir,  # Pass Path object
        quality_score=0.0,  # Stub adapter - no quality score
        metrics={
            "type": "lora",
            "purpose": "pipeline_smoke_test",
            "created_by": "create_stub_adapter.py",
            "note": "Stub adapter with random weights for pipeline testing only",
        },
        auto_activate=False,
    )
    am.activate(args.name)
    
    print(f"✓ Adapter registered and activated: {args.name}")
    print()
    print("Next steps:")
    print("  export LLAMA_CPP_DIR=$HOME/llama.cpp")
    print("  python scripts/distill_current_adapter.py")
    print("  python scripts/quantize_latest_model.py --bits 4")


if __name__ == "__main__":
    main()
