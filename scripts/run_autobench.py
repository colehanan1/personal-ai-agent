#!/usr/bin/env python3
"""
Automated benchmark runner for Milton model registry.

Enumerates candidate models from the registry and produces benchmark result files
with comprehensive metrics and error tracking.
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.schema import (
    BenchmarkRun,
    BenchmarkCandidate,
    MetricResult,
    MetricStatus,
    RunMetadata,
    SystemInfo,
)
from benchmarks.backends import VLLMOpenAIBackend
from benchmarks.prompts import get_quick_prompts
from benchmarks.measure import run_prompt_benchmark, aggregate_measurements
from benchmarks.tiers.reasoning_cove import CoveEvaluator, DEFAULT_COVE_TEST_CASES
from benchmarks.tiers.retrieval import RetrievalEvaluator, load_golden_set
from training.model_registry import ModelRegistry
from milton_orchestrator.state_paths import resolve_state_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_model_file_size(model_path: Path) -> Optional[float]:
    """Get total size of model files in MB."""
    try:
        if not model_path.exists():
            return None
        
        total_size = 0
        if model_path.is_file():
            total_size = model_path.stat().st_size
        elif model_path.is_dir():
            for file in model_path.rglob("*"):
                if file.is_file():
                    total_size += file.stat().st_size
        
        return round(total_size / (1024 * 1024), 2)
    except Exception as e:
        logger.warning(f"Could not get file size for {model_path}: {e}")
        return None


def run_inference_benchmarks(
    backend,
    num_prompts: int = 3,
    num_iterations: int = 3,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Run inference benchmarks and return aggregated metrics.
    
    Args:
        backend: BenchmarkBackend instance
        num_prompts: Number of prompts to test
        num_iterations: Number of iterations per prompt
    
    Returns:
        Tuple of (first_token_latency_ms, total_latency_ms, tokens_per_sec)
    """
    prompts = get_quick_prompts(num_prompts)
    measurements = []
    
    for prompt_data in prompts:
        logger.debug(f"  Running prompt: {prompt_data['id']}")
        measurement = run_prompt_benchmark(
            backend=backend,
            prompt=prompt_data["prompt"],
            num_iterations=num_iterations,
            warmup_iterations=1,
            max_tokens=prompt_data.get("expected_tokens", 100),
            temperature=0.7,
        )
        measurements.append(measurement)
    
    # Aggregate across all prompts
    aggregated = aggregate_measurements(measurements)
    
    first_token_latency = None
    total_latency = None
    tokens_per_sec = None
    
    if aggregated.first_token_latency_ms:
        first_token_latency = aggregated.first_token_latency_ms.mean
    
    if aggregated.total_latency_ms:
        total_latency = aggregated.total_latency_ms.mean
    
    if aggregated.tokens_per_sec:
        tokens_per_sec = aggregated.tokens_per_sec.mean
    
    return first_token_latency, total_latency, tokens_per_sec


def run_cove_benchmark(backend) -> Optional[float]:
    """
    Run CoVe reasoning benchmark.
    
    Args:
        backend: BenchmarkBackend instance
    
    Returns:
        CoVe pass rate (0-100) or None on error
    """
    try:
        logger.info("  Running CoVe reasoning benchmark...")
        evaluator = CoveEvaluator(backend=backend)
        
        # Use default test cases
        results = evaluator.evaluate(DEFAULT_COVE_TEST_CASES)
        
        pass_rate = results.get("pass_rate", 0.0)
        logger.info(f"  CoVe pass rate: {pass_rate:.1f}% ({results['passed']}/{results['total_cases']} passed)")
        
        return pass_rate
    
    except Exception as e:
        logger.error(f"CoVe benchmark failed: {e}")
        return None


def run_retrieval_benchmark() -> Optional[float]:
    """
    Run retrieval quality benchmark.
    
    Returns:
        Retrieval F1 score (0-100) or None on error
    """
    try:
        logger.info("  Running retrieval benchmark...")
        
        # Load golden set
        golden_dir = Path(__file__).parent.parent / "benchmarks" / "goldens"
        documents, queries = load_golden_set(golden_dir)
        
        if not documents or not queries:
            logger.warning("  Golden set not found or empty")
            return None
        
        # Run evaluation
        evaluator = RetrievalEvaluator(documents=documents)
        results = evaluator.evaluate(queries, k=3)
        
        retrieval_score = results.get("retrieval_score", 0.0)
        logger.info(f"  Retrieval score: {retrieval_score:.1f}% (F1: {results['mean_f1']:.3f})")
        
        return retrieval_score
    
    except Exception as e:
        logger.error(f"Retrieval benchmark failed: {e}")
        return None


