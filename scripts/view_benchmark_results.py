#!/usr/bin/env python3
"""
View benchmark results with model rankings and selection.

Shows detailed benchmark summary with scores and recommendations.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.select import (
    select_best_model_from_file,
    SelectionWeights,
    SelectionThresholds,
)
from milton_orchestrator.state_paths import resolve_state_dir


def format_score_bar(score: float, width: int = 20) -> str:
    """Create a visual score bar."""
    filled = int(score * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {score:.3f}"


def print_benchmark_summary(benchmark_path: Path, detailed: bool = False):
    """Print formatted benchmark summary."""
    # Load benchmark data
    with open(benchmark_path) as f:
        data = json.load(f)
    
    # Print header
    print("=" * 80)
    print(f"BENCHMARK SUMMARY: {data['metadata']['run_id']}")
    print("=" * 80)
    print()
    
    # Print metadata
    print("Run Information:")
    print(f"  Timestamp: {data['metadata']['timestamp']}")
    print(f"  Git SHA: {data['metadata'].get('git_sha', 'unknown')}")
    print(f"  Git Branch: {data['metadata'].get('git_branch', 'unknown')}")
    print(f"  Dry Run: {data['metadata']['dry_run']}")
    print()
    
    # Print system info
    print("System Information:")
    sys_info = data['system_info']
    print(f"  Host: {sys_info['hostname']}")
    print(f"  Platform: {sys_info['platform']} {sys_info['platform_version']}")
    print(f"  CPU: {sys_info['cpu_info']} ({sys_info['cpu_count']} cores)")
    print(f"  RAM: {sys_info['total_ram_gb']} GB")
    if sys_info.get('gpu_info'):
        print(f"  GPU: {sys_info['gpu_info']}")
    print()
    
    # Print candidates summary
    print(f"Candidates: {len(data['candidates'])}")
    print()
    
    # Print each candidate's metrics
    for i, candidate in enumerate(data['candidates'], 1):
        print(f"{i}. {candidate['version']} ({candidate['model_type']})")
        print(f"   Path: {candidate['model_path']}")
        if candidate.get('file_size_mb'):
            print(f"   Size: {candidate['file_size_mb']:.2f} MB")
        
        print("   Metrics:")
        metrics = candidate['metrics']
        
        # Latency
        lat = metrics['latency_ms']
        if lat['status'] == 'ok':
            print(f"     First Token Latency: {lat['value']:.2f} ms")
        else:
            print(f"     First Token Latency: {lat['status']}")
        
        # Throughput
        tps = metrics['tokens_per_sec']
        if tps['status'] == 'ok':
            print(f"     Throughput: {tps['value']:.2f} tokens/sec")
        else:
            print(f"     Throughput: {tps['status']}")
        
        # CoVe
        cove = metrics['cove_pass_rate']
        if cove['status'] == 'ok':
            print(f"     CoVe Pass Rate: {cove['value']:.1f}%")
        else:
            print(f"     CoVe Pass Rate: {cove['status']}")
        
        # Retrieval
        retr = metrics['retrieval_score']
        if retr['status'] == 'ok':
            print(f"     Retrieval Score: {retr['value']:.1f}%")
        else:
            print(f"     Retrieval Score: {retr['status']}")
        
        print()


def print_model_rankings(benchmark_path: Path, weights: Optional[SelectionWeights] = None):
    """Print model rankings with scores."""
    # Run selection
    result = select_best_model_from_file(benchmark_path, weights=weights)
    
    print("=" * 80)
    print("MODEL RANKINGS")
    print("=" * 80)
    print()
    
    # Print weights used
    weights_dict = result.selection_metadata['weights']
    print("Scoring Weights:")
    print(f"  Latency (lower is better): {weights_dict['latency_ms']:.2f}")
    print(f"  Throughput (higher is better): {weights_dict['throughput']:.2f}")
    print(f"  CoVe Pass Rate: {weights_dict['cove_pass_rate']:.2f}")
    print(f"  Retrieval Score: {weights_dict['retrieval_score']:.2f}")
    print()
    
    # Print thresholds
    thresholds = result.selection_metadata['thresholds']
    print("Minimum Thresholds:")
    print(f"  CoVe Pass Rate: {thresholds['min_cove_pass_rate']:.1f}%")
    print(f"  Retrieval Score: {thresholds['min_retrieval_score']:.1f}%")
    if thresholds['max_latency_ms']:
        print(f"  Max Latency: {thresholds['max_latency_ms']:.2f} ms")
    if thresholds['min_throughput']:
        print(f"  Min Throughput: {thresholds['min_throughput']:.2f} tokens/sec")
    print()
    
    # Print rankings
    print("Rankings:")
    print()
    
    for rank, score in enumerate(result.all_scores, 1):
        status = "✓" if score.passed_thresholds else "✗"
        print(f"{rank}. {status} {score.model_version}")
        print(f"   Total Score: {format_score_bar(score.total_score)}")
        
        # Component scores
        print("   Component Scores:")
        for component, value in score.component_scores.items():
            print(f"     {component}: {value:.4f}")
        
        # Show failures
        if not score.passed_thresholds:
            print("   ⚠ Threshold Failures:")
            for failure in score.threshold_failures:
                print(f"     - {failure}")
        
        print()
    
    # Print recommendation
    print("=" * 80)
    if result.recommended_model:
        print(f"✓ RECOMMENDED MODEL: {result.recommended_model}")
        print(f"  Reason: {result.reason}")
    else:
        print(f"✗ NO MODEL RECOMMENDED")
        print(f"  Reason: {result.reason}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="View benchmark results with model rankings"
    )
    parser.add_argument(
        "benchmark_file",
        nargs="?",
        type=Path,
        help="Path to benchmark JSON file (default: latest)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed candidate information",
    )
    parser.add_argument(
        "--weights",
        help="Custom weights as JSON (e.g., '{\"latency_ms\": 0.3, \"throughput\": 0.3, \"cove_pass_rate\": 0.2, \"retrieval_score\": 0.2}')",
    )
    
    args = parser.parse_args()
    
    # Find benchmark file
    if args.benchmark_file is None:
        benchmarks_dir = Path(resolve_state_dir()) / "benchmarks" / "runs"
        if not benchmarks_dir.exists():
            print("Error: No benchmarks directory found", file=sys.stderr)
            return 1
        
        runs = sorted(benchmarks_dir.glob("benchmark_*.json"))
        if not runs:
            print("Error: No benchmark runs found", file=sys.stderr)
            return 1
        
        benchmark_file = runs[-1]
        print(f"Using latest benchmark: {benchmark_file.name}")
        print()
    else:
        benchmark_file = args.benchmark_file
        if not benchmark_file.exists():
            print(f"Error: Benchmark file not found: {benchmark_file}", file=sys.stderr)
            return 1
    
    # Parse custom weights if provided
    weights = None
    if args.weights:
        try:
            weights_dict = json.loads(args.weights)
            weights = SelectionWeights(**weights_dict)
        except Exception as e:
            print(f"Error parsing weights: {e}", file=sys.stderr)
            return 1
    
    # Print summary
    print_benchmark_summary(benchmark_file, detailed=args.detailed)
    
    # Print rankings
    print_model_rankings(benchmark_file, weights=weights)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
