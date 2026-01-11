#!/usr/bin/env python3
"""
Deploy the best model from autobench results.

This script:
1. Finds the latest benchmark results
2. Selects the best model using selection policy
3. Packages the model into an edge bundle
4. Deploys to target path with validation

Usage:
    python scripts/deploy_best_model.py --dry-run
    python scripts/deploy_best_model.py --target-path /path/to/deployment
    python scripts/deploy_best_model.py --benchmark-file benchmark_20260111_195651.json
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from benchmarks.schema import BenchmarkRun
from benchmarks.select import ModelSelector
from deployment.edge_packager import EdgePackager
from deployment.deployment_manager import DeploymentManager
from training.model_registry import ModelRegistry


def find_latest_benchmark(benchmarks_dir: Path) -> Path:
    """Find the latest benchmark results file."""
    benchmark_files = list(benchmarks_dir.glob("benchmark_*.json"))
    if not benchmark_files:
        raise FileNotFoundError(f"No benchmark files found in {benchmarks_dir}")
    
    # Sort by filename (YYYYMMDD_HHMMSS format)
    benchmark_files.sort(reverse=True)
    return benchmark_files[0]


def get_artifact_path_from_registry(
    model_version: str, 
    registry: ModelRegistry,
    artifact_type: str = "gguf"
) -> tuple[Path, str]:
    """
    Get artifact path from registry.
    
    Args:
        model_version: Model version to look up
        registry: Model registry instance
        artifact_type: "gguf" or "hf-distilled"
    
    Returns:
        (artifact_path, artifact_type)
    
    Raises:
        ValueError: If model not found
        RuntimeError: If GGUF requested but not available
    """
    entries = registry.list_models()
    for entry in entries:
        if entry.version == model_version:
            if artifact_type == "gguf":
                # Try to get GGUF path from metrics.compression.gguf_path
                gguf_path = None
                if hasattr(entry, 'metrics') and isinstance(entry.metrics, dict):
                    compression = entry.metrics.get('compression', {})
                    gguf_path = compression.get('gguf_path')
                
                if not gguf_path:
                    raise RuntimeError(
                        f"❌ No GGUF found for model {model_version}.\n"
                        f"   The registry entry does not have metrics.compression.gguf_path.\n"
                        f"   Next steps:\n"
                        f"     1. Run quantization: python scripts/quantize_model.py\n"
                        f"     2. Or use HF distilled: --artifact hf-distilled"
                    )
                
                gguf_path = Path(gguf_path)
                if not gguf_path.exists():
                    raise RuntimeError(
                        f"❌ GGUF path does not exist: {gguf_path}\n"
                        f"   Registry points to missing file.\n"
                        f"   Next steps:\n"
                        f"     1. Check if file was moved/deleted\n"
                        f"     2. Re-run quantization: python scripts/quantize_model.py\n"
                        f"     3. Or use HF distilled: --artifact hf-distilled"
                    )
                
                if not gguf_path.is_file():
                    raise RuntimeError(
                        f"❌ GGUF path is not a file: {gguf_path}\n"
                        f"   Expected a single .gguf file, got directory or other.\n"
                        f"   Next steps:\n"
                        f"     1. Check registry entry for correct path\n"
                        f"     2. Or use HF distilled: --artifact hf-distilled"
                    )
                
                return gguf_path, "gguf"
            
            else:  # hf-distilled
                model_path = Path(entry.model_path)
                if not model_path.exists():
                    raise RuntimeError(
                        f"❌ HF distilled model path does not exist: {model_path}"
                    )
                return model_path, "hf-distilled"
    
    raise ValueError(f"Model not found in registry: {model_version}")


def main():
    parser = argparse.ArgumentParser(description="Deploy best model from autobench results")
    parser.add_argument(
        "--benchmark-file",
        type=str,
        help="Specific benchmark file to use (default: latest)"
    )
    parser.add_argument(
        "--target-path",
        type=str,
        help="Target deployment path (default: auto in deployment_dir)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, do not deploy"
    )
    parser.add_argument(
        "--skip-checksum",
        action="store_true",
        help="Skip checksum verification"
    )
    parser.add_argument(
        "--skip-load-test",
        action="store_true",
        help="Skip load test"
    )
    parser.add_argument(
        "--benchmarks-dir",
        type=str,
        default=str(Path.home() / ".local" / "state" / "milton" / "benchmarks" / "runs"),
        help="Directory containing benchmark results"
    )
    parser.add_argument(
        "--artifact",
        type=str,
        choices=["gguf", "hf-distilled"],
        default="gguf",
        help="Artifact type to bundle: gguf (default, fast 4GB) or hf-distilled (slow 15GB)"
    )
    
    args = parser.parse_args()
    
    # Find benchmark file
    benchmarks_dir = Path(args.benchmarks_dir)
    if args.benchmark_file:
        benchmark_path = benchmarks_dir / args.benchmark_file
    else:
        benchmark_path = find_latest_benchmark(benchmarks_dir)
    
    print(f"Using benchmark: {benchmark_path.name}")
    
    # Load benchmark results
    benchmark_run = BenchmarkRun.load(benchmark_path)
    print(f"Run ID: {benchmark_run.metadata.run_id}")
    print(f"Candidates: {len(benchmark_run.candidates)}")
    
    # Select best model
    selector = ModelSelector()
    selection_result = selector.select_best_model(benchmark_run)
    
    if selection_result.recommended_model is None:
        print(f"\n❌ No candidate passed selection thresholds")
        print(f"   Reason: {selection_result.reason}")
        return 1
    
    # Find the candidate
    best_candidate = None
    for candidate in benchmark_run.candidates:
        if candidate.version == selection_result.recommended_model:
            best_candidate = candidate
            break
    
    if best_candidate is None:
        print(f"\n❌ Error: Recommended model not found in candidates")
        return 1
    
    print(f"\n✅ Selected model: {best_candidate.version}")
    
    # Show metrics
    print("\n📊 Metrics:")
    
    if best_candidate.latency_ms.status.value == "ok":
        print(f"   latency_ms: {best_candidate.latency_ms.value:.2f} ms ({best_candidate.latency_ms.status.value})")
    if best_candidate.tokens_per_sec.status.value == "ok":
        print(f"   tokens_per_sec: {best_candidate.tokens_per_sec.value:.2f} tok/s ({best_candidate.tokens_per_sec.status.value})")
    if best_candidate.cove_pass_rate.status.value == "ok":
        print(f"   cove_pass_rate: {best_candidate.cove_pass_rate.value:.2f}% ({best_candidate.cove_pass_rate.status.value})")
    if best_candidate.retrieval_score.status.value == "ok":
        print(f"   retrieval_score: {best_candidate.retrieval_score.value:.2f}% ({best_candidate.retrieval_score.status.value})")
    
    # Initialize registry
    registry = ModelRegistry()
    
    # Get artifact path (GGUF by default)
    try:
        artifact_path, artifact_type = get_artifact_path_from_registry(
            best_candidate.version, 
            registry,
            artifact_type=args.artifact
        )
        print(f"\n📂 Artifact type: {artifact_type}")
        print(f"   Artifact path: {artifact_path}")
        if artifact_type == "hf-distilled":
            # Get size for warning
            if artifact_path.is_dir():
                import subprocess
                result = subprocess.run(
                    ["du", "-sh", str(artifact_path)],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    size = result.stdout.split()[0]
                    print(f"   ⚠️  WARNING: HF distilled directory is {size} - this may take several minutes to hash and bundle")
    except (ValueError, RuntimeError) as e:
        print(f"\n{e}")
        return 1
    
    # Create bundle
    print("\n📦 Creating edge bundle...")
    packager = EdgePackager()
    
    # Prepare registry entry
    registry_entries = registry.list_models()
    registry_entry = None
    for entry in registry_entries:
        if entry.version == best_candidate.version:
            registry_entry = entry.to_dict()
            break
    
    if registry_entry is None:
        print(f"❌ Registry entry not found for {best_candidate.version}")
        return 1
    
    # Prepare benchmark summary
    benchmark_summary = {
        "run_id": benchmark_run.metadata.run_id,
        "timestamp": benchmark_run.metadata.timestamp,
        "model_version": best_candidate.version,
        "metrics": {
            "latency_ms": {
                "value": best_candidate.latency_ms.value,
                "status": best_candidate.latency_ms.status.value
            },
            "tokens_per_sec": {
                "value": best_candidate.tokens_per_sec.value,
                "status": best_candidate.tokens_per_sec.status.value
            },
            "cove_pass_rate": {
                "value": best_candidate.cove_pass_rate.value,
                "status": best_candidate.cove_pass_rate.status.value
            },
            "retrieval_score": {
                "value": best_candidate.retrieval_score.value,
                "status": best_candidate.retrieval_score.status.value
            }
        }
    }
    
    try:
        bundle_path = packager.create_bundle(
            model_path=artifact_path,
            registry_entry=registry_entry,
            benchmark_summary=benchmark_summary,
            artifact_type=artifact_type
        )
        print(f"✅ Bundle created: {bundle_path.name}")
        print(f"   Size: {bundle_path.stat().st_size / (1024*1024):.2f} MB")
    except Exception as e:
        print(f"❌ Bundle creation failed: {e}")
        return 1
    
    # Deploy bundle
    print(f"\n🚀 {'[DRY RUN] ' if args.dry_run else ''}Deploying bundle...")
    manager = DeploymentManager()
    
    target_path = Path(args.target_path) if args.target_path else None
    
    try:
        record = manager.deploy_bundle(
            bundle_path=bundle_path,
            target_path=target_path,
            dry_run=args.dry_run,
            verify_checksums=not args.skip_checksum,
            run_load_test=not args.skip_load_test
        )
        
        if record.status == "success":
            print(f"✅ Deployment successful")
            print(f"   Deployment ID: {record.deployment_id}")
            print(f"   Target path: {record.target_path}")
            print(f"   Checksum verified: {record.checksum_verified}")
            print(f"   Load test passed: {record.load_test_passed}")
            if args.dry_run:
                print("\n⚠️  DRY RUN: No files were actually deployed")
        else:
            print(f"❌ Deployment failed: {record.error_message}")
            return 1
    
    except Exception as e:
        print(f"❌ Deployment error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