def create_candidate_from_registry_entry(entry, run_inference: bool = False, backend=None) -> BenchmarkCandidate:
    """Create a benchmark candidate from a registry entry."""
    model_path = Path(entry.model_path)
    
    # Determine model type
    if entry.quantization and entry.distilled_from:
        model_type = "quantized+distilled"
    elif entry.quantization:
        model_type = "quantized"
    elif entry.distilled_from:
        model_type = "distilled"
    else:
        model_type = "base"
    
    candidate = BenchmarkCandidate(
        version=entry.version,
        model_type=model_type,
        model_path=str(model_path),
        base_model=entry.base_model,
        quantization=entry.quantization,
        distilled_from=entry.distilled_from,
        file_size_mb=get_model_file_size(model_path),
    )
    
    # Check if model path exists
    if not model_path.exists():
        error_msg = f"Model path does not exist: {model_path}"
        logger.warning(f"{entry.version}: {error_msg}")
        
        # Mark all metrics as error
        for metric_name in ["latency_ms", "tokens_per_sec", "peak_vram_mb", 
                           "peak_ram_mb", "cove_pass_rate", "retrieval_score"]:
            setattr(
                candidate,
                metric_name,
                MetricResult(status=MetricStatus.ERROR, error_message=error_msg)
            )
    elif run_inference and backend is not None:
        # Run actual inference benchmarks
        logger.info(f"{entry.version}: Running inference benchmarks...")
        try:
            first_token, total, tps = run_inference_benchmarks(backend)
            
            if first_token is not None:
                candidate.latency_ms = MetricResult(
                    status=MetricStatus.OK,
                    value=first_token,
                    metadata={"metric": "first_token_latency"}
                )
            
            if total is not None:
                # Store total latency in peak_ram_mb temporarily
                # (will be properly structured in future phases)
                candidate.peak_ram_mb = MetricResult(
                    status=MetricStatus.OK,
                    value=total,
                    metadata={"metric": "total_latency"}
                )
            
            if tps is not None:
                candidate.tokens_per_sec = MetricResult(
                    status=MetricStatus.OK,
                    value=tps,
                )
            
            # Run CoVe reasoning benchmark
            cove_pass_rate = run_cove_benchmark(backend)
            if cove_pass_rate is not None:
                candidate.cove_pass_rate = MetricResult(
                    status=MetricStatus.OK,
                    value=cove_pass_rate,
                )
            else:
                candidate.cove_pass_rate = MetricResult(
                    status=MetricStatus.ERROR,
                    error_message="CoVe benchmark failed"
                )
            
            # Run retrieval benchmark
            retrieval_score = run_retrieval_benchmark()
            if retrieval_score is not None:
                candidate.retrieval_score = MetricResult(
                    status=MetricStatus.OK,
                    value=retrieval_score,
                )
            else:
                candidate.retrieval_score = MetricResult(
                    status=MetricStatus.ERROR,
                    error_message="Retrieval benchmark failed"
                )
            
            logger.info(f"{entry.version}: Benchmarks complete")
            logger.info(f"  First token: {first_token:.2f}ms" if first_token else "  First token: N/A")
            logger.info(f"  Total: {total:.2f}ms" if total else "  Total: N/A")
            logger.info(f"  Throughput: {tps:.2f} tok/s" if tps else "  Throughput: N/A")
            logger.info(f"  CoVe pass rate: {cove_pass_rate:.1f}%" if cove_pass_rate else "  CoVe: N/A")
            logger.info(f"  Retrieval score: {retrieval_score:.1f}%" if retrieval_score else "  Retrieval: N/A")
            
        except Exception as e:
            error_msg = f"Inference benchmark failed: {str(e)}"
            logger.error(f"{entry.version}: {error_msg}")
            candidate.latency_ms = MetricResult(
                status=MetricStatus.ERROR,
                error_message=error_msg
            )
            candidate.tokens_per_sec = MetricResult(
                status=MetricStatus.ERROR,
                error_message=error_msg
            )
    else:
        # Model exists but metrics are skipped (no backend running yet)
        logger.info(f"{entry.version}: Model exists, metrics skipped (no backend)")
    
    return candidate


def enumerate_candidates(
    registry: ModelRegistry,
    run_inference: bool = False,
    backend=None,
) -> List[BenchmarkCandidate]:
    """Enumerate all candidates from the registry."""
    candidates = []
    
    entries = registry.list_models()
    logger.info(f"Found {len(entries)} models in registry")
    
    for entry in entries:
        try:
            candidate = create_candidate_from_registry_entry(
                entry,
                run_inference=run_inference,
                backend=backend,
            )
            candidates.append(candidate)
        except Exception as e:
            logger.error(f"Failed to create candidate for {entry.version}: {e}")
    
    return candidates


