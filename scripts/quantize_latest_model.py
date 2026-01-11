#!/usr/bin/env python3
"""
Quantize Latest Model Script

Quantizes the latest distilled model for edge deployment.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.model_evolution import ModelEvolution
from training.model_compression import ModelCompression, QuantizationConfig
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
        description="Quantize latest distilled model"
    )
    parser.add_argument(
        "--model-path",
        help="Specific model to quantize (default: latest distilled)",
    )
    parser.add_argument(
        "--bits",
        type=int,
        choices=[4, 8],
        default=4,
        help="Quantization bits (4 or 8)",
    )
    parser.add_argument(
        "--format",
        choices=["gguf", "awq", "gptq"],
        default="gguf",
        help="Quantization format",
    )
    parser.add_argument(
        "--output-name",
        help="Output name (default: auto-generated)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate quantized model",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't actually quantize",
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
        model_evolution = ModelEvolution()
        model_compression = ModelCompression()
        
        # Find model to quantize
        if args.model_path:
            model_path = Path(args.model_path)
            if not model_path.exists():
                logger.error(f"Model not found: {model_path}")
                return 1
        else:
            # Find latest distilled model
            distilled_dir = model_evolution.models_dir
            distilled_models = sorted(distilled_dir.glob("distilled_*"), key=lambda p: p.stat().st_mtime)
            
            if not distilled_models:
                logger.error("No distilled models found")
                return 1
            
            model_path = distilled_models[-1]
        
        logger.info(f"Quantizing model: {model_path}")
        logger.info(f"Format: {args.format}, Bits: {args.bits}")
        
        # Configure quantization
        config = QuantizationConfig(
            bits=args.bits,
            format=args.format,
        )
        
        # Generate output name
        output_name = args.output_name or f"quantized_{model_path.name}_{args.bits}bit"
        
        # Quantize model
        logger.info("Starting quantization...")
        quantized_path, metrics = model_compression.quantize_model(
            model_path=model_path,
            output_name=output_name,
            config=config,
            dry_run=args.dry_run,
        )
        
        # Validate if requested
        validation_results = None
        if args.validate and not args.dry_run:
            logger.info("Validating quantized model...")
            validation_results = model_compression.validate_quantized_model(
                quantized_model_path=quantized_path,
                original_model_path=model_path,
            )
        
        # Print results
        print("\n" + "=" * 60)
        print("Quantization Complete")
        print("=" * 60)
        print(f"Output: {quantized_path}")
        print(f"Original Size: {metrics.original_size_mb:.0f} MB")
        print(f"Compressed Size: {metrics.compressed_size_mb:.0f} MB")
        print(f"Compression Ratio: {metrics.compression_ratio:.2f}x")
        print(f"Memory Reduction: {metrics.memory_reduction:.1%}")
        print(f"Inference Speedup: {metrics.inference_speedup:.2f}x")
        
        if validation_results:
            print(f"\nValidation: {'PASSED' if validation_results['validation_passed'] else 'FAILED'}")
            print(f"Output Similarity: {validation_results['output_similarity']:.2%}")
        
        # Output JSON metrics for automation
        metrics_output = {
            "status": "success",
            "model_path": str(model_path),
            "quantized_path": str(quantized_path),
            "metrics": metrics.to_dict(),
        }
        
        if validation_results:
            metrics_output["validation"] = validation_results
        
        print("\nJSON Metrics:")
        print(json.dumps(metrics_output, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Quantization failed: {e}", exc_info=True)
        
        error_output = {
            "status": "error",
            "error": str(e),
        }
        print("\nJSON Output:")
        print(json.dumps(error_output, indent=2))
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
