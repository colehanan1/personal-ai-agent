#!/usr/bin/env python3
"""
Distill Current Adapter Script

Distills the currently active LoRA adapter into an optimized standalone model.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.adapter_manager import AdapterManager
from training.model_evolution import ModelEvolution, DistillationConfig
from training.model_registry import ModelRegistry


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


def main():
    parser = argparse.ArgumentParser(
        description="Distill current adapter into optimized model"
    )
    parser.add_argument(
        "--adapter-name",
        help="Specific adapter to distill (default: current active)",
    )
    parser.add_argument(
        "--base-model",
        default=str(Path.home() / "milton" / "models" / "Llama-3.1-8B-Instruct-HF"),
        help="Base model path",
    )
    parser.add_argument(
        "--output-name",
        help="Output model name (default: auto-generated)",
    )
    parser.add_argument(
        "--use-pruning",
        action="store_true",
        help="Enable weight pruning",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't actually distill",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize components
        adapter_manager = AdapterManager()
        model_evolution = ModelEvolution()
        
        # Get adapter to distill
        if args.adapter_name:
            adapter_info = None
            for adapter in adapter_manager.list_adapters():
                if adapter.name == args.adapter_name:
                    adapter_info = adapter
                    break
            
            if not adapter_info:
                logger.error(f"Adapter not found: {args.adapter_name}")
                return 1
        else:
            # Use active adapter
            adapter_info = adapter_manager.current_adapter()
            if not adapter_info:
                logger.error("No active adapter found")
                return 1
        
        logger.info(f"Distilling adapter: {adapter_info.name}")
        logger.info(f"Base model: {args.base_model}")
        
        # Configure distillation
        config = DistillationConfig(
            teacher_model_path=args.base_model,
            adapter_path=adapter_info.adapter_path,
            prune_magnitude_threshold=0.01 if args.use_pruning else 0.0,
        )
        
        # Generate output name
        output_name = args.output_name or f"distilled_{adapter_info.name}"
        output_path = model_evolution.models_dir / output_name
        
        # Distill model
        logger.info("Starting distillation...")
        distilled_path, metrics = model_evolution.distill_model(
            base_model_path=args.base_model,
            adapter_path=adapter_info.adapter_path,
            output_path=output_path,
            config=config,
            dry_run=args.dry_run,
        )
        
        # Print results
        print("\n" + "=" * 60)
        print("Distillation Complete")
        print("=" * 60)
        print(f"Output: {distilled_path}")
        print(f"Method: {metrics.method}")
        print(f"Parameters: {metrics.parameter_count:,}")
        print(f"Size: {metrics.model_size_mb:.1f} MB")
        print(f"Time: {metrics.training_time_seconds:.1f}s")
        
        # Output JSON metrics for automation
        metrics_output = {
            "status": "success",
            "adapter_name": adapter_info.name,
            "distilled_path": str(distilled_path),
            "metrics": metrics.to_dict(),
        }
        
        print("\nJSON Metrics:")
        print(json.dumps(metrics_output, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Distillation failed: {e}", exc_info=True)
        
        error_output = {
            "status": "error",
            "error": str(e),
        }
        print("\nJSON Output:")
        print(json.dumps(error_output, indent=2))
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