def run_benchmark(
    registry_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
    run_inference: bool = False,
    backend_url: Optional[str] = None,
) -> Path:
    """
    Run benchmark enumeration and write results.
    
    Args:
        registry_path: Path to model registry (default: from state dir)
        output_dir: Output directory for results (default: state dir)
        dry_run: If True, mark as dry run in metadata
        run_inference: If True, run actual inference benchmarks
        backend_url: URL of inference backend (default: http://localhost:8000)
    
    Returns:
        Path to written JSON file
    """
    # Initialize paths
    if output_dir is None:
        output_dir = Path(resolve_state_dir()) / "benchmarks" / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load registry
    logger.info("Loading model registry...")
    registry = ModelRegistry(registry_path=registry_path)
    
    # Collect system info
    logger.info("Collecting system information...")
    system_info = SystemInfo.collect()
    
    # Create run metadata
    command_line = " ".join(sys.argv)
    metadata = RunMetadata.create(dry_run=dry_run, command_line=command_line)
    
    logger.info(f"Run ID: {metadata.run_id}")
    logger.info(f"Git SHA: {metadata.git_sha or 'unknown'}")
    logger.info(f"System: {system_info.hostname} ({system_info.platform})")
    logger.info(f"CPU: {system_info.cpu_info} ({system_info.cpu_count} cores)")
    logger.info(f"RAM: {system_info.total_ram_gb} GB")
    if system_info.gpu_info:
        logger.info(f"GPU: {system_info.gpu_info}")
    
    # Initialize backend if running inference
    backend = None
    if run_inference:
        logger.info("Initializing inference backend...")
        backend = VLLMOpenAIBackend(
            base_url=backend_url or "http://localhost:8000",
        )
        
        if not backend.is_available():
            error = backend.get_availability_error()
            logger.error(f"Backend not available: {error}")
            logger.warning("Continuing without inference benchmarks")
            run_inference = False
        else:
            logger.info("Backend available, warming up...")
            backend.warmup(num_iterations=2)
            logger.info("Warmup complete")
    
    # Enumerate candidates
    logger.info("Enumerating model candidates...")
    candidates = enumerate_candidates(
        registry,
        run_inference=run_inference,
        backend=backend,
    )
    
    logger.info(f"Found {len(candidates)} candidates")
    
    # Create benchmark run
    benchmark_run = BenchmarkRun(
        metadata=metadata,
        system_info=system_info,
        candidates=candidates,
    )
    
    # Write results
    output_path = output_dir / f"{metadata.run_id}.json"
    logger.info(f"Writing results to: {output_path}")
    benchmark_run.save(output_path)
    
    # Print summary
    logger.info("=" * 60)
    logger.info("BENCHMARK SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Run ID: {metadata.run_id}")
    logger.info(f"Candidates: {len(candidates)}")
    logger.info(f"Output: {output_path}")
    
    # Count by model type
    type_counts = {}
    for c in candidates:
        type_counts[c.model_type] = type_counts.get(c.model_type, 0) + 1
    
    logger.info("\nCandidates by type:")
    for model_type, count in sorted(type_counts.items()):
        logger.info(f"  {model_type}: {count}")
    
    # Count metrics with errors
    error_count = 0
    for c in candidates:
        for metric_name in ["latency_ms", "tokens_per_sec", "peak_vram_mb",
                           "peak_ram_mb", "cove_pass_rate", "retrieval_score"]:
            metric = getattr(c, metric_name)
            if metric.status == MetricStatus.ERROR:
                error_count += 1
                break
    
    if error_count > 0:
        logger.warning(f"\nCandidates with errors: {error_count}")
    
    logger.info("=" * 60)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Run automated benchmarks on Milton model registry"
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help="Path to model registry JSON (default: from state dir)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for benchmark results (default: state dir)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mark run as dry run (no actual benchmarking)",
    )
    parser.add_argument(
        "--run-inference",
        action="store_true",
        help="Run actual inference benchmarks (requires backend)",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default="http://localhost:8000",
        help="URL of inference backend (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        output_path = run_benchmark(
            registry_path=args.registry,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            run_inference=args.run_inference,
            backend_url=args.backend_url,
        )
        logger.info(f"\n✓ Benchmark completed successfully")
        logger.info(f"  Results: {output_path}")
        return 0
    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
