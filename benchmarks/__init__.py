"""
Benchmarking infrastructure for Milton model registry.

Provides schema definitions, runner, and utilities for automated benchmarking
of registered models with comprehensive metric tracking and error handling.
"""
from benchmarks.schema import (
    BenchmarkRun,
    BenchmarkCandidate,
    MetricResult,
    MetricStatus,
    RunMetadata,
    SystemInfo,
)

__all__ = [
    "BenchmarkRun",
    "BenchmarkCandidate",
    "MetricResult",
    "MetricStatus",
    "RunMetadata",
    "SystemInfo",
]
