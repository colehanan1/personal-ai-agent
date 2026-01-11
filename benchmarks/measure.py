"""
Measurement and statistics utilities for benchmarking.

Provides functions for:
- Running repeated measurements with warmup
- Computing confidence intervals and statistics
- Handling outliers
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Callable, Optional, Any, Dict

from benchmarks.backends.base import InferenceResult


@dataclass
class MeasurementStats:
    """Statistics for a set of measurements."""
    mean: float
    median: float
    std_dev: float
    min_val: float
    max_val: float
    p95: float
    p99: float
    count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mean": round(self.mean, 2),
            "median": round(self.median, 2),
            "std_dev": round(self.std_dev, 2),
            "min": round(self.min_val, 2),
            "max": round(self.max_val, 2),
            "p95": round(self.p95, 2),
            "p99": round(self.p99, 2),
            "count": self.count,
        }


@dataclass
class BenchmarkMeasurement:
    """Result from a benchmark measurement with statistics."""
    first_token_latency_ms: Optional[MeasurementStats] = None
    total_latency_ms: Optional[MeasurementStats] = None
    tokens_per_sec: Optional[MeasurementStats] = None
    success_count: int = 0
    error_count: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "success_count": self.success_count,
            "error_count": self.error_count,
        }
        
        if self.first_token_latency_ms:
            result["first_token_latency_ms"] = self.first_token_latency_ms.to_dict()
        
        if self.total_latency_ms:
            result["total_latency_ms"] = self.total_latency_ms.to_dict()
        
        if self.tokens_per_sec:
            result["tokens_per_sec"] = self.tokens_per_sec.to_dict()
        
        if self.errors:
            result["errors"] = self.errors
        
        return result


def compute_stats(values: List[float]) -> Optional[MeasurementStats]:
    """
    Compute statistics for a list of values.
    
    Args:
        values: List of numeric values
    
    Returns:
        MeasurementStats or None if no valid values
    """
    if not values:
        return None
    
    # Filter out None and infinite values
    valid_values = [v for v in values if v is not None and abs(v) != float('inf')]
    
    if not valid_values:
        return None
    
    sorted_values = sorted(valid_values)
    
    return MeasurementStats(
        mean=statistics.mean(valid_values),
        median=statistics.median(valid_values),
        std_dev=statistics.stdev(valid_values) if len(valid_values) > 1 else 0.0,
        min_val=min(valid_values),
        max_val=max(valid_values),
        p95=_percentile(sorted_values, 0.95),
        p99=_percentile(sorted_values, 0.99),
        count=len(valid_values),
    )


def _percentile(sorted_values: List[float], p: float) -> float:
    """
    Calculate percentile from sorted values.
    
    Args:
        sorted_values: List of sorted numeric values
        p: Percentile (0.0 to 1.0)
    
    Returns:
        Percentile value
    """
    if not sorted_values:
        return 0.0
    
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = k - f
    
    if f + 1 < len(sorted_values):
        return sorted_values[f] + (sorted_values[f + 1] - sorted_values[f]) * c
    else:
        return sorted_values[f]


def run_repeated_measurement(
    measurement_fn: Callable[[], InferenceResult],
    num_iterations: int = 5,
    warmup_iterations: int = 2,
) -> BenchmarkMeasurement:
    """
    Run a measurement multiple times with warmup.
    
    Args:
        measurement_fn: Function that performs one measurement
        num_iterations: Number of measurement iterations (after warmup)
        warmup_iterations: Number of warmup iterations (discarded)
    
    Returns:
        BenchmarkMeasurement with aggregated statistics
    """
    # Warmup iterations
    for _ in range(warmup_iterations):
        measurement_fn()
    
    # Actual measurements
    results: List[InferenceResult] = []
    for _ in range(num_iterations):
        result = measurement_fn()
        results.append(result)
    
    # Aggregate results
    first_token_latencies = []
    total_latencies = []
    tokens_per_secs = []
    errors = []
    success_count = 0
    error_count = 0
    
    for result in results:
        if result.error:
            error_count += 1
            if result.error not in errors:
                errors.append(result.error)
        else:
            success_count += 1
            if result.first_token_latency_ms is not None:
                first_token_latencies.append(result.first_token_latency_ms)
            if result.total_latency_ms is not None:
                total_latencies.append(result.total_latency_ms)
            if result.tokens_per_sec is not None:
                tokens_per_secs.append(result.tokens_per_sec)
    
    return BenchmarkMeasurement(
        first_token_latency_ms=compute_stats(first_token_latencies),
        total_latency_ms=compute_stats(total_latencies),
        tokens_per_sec=compute_stats(tokens_per_secs),
        success_count=success_count,
        error_count=error_count,
        errors=errors,
    )


def run_prompt_benchmark(
    backend,
    prompt: str,
    num_iterations: int = 5,
    warmup_iterations: int = 2,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> BenchmarkMeasurement:
    """
    Run a benchmark for a specific prompt.
    
    Args:
        backend: BenchmarkBackend instance
        prompt: Input prompt
        num_iterations: Number of measurement iterations
        warmup_iterations: Number of warmup iterations
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
    
    Returns:
        BenchmarkMeasurement with statistics
    """
    def measure():
        return backend.run_inference(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    
    return run_repeated_measurement(
        measurement_fn=measure,
        num_iterations=num_iterations,
        warmup_iterations=warmup_iterations,
    )


def aggregate_measurements(measurements: List[BenchmarkMeasurement]) -> BenchmarkMeasurement:
    """
    Aggregate multiple benchmark measurements.
    
    Args:
        measurements: List of BenchmarkMeasurement objects
    
    Returns:
        Aggregated BenchmarkMeasurement
    """
    all_first_token = []
    all_total = []
    all_tokens_per_sec = []
    all_errors = []
    total_success = 0
    total_errors = 0
    
    for m in measurements:
        total_success += m.success_count
        total_errors += m.error_count
        all_errors.extend(m.errors)
        
        if m.first_token_latency_ms:
            # Use mean from each measurement's stats
            all_first_token.append(m.first_token_latency_ms.mean)
        
        if m.total_latency_ms:
            all_total.append(m.total_latency_ms.mean)
        
        if m.tokens_per_sec:
            all_tokens_per_sec.append(m.tokens_per_sec.mean)
    
    return BenchmarkMeasurement(
        first_token_latency_ms=compute_stats(all_first_token),
        total_latency_ms=compute_stats(all_total),
        tokens_per_sec=compute_stats(all_tokens_per_sec),
        success_count=total_success,
        error_count=total_errors,
        errors=list(set(all_errors)),  # Deduplicate errors
    )
